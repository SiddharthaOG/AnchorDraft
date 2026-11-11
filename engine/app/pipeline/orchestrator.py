"""Review pipeline orchestration service.

This module implements the main pipeline orchestration that connects all
review engine components into a complete execution flow.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.auth.supabase import get_supabase_client
from app.checks import run_deterministic_checks, DeterministicCheckResult
from app.llm import get_provider_with_fallback
from app.models.pipeline import (
    ProviderRequest,
    ProviderResult,
)
from app.llm.token_budget import TokenBudgetExceededError
from app.llm.prompt_builder import (
    build_provider_request,
    extract_offered_references,
    RuleData,
    FactData,
)
from app.validator import (
    run_citation_validator,
    ValidationContext,
    RuleRecord,
    FactRecord,
    AggregateValidationResult,
)
from app.models.pipeline import (
    ProviderError,
    RateLimitedError,
    TimeoutError,
    UnavailableError,
    BadOutputError,
    BlockedError,
    ValidatedFinding,
    ModelFindingCandidate,
    DeterministicFindingCandidate,
)
from app.store.db import get_db_pool
from app.auth.supabase import SupabaseClient
from app.visual import (
    run_visual_analysis,
    VisualGuideline,
    parse_visual_guidelines,
    VisualAnalysisResult,
    VisualFindingCandidate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PipelineInput:
    """Input data for the review pipeline."""
    review_id: str
    revision_id: str
    revision_text: str
    kit_id: str
    org_id: str
    purpose: str
    channel: str
    engine_version: str


@dataclass
class PipelineOutput:
    """Output from the review pipeline."""
    validated_findings: list
    llm_status: str  # "ok", "skipped", "failed"
    warnings: list
    llm_findings_raw: int
    llm_findings_dropped: int
    validator_stats: dict
    model: str | None
    prompt_version: str | None
    error: str | None


# ---------------------------------------------------------------------------
# Supabase data loading
# ---------------------------------------------------------------------------


class SupabaseDataLoader:
    """Loads all data needed for the review pipeline from Supabase."""

    def __init__(self):
        self._client = get_supabase_client()

    def load_review_input(self, review_id: str) -> PipelineInput:
        """Load all data needed for the pipeline for a given review."""
        supabase = self._client

        # Get review
        review = supabase._get_client().table("reviews").select("*").eq("id", review_id).execute()
        if not review.data:
            raise ValueError(f"Review {review_id} not found")
        review = review.data[0]

        # Get revision
        revision = supabase.get_revision(review["revision_id"])
        if not revision:
            raise ValueError(f"Revision {review['revision_id']} not found")

        # Get content to get purpose/channel
        content = supabase.get_content(revision["content_id"])
        if not content:
            raise ValueError(f"Content {revision['content_id']} not found")

        # Get kit
        kit = supabase._get_client().table("brand_kits").select("*").eq("id", review["kit_id"]).execute()
        if not kit.data:
            raise ValueError(f"Kit {review['kit_id']} not found")
        kit = kit.data[0]

        # Get rules and facts for the kit
        rules_data = supabase.get_kit_rules(kit["id"])
        facts_data = supabase.get_kit_facts(kit["id"])

        return PipelineInput(
            review_id=review_id,
            revision_id=review["revision_id"],
            revision_text=revision["body"],
            kit_id=kit["id"],
            org_id=review["org_id"],
            purpose=content["purpose"],
            channel=content["channel"],
            engine_version=review["engine_version"],
        )

    def load_rules_and_facts(self, kit_id: str) -> tuple[list[RuleData], list[FactData]]:
        """Load rules and facts for the given kit as RuleData/FactData."""
        supabase = self._client

        rules_data = supabase.get_kit_rules(kit_id)
        facts_data = supabase.get_kit_facts(kit_id)

        rules = []
        for r in rules_data:
            rules.append(RuleData(
                rule_key=r["rule_key"],
                category=r["category"],
                severity=r["severity"],
                title=r["title"],
                guideline_text=r["guideline_text"],
                check_kind=r["check_kind"],
                needs_reviewer=r.get("needs_reviewer", False),
            ))

        facts = []
        for f in facts_data:
            facts.append(FactData(
                fact_key=f["fact_key"],
                statement=f["statement"],
                source_note=f["source_note"],
                valid_until=f["valid_until"],
            ))

        return rules, facts

    def load_validation_context(
        self,
        kit_id: str,
        model_offered_rule_keys: set[str],
        model_offered_fact_keys: set[str],
    ) -> ValidationContext:
        """Load ValidationContext with all rules and facts for the kit."""
        rules, facts = self.load_rules_and_facts(kit_id)

        all_rules = []
        for r in rules:
            all_rules.append(RuleRecord(
                rule_key=r.rule_key,
                category=r.category,
                severity=r.severity,
                needs_reviewer=False,  # We'll need to load this from DB; for now default
                check_kind=r.check_kind,
            ))

        all_facts = []
        for f in facts:
            all_facts.append(FactRecord(
                fact_key=f.fact_key,
                statement=f.statement,
                valid_until=f.valid_until,
            ))

        return ValidationContext(
            all_rules=all_rules,
            all_facts=all_facts,
            model_offered_rule_keys=model_offered_rule_keys,
            model_offered_fact_keys=model_offered_fact_keys,
        )


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------


class ReviewOrchestrator:
    """Orchestrates the complete review pipeline execution."""

    def __init__(self):
        self.loader = SupabaseDataLoader()
        self.supabase = get_supabase_client()
        self.db_pool = None

    async def _get_db_pool(self):
        if self.db_pool is None:
            self.db_pool = await get_db_pool()
        return self.db_pool

    async def _claim_review(self, review_id: str) -> tuple[bool, Optional[uuid.UUID]]:
        """Attempt to claim a queued review for processing.

        Uses advisory lock and status update to atomically claim the review.
        Generates and stores a claim_token for fencing against stale workers.
        Returns (claimed: bool, claim_token: Optional[uuid]).
        """
        pool = await self._get_db_pool()

        # Try to atomically transition from queued to running with claim_token
        claim_token = uuid.uuid4()

        async with pool.pool.acquire() as conn:
            async with conn.transaction():
                # Acquire advisory lock for this review
                lock_id = int.from_bytes(
                    uuid.uuid5(uuid.NAMESPACE_DNS, review_id).bytes[:8],
                    "big",
                    signed=True,
                )
                await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_id)

                # Try to update status from queued to running with claim_token
                result = await conn.execute(
                    """
                    UPDATE reviews
                    SET status = 'running', started_at = now(), claim_token = $1, claimed_at = now()
                    WHERE id = $2 AND status = 'queued'
                    """,
                    claim_token,
                    uuid.UUID(review_id),
                )

                # Check if row was updated
                if result == "UPDATE 1":
                    return True, claim_token
                return False, None

    async def _load_review_data(self, review_id: str) -> PipelineInput:
        """Load all data needed for the pipeline."""
        return self.loader.load_review_input(review_id)

    async def _run_deterministic_checks(
        self,
        text: str,
        rules: list[RuleData],
    ) -> DeterministicCheckResult:
        """Run deterministic checks against the revision text."""
        # Filter to only deterministic rules
        deterministic_rules = [r for r in rules if r.check_kind == "deterministic"]
        return run_deterministic_checks(text, deterministic_rules)

    def _convert_deterministic_to_pipeline(
        self,
        det_result: DeterministicCheckResult,
    ) -> tuple[list, list]:
        """Convert deterministic check result to validator input format."""
        candidates = []
        skipped = []

        for c in det_result.candidates:
            # The deterministic checker already produces DeterministicFindingCandidate
            candidates.append(c)

        for s in det_result.skipped_checks:
            skipped.append({
                "rule_key": s.rule_key,
                "check_type": s.check_type,
                "reason": s.reason,
            })

        return candidates, skipped

    async def _run_model_analysis(
        self,
        text: str,
        rules: list[RuleData],
        facts: list[FactData],
        purpose: str,
        channel: str,
    ) -> tuple[list, list, str | None, str | None, int, int, list]:
        """Run model analysis using the provider factory.

        Returns:
            (model_candidates, skipped, model, prompt_version, raw_count, dropped_count, warnings)
        """
        # Build provider request
        model_rules = [r for r in rules if r.check_kind == "llm"]
        valid_facts = [f for f in facts if f.valid_until is None or f.valid_until >= __import__("datetime").date.today()]

        if not model_rules and not valid_facts:
            # No model-checked rules or valid facts - skip model analysis
            return [], [], None, None, 0, 0, ["llm_status = skipped: no model-checked rules or valid facts"]

        # Build prompt input
        from app.llm.prompt_builder import PromptInput
        prompt_input = PromptInput(
            draft_text=text,
            purpose=purpose,
            channel=channel,
            rules=model_rules,
            facts=valid_facts,
            max_findings=25,
        )

        provider_request = build_provider_request(prompt_input)
        provider = get_provider_with_fallback()

        try:
            result = await provider.generate_findings(provider_request)

            # Parse model response
            import json
            try:
                parsed = json.loads(result.raw_json)
                raw_findings = parsed.get("findings", [])
            except json.JSONDecodeError:
                # Bad JSON - will be caught by validator
                raw_findings = []

            # Convert to ModelFindingCandidate
            from app.models.pipeline import ModelFindingCandidate
            model_candidates = []
            for f in raw_findings:
                try:
                    model_candidates.append(ModelFindingCandidate.model_validate(f))
                except Exception:
                    # Invalid finding - will be caught by validator
                    pass

            return (
                model_candidates,
                [],  # skipped - provider handles this internally
                result.model,
                provider_request.system_instruction[:50],  # prompt_version approximation
                result.input_tokens,
                result.output_tokens,
                [],  # warnings - provider returns structured errors
            )

        except TokenBudgetExceededError as e:
            logger.warning("token_budget_exceeded", extra={"review_id": "unknown", "error": str(e)})
            return [], [], None, None, 0, 0, [f"token budget exceeded: {e}"]
        except (RateLimitedError, TimeoutError, UnavailableError, BadOutputError, BlockedError, ProviderError) as e:
            logger.warning("provider_error", extra={"review_id": "unknown", "error_type": type(e).__name__, "error": str(e)})
            raise
        except Exception as e:
            logger.exception("unexpected_provider_error", extra={"review_id": "unknown", "error": str(e)})
            raise ProviderError(f"Unexpected provider error: {e}")

    def _extract_offered_keys(self, rules: list[RuleData], facts: list[FactData]) -> tuple[set, set]:
        """Extract keys offered to the model."""
        model_rules = [r for r in rules if r.check_kind == "llm"]
        valid_facts = [f for f in facts if f.valid_until is None or f.valid_until >= __import__("datetime").date.today()]
        return (
            {r.rule_key for r in model_rules},
            {f.fact_key for f in valid_facts},
        )

    async def _load_visual_asset_ids(self, revision_id: str, org_id: str) -> list[UUID]:
        """Load visual asset IDs explicitly associated with a revision.

        Uses the revision-specific RPC to retrieve only assets explicitly linked
        to this revision (or its parent content), enforcing organization isolation.
        """
        try:
            # Call the revision-specific RPC that enforces:
            # - Revision exists and belongs to the organization
            # - Assets are explicitly linked to this revision
            # - Organization isolation is enforced
            # Use asyncio.to_thread since the Supabase client is synchronous
            import asyncio
            response = await asyncio.to_thread(
                lambda: self.supabase._get_client().rpc(
                    "get_visual_assets_for_revision",
                    {"_revision_id": revision_id, "_org_id": org_id},
                ).execute()
            )

            return [UUID(asset["id"]) for asset in (response.data or [])]
        except Exception as e:
            logger.error("load_visual_asset_ids_failed", extra={"revision_id": revision_id, "error": str(e)})
            # Don't silently return empty list on failure - propagate the error
            raise

    async def _run_validation(
        self,
        text: str,
        deterministic_candidates: list,
        model_candidates: list,
        rules: list,
        facts: list,
        model_offered_rules: set,
        model_offered_facts: set,
        visual_deterministic_candidates: list = None,
        visual_model_candidates: list = None,
    ) -> AggregateValidationResult:
        """Run citation validator on all candidates."""
        context = self.loader.load_validation_context(
            kit_id="",  # We'll pass the kit_id separately
            model_offered_rule_keys=model_offered_rules,
            model_offered_fact_keys=model_offered_facts,
        )
        # Override with actual data
        context.all_rules = [
            RuleRecord(
                rule_key=r.rule_key,
                category=r.category,
                severity=r.severity,
                needs_reviewer=r.needs_reviewer,
                check_kind=r.check_kind,
            )
            for r in rules
        ]
        context.all_facts = [
            FactRecord(
                fact_key=f.fact_key,
                statement=f.statement,
                valid_until=f.valid_until,
            )
            for f in facts
        ]

        return run_citation_validator(
            text,
            deterministic_candidates,
            model_candidates,
            context,
            visual_deterministic_candidates=visual_deterministic_candidates or [],
            visual_model_candidates=visual_model_candidates or [],
        )

    async def _persist_results(
        self,
        review_id: str,
        validation_result: AggregateValidationResult,
        llm_status: str,
        warnings: list,
        llm_findings_raw: int,
        llm_findings_dropped: int,
        validator_stats: dict,
        model: str | None,
        prompt_version: str | None,
        claim_token: uuid.UUID,
    ) -> None:
        """Persist validated findings and update review status via engine_complete_review."""
        pool = await self._get_db_pool()

        # Convert findings to JSON for the database function
        import json
        findings_json = []
        for f in validation_result.validated_findings:
            finding_dict = {
                "source": f.source,
                "ref_key": f.ref_key,
                "category": f.category,
                "severity": f.severity,
                "explanation": f.explanation,
                "suggestion": f.suggestion,
                "confidence": f.confidence,
                "needs_human": f.needs_human,
                "needs_reviewer": f.needs_reviewer,
            }
            # Add text-based evidence
            if f.quote is not None:
                finding_dict["quote"] = f.quote
                finding_dict["start_offset"] = f.start_offset
                finding_dict["end_offset"] = f.end_offset
            # Add visual evidence
            if f.asset_id is not None:
                finding_dict["asset_id"] = str(f.asset_id)
            if f.region is not None:
                finding_dict["region"] = f.region
            findings_json.append(finding_dict)

        findings_json = json.dumps(findings_json)

        async with pool.pool.acquire() as conn:
            await conn.execute(
                """
                SELECT engine_complete_review(
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                )
                """,
                uuid.UUID(review_id),
                "done",
                llm_status,
                json.dumps(warnings),
                llm_findings_raw,
                llm_findings_dropped,
                json.dumps(validator_stats),
                model,
                prompt_version,
                findings_json,
                claim_token,
            )

    async def _persist_failure(
        self,
        review_id: str,
        error: str,
        claim_token: Optional[uuid.UUID] = None,
    ) -> None:
        """Persist review failure via engine_fail_review."""
        pool = await self._get_db_pool()
        async with pool.pool.acquire() as conn:
            if claim_token:
                await conn.execute(
                    "SELECT engine_fail_review($1, $2, $3)",
                    uuid.UUID(review_id),
                    error,
                    claim_token,
                )
            else:
                await conn.execute(
                    "SELECT engine_fail_review($1, $2, $3)",
                    uuid.UUID(review_id),
                    error,
                    None,
                )

    async def run_pipeline(self, review_id: str) -> PipelineOutput:
        """Execute the complete review pipeline for a review."""
        start_time = time.time()
        claim_token: Optional[uuid.UUID] = None

        try:
            # 1. Claim the review
            claimed, claim_token = await self._claim_review(review_id)
            if not claimed:
                logger.info("review_already_claimed", extra={"review_id": review_id})
                return PipelineOutput(
                    validated_findings=[],
                    llm_status="failed",
                    warnings=["Review already claimed or not queued"],
                    llm_findings_raw=0,
                    llm_findings_dropped=0,
                    validator_stats={},
                    model=None,
                    prompt_version=None,
                    error="Review already claimed or not queued",
                )

            # 2. Load all data
            pipeline_input = await self._load_review_data(review_id)

            # 3. Load rules and facts
            rules, facts = self.loader.load_rules_and_facts(pipeline_input.kit_id)

            # 3b. Load visual guidelines from kit (optional - handle missing Supabase)
            visual_guidelines = {}
            try:
                kit = self.supabase._get_client().table("brand_kits").select("visual_guidelines").eq("id", pipeline_input.kit_id).execute()
                visual_guidelines = kit.data[0].get("visual_guidelines", {}) if kit.data else {}
            except Exception as e:
                logger.warning("visual_guidelines_load_failed", extra={"kit_id": pipeline_input.kit_id, "error": str(e)})
                visual_guidelines = {}

            # 3c. Load visual assets associated with this revision
            asset_ids = await self._load_visual_asset_ids(pipeline_input.revision_id, pipeline_input.org_id)

            # 4. Extract offered keys
            model_offered_rules, model_offered_facts = self._extract_offered_keys(rules, facts)

            # 5. Run deterministic checks (text)
            det_result = await self._run_deterministic_checks(
                pipeline_input.revision_text,
                rules,
            )
            deterministic_candidates, skipped_checks = self._convert_deterministic_to_pipeline(det_result)

            # 5b. Run visual analysis (skip if no assets or guidelines)
            visual_result = VisualAnalysisResult(
                deterministic_findings=[],
                model_findings=[],
                llm_status="skipped",
                warnings=[],
                raw_model_count=0,
                dropped_model_count=0,
            )
            if asset_ids:
                visual_result = await run_visual_analysis(
                    asset_ids=asset_ids,
                    revision_text=pipeline_input.revision_text,
                    purpose=pipeline_input.purpose,
                    channel=pipeline_input.channel,
                    visual_guidelines=visual_guidelines,
                    org_id=UUID(pipeline_input.org_id),
                    approved_logo_hashes=visual_guidelines.get("logo", {}).get("approved_hashes", []) if visual_guidelines else [],
                )

            # Visual findings are kept as-is (they have asset_id and region, not quote/offsets)
            # They will be passed directly to the validator which now handles visual candidates
            visual_deterministic_candidates = list(visual_result.deterministic_findings)

            # Combine deterministic candidates (text + visual)
            all_deterministic_candidates = deterministic_candidates + visual_deterministic_candidates

            # 6. Run model analysis (text + visual)
            warnings = []
            if skipped_checks:
                warnings.extend([f"Check skipped: {s['reason']}" for s in skipped_checks])

            llm_status = "ok"
            model = None
            prompt_version = "p1"
            llm_findings_raw = 0
            model_candidates = []
            model_warnings = []

            try:
                # Text model analysis
                text_model_candidates, _, model, _, input_tokens, output_tokens, model_warnings = \
                    await self._run_model_analysis(
                        pipeline_input.revision_text,
                        rules,
                        facts,
                        pipeline_input.purpose,
                        pipeline_input.channel,
                    )
                llm_findings_raw = len(text_model_candidates)
                warnings.extend(model_warnings)

                # Add visual model findings
                model_candidates = text_model_candidates + visual_result.model_findings
                llm_findings_raw = len(model_candidates)

                # Combine warnings
                warnings.extend(visual_result.warnings)
            except (RateLimitedError, TimeoutError, UnavailableError, BadOutputError, BlockedError, ProviderError) as e:
                llm_status = "failed"
                logger.warning(
                    "llm_failed_fallback_to_deterministic",
                    extra={"review_id": review_id, "error_type": type(e).__name__, "error": str(e)},
                )
                warnings.append(f"model unavailable: deterministic checks only ({type(e).__name__})")
                # Keep visual deterministic findings, but visual model findings failed
                model_candidates = visual_result.model_findings
                warnings.extend(visual_result.warnings)
            except Exception as e:
                llm_status = "failed"
                logger.exception(
                    "unexpected_llm_error",
                    extra={"review_id": review_id, "error": str(e)},
                )
                warnings.append(f"model error: deterministic checks only")
                model_candidates = visual_result.model_findings
                warnings.extend(visual_result.warnings)

            # 7. Run validation
            # 7. Run validation
            validation_result = await self._run_validation(
                pipeline_input.revision_text,
                all_deterministic_candidates,
                model_candidates,
                rules,
                facts,
                model_offered_rules=set([r.rule_key for r in rules if r.check_kind == "llm"]),
                model_offered_facts=model_offered_facts,
                visual_deterministic_candidates=visual_deterministic_candidates,
                visual_model_candidates=visual_result.model_findings,
            )

            # 8. Prepare validator stats
            total_dropped = sum(validation_result.dropped_counts.values())
            llm_findings_dropped = total_dropped
            validator_stats = {
                "raw": validation_result.raw_candidate_count,
                "kept": validation_result.kept_count,
                "dropped": validation_result.dropped_counts,
            }

            # 9. Persist results with claim_token for fencing
            await self._persist_results(
                review_id=review_id,
                validation_result=validation_result,
                llm_status=llm_status,
                warnings=warnings,
                llm_findings_raw=llm_findings_raw,
                llm_findings_dropped=llm_findings_dropped,
                validator_stats=validator_stats,
                model=model,
                prompt_version=prompt_version,
                claim_token=claim_token,
            )

            elapsed = time.time() - start_time
            logger.info(
                "pipeline_completed",
                extra={
                    "review_id": review_id,
                    "elapsed_ms": int(elapsed * 1000),
                    "llm_status": llm_status,
                    "findings_kept": validation_result.kept_count,
                    "findings_dropped": total_dropped,
                },
            )

            return PipelineOutput(
                validated_findings=validation_result.validated_findings,
                llm_status=llm_status,
                warnings=warnings,
                llm_findings_raw=llm_findings_raw,
                llm_findings_dropped=llm_findings_dropped,
                validator_stats=validator_stats,
                model=model,
                prompt_version=prompt_version,
                error=None,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(
                "pipeline_failed",
                extra={"review_id": review_id, "elapsed_ms": int((time.time() - start_time) * 1000), "error": str(e)},
            )

            # Try to persist failure with claim_token for fencing
            try:
                await self._persist_failure(review_id, str(e), claim_token)
            except Exception:
                logger.exception("failed_to_persist_failure", extra={"review_id": review_id})

            return PipelineOutput(
                validated_findings=[],
                llm_status="failed",
                warnings=[f"Pipeline error: {str(e)[:200]}"],
                llm_findings_raw=0,
                llm_findings_dropped=0,
                validator_stats={},
                model=None,
                prompt_version=None,
                error=str(e)[:500],
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Stale job recovery
# ---------------------------------------------------------------------------


async def reclaim_stale_reviews(lease_minutes: int = 30) -> int:
    """Reclaim stale running reviews by resetting them to queued.

    A review is considered stale if it has been in 'running' status for longer
    than the lease period and has a valid claim_token.

    Args:
        lease_minutes: Maximum minutes a review can be in 'running' status before
            being considered stale. Default 30 minutes.

    Returns:
        Number of reviews reclaimed (reset to queued).
    """
    pool = await get_db_pool()
    async with pool.pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT reclaim_stale_reviews($1)",
            lease_minutes,
        )
        return result or 0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_review_pipeline(review_id: str) -> PipelineOutput:
    """Run the complete review pipeline for a review.

    This is the main entry point for executing a review pipeline.
    It handles claiming, execution, validation, and persistence.

    Args:
        review_id: The UUID of the review to process.

    Returns:
        PipelineOutput with the execution results.
    """
    orchestrator = ReviewOrchestrator()
    return await orchestrator.run_pipeline(review_id)

