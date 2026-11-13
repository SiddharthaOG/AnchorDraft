"""Review pipeline orchestration service.

This module implements the main pipeline orchestration that connects all
review engine components into a complete execution flow.
"""

import asyncio
import json
import logging
import time
from datetime import date
import uuid
from dataclasses import dataclass, replace
from typing import Optional
from uuid import UUID

from app.auth.supabase import get_supabase_client
from app.checks import run_deterministic_checks, DeterministicCheckResult
from app.checks.deterministic import RuleConfig, SkippedCheck, check_map
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
from app.confidentiality import (
    ConfidentialityEngine,
    ConfidentialityPolicyStore,
    expand_placeholders,
)
from app.visual import (
    run_visual_analysis,
    VisualGuideline,
    parse_visual_guidelines,
    VisualAnalysisResult,
    VisualFindingCandidate,
)
from app.visual.vision_providers import get_visual_guideline_ref_keys

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
    preview_id: str | None = None


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
            preview_id=review.get("preview_id"),
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
                config=r.get("config"),
            ))

        facts = []
        for f in facts_data:
            facts.append(FactData(
                fact_key=f["fact_key"],
                statement=f["statement"],
                source_note=f["source_note"],
                valid_until=(
                    date.fromisoformat(f["valid_until"])
                    if isinstance(f.get("valid_until"), str)
                    else f.get("valid_until")
                ),
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

    async def _load_confirmed_preview(self, review_id: str, preview_id: str):
        """Load only the preview atomically consumed by this review."""
        pool = await self._get_db_pool()
        async with pool.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT p.*, r.requested_by AS review_requested_by
                FROM review_previews p
                JOIN reviews r ON r.preview_id=p.id
                WHERE r.id=$1 AND p.id=$2 AND p.review_id=r.id
                  AND p.consumed_at IS NOT NULL
                  AND p.confirmed_by=r.requested_by
                """,
                uuid.UUID(review_id), uuid.UUID(preview_id),
            )

    @staticmethod
    def _resolve_deterministic_rule(rule: RuleData) -> tuple[RuleConfig | None, str | None]:
        """Convert persisted rule data into a validated check configuration.

        Newer records may declare ``config.check``. Older records in existing
        kits predate that discriminator, so infer only from an unambiguous
        required-key signature. Never guess when the configuration is absent,
        malformed, ambiguous, or names an unsupported check.
        """
        config = rule.config
        if not isinstance(config, dict):
            return None, "Deterministic rule config must be an object"

        declared = config.get("check")
        signatures = {
            "term_map": {"entries"},
            "phrase_list": {"phrases"},
            "missing_alt_text": {"min_length", "generic"},
            "required_disclosure": {"when_any", "require_any"},
        }

        if declared is not None:
            if not isinstance(declared, str) or declared not in check_map or check_map[declared] is None:
                return None, f"Unsupported deterministic check type: {declared!r}"
            check_name = declared
        else:
            matches = [
                name for name, required_keys in signatures.items()
                if required_keys.issubset(config.keys())
            ]
            if len(matches) != 1:
                reason = "Ambiguous deterministic config shape" if matches else "Cannot infer deterministic check type from config"
                return None, reason
            check_name = matches[0]

        check_config = {key: value for key, value in config.items() if key != "check"}
        rule_config = RuleConfig(
            check=check_name,
            config=check_config,
            rule_key=rule.rule_key,
            category=rule.category,
            severity=rule.severity,
            guideline_text=rule.guideline_text,
            needs_reviewer=rule.needs_reviewer,
        )
        try:
            checker = check_map[check_name](rule_config)
            checker.validate_config()
        except (TypeError, ValueError) as exc:
            return None, f"Invalid {check_name} config: {exc}"
        except Exception as exc:
            return None, f"Unable to initialize {check_name} check: {type(exc).__name__}"
        return rule_config, None

    async def _run_deterministic_checks(
        self,
        text: str,
        rules: list[RuleData],
    ) -> DeterministicCheckResult:
        """Run deterministic checks; isolate unsupported rules as skipped."""
        deterministic_rules = [r for r in rules if r.check_kind == "deterministic"]
        resolved: list[RuleConfig] = []
        skipped: list[SkippedCheck] = []

        for rule in deterministic_rules:
            rule_config, reason = self._resolve_deterministic_rule(rule)
            if rule_config is None:
                skipped.append(SkippedCheck(
                    rule_key=rule.rule_key,
                    check_type="unresolved",
                    reason=reason or "Unsupported deterministic configuration",
                ))
            else:
                resolved.append(rule_config)

        result = run_deterministic_checks(text, resolved)
        result.skipped_checks = skipped + result.skipped_checks
        return result

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
        placeholder_map: dict[str, str] | None = None,
        provider_request_override: ProviderRequest | None = None,
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

        provider_request = provider_request_override or build_provider_request(prompt_input)
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

            # Restore private placeholders before validating citations against the
            # original revision. The reverse map never leaves this process.
            if placeholder_map:
                for candidate in model_candidates:
                    candidate.ref_key = expand_placeholders(candidate.ref_key, placeholder_map)
                    candidate.quote = expand_placeholders(candidate.quote, placeholder_map)
                    candidate.explanation = expand_placeholders(candidate.explanation, placeholder_map)
                    if candidate.suggestion:
                        candidate.suggestion = expand_placeholders(candidate.suggestion, placeholder_map)

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
            logger.warning("token_budget_exceeded", extra={"review_id": "unknown", "error_type": type(e).__name__})
            return [], [], None, None, 0, 0, [f"token budget exceeded: {e}"]
        except (RateLimitedError, TimeoutError, UnavailableError, BadOutputError, BlockedError, ProviderError) as e:
            logger.warning("provider_error", extra={"review_id": "unknown", "error_type": type(e).__name__})
            raise
        except Exception as e:
            logger.error("unexpected_provider_error", extra={"review_id": "unknown", "error_type": type(e).__name__})
            raise ProviderError(f"Unexpected provider error ({type(e).__name__})")

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
            logger.error("load_visual_asset_ids_failed", extra={"revision_id": revision_id, "error_type": type(e).__name__})
            # Don't silently return empty list on failure - propagate the error
            raise

    async def _run_validation(
        self,
        text: str,
        kit_id: str,
        deterministic_candidates: list,
        model_candidates: list,
        rules: list,
        facts: list,
        model_offered_rules: set,
        model_offered_facts: set,
        visual_deterministic_candidates: list = None,
        visual_model_candidates: list = None,
        visual_model_offered_rules: set = None,
    ) -> AggregateValidationResult:
        """Run citation validator on all candidates."""
        if not kit_id:
            raise ValueError("kit_id is required for citation validation")
        context = self.loader.load_validation_context(
            kit_id=kit_id,
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
        context.visual_model_offered_rule_keys = visual_model_offered_rules or set()

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
        redaction_summary: dict | None = None,
    ) -> None:
        """Persist findings and counts-only redaction audit metadata atomically."""
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
            async with conn.transaction():
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
                if redaction_summary is not None:
                    # Counts and lengths only: never persist matched source values.
                    await conn.execute(
                        """
                        INSERT INTO public.audit_log
                            (org_id, actor_id, action, entity_type, entity_id, detail)
                        SELECT
                            org_id,
                            requested_by,
                            'review.redaction_applied',
                            'review',
                            id,
                            $2::jsonb
                        FROM public.reviews
                        WHERE id = $1
                        """,
                        uuid.UUID(review_id),
                        json.dumps(redaction_summary),
                    )
                    # The reverse map is no longer needed after findings are validated.
                    await conn.execute(
                        """
                        UPDATE review_previews
                        SET reverse_map_ciphertext='', payload='{}'::jsonb,
                            asset_manifest='[]'::jsonb
                        WHERE review_id=$1
                        """,
                        uuid.UUID(review_id),
                    )

    async def _persist_failure(
        self,
        review_id: str,
        error: str,
        claim_token: Optional[uuid.UUID] = None,
        preview_id: Optional[str] = None,
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
            if preview_id:
                await conn.execute(
                    """
                    UPDATE review_previews
                    SET reverse_map_ciphertext='', payload='{}'::jsonb,
                        asset_manifest='[]'::jsonb
                    WHERE id=$1
                    """,
                    uuid.UUID(preview_id),
                )

    async def run_pipeline(self, review_id: str) -> PipelineOutput:
        """Execute the complete review pipeline for a review."""
        start_time = time.time()
        claim_token: Optional[uuid.UUID] = None
        preview_id: Optional[str] = None

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
            preview_id = pipeline_input.preview_id

            # 3. Load rules and facts
            rules, facts = self.loader.load_rules_and_facts(pipeline_input.kit_id)
            if not pipeline_input.preview_id:
                raise RuntimeError("Review has no confirmed confidentiality preview")
            preview_record = await self._load_confirmed_preview(
                review_id, pipeline_input.preview_id
            )
            if not preview_record:
                raise RuntimeError("Confirmed review preview is missing or invalid")
            if (
                str(preview_record["org_id"]) != str(pipeline_input.org_id)
                or str(preview_record["revision_id"]) != str(pipeline_input.revision_id)
                or str(preview_record["kit_id"]) != str(pipeline_input.kit_id)
                or str(preview_record["user_id"]) != str(preview_record["review_requested_by"])
            ):
                raise RuntimeError("Confirmed review preview scope does not match the review")
            from app.confidentiality.preview import (
                decrypt_reverse_map, sha256_json, sha256_text, decode_jsonb,
                confidentiality_policy_sha256,
            )
            preview_payload = decode_jsonb(preview_record["payload"], {})
            preview_assets = decode_jsonb(preview_record["asset_manifest"], [])
            if preview_assets != (preview_payload.get("asset_manifest") or []):
                raise RuntimeError("Confirmed preview asset manifest integrity check failed")
            if preview_record["payload_sha256"] != sha256_json(preview_payload):
                raise RuntimeError("Confirmed review preview payload integrity check failed")
            if sha256_text(pipeline_input.revision_text) != preview_record["revision_sha256"]:
                raise RuntimeError("Revision changed after preview confirmation")

            # Stage 1 (Prepare): reuse the exact frozen, redacted inputs approved by the user.
            # Original values remain in pipeline_input/rules/facts for deterministic
            # checks and citation validation; only cloned prompt inputs are redacted.
            confidentiality_policy = await ConfidentialityPolicyStore(
                self.supabase
            ).load_policy(pipeline_input.org_id)
            if (
                confidentiality_policy.version != preview_record["policy_version"]
                or confidentiality_policy_sha256(confidentiality_policy) != preview_record["policy_sha256"]
            ):
                raise RuntimeError("Confidentiality policy changed after preview confirmation")
            redaction_fields = preview_payload["redacted_fields"]
            reverse_map = decrypt_reverse_map(preview_record["reverse_map_ciphertext"])
            redacted_rules = [
                RuleData(**item) for item in preview_payload["redacted_rules"]
            ]
            from datetime import date
            redacted_facts = [
                FactData(
                    fact_key=item["fact_key"],
                    statement=item["statement"],
                    source_note=item["source_note"],
                    valid_until=date.fromisoformat(item["valid_until"]) if item.get("valid_until") else None,
                )
                for item in preview_payload["redacted_facts"]
            ]
            redacted_revision_text = redaction_fields["draft_text"]
            redacted_purpose = redaction_fields["purpose"]
            redacted_channel = redaction_fields["channel"]
            redaction_summary = dict(decode_jsonb(preview_record["redaction_summary"], {}) or {})
            redaction_summary["asset_count"] = len(preview_payload.get("asset_manifest") or [])

            # 3b. Load visual assets associated with this revision.
            asset_ids = await self._load_visual_asset_ids(pipeline_input.revision_id, pipeline_input.org_id)

            # Load the current kit snapshot even when no images are attached; the
            # preview fingerprint binds all policy-bearing kit content.
            try:
                kit_response = await asyncio.to_thread(
                    lambda: self.supabase._get_client()
                    .table("brand_kits")
                    .select("version,visual_guidelines")
                    .eq("id", pipeline_input.kit_id)
                    .execute()
                )
            except Exception as exc:
                logger.error("visual_guidelines_load_failed", extra={"kit_id": pipeline_input.kit_id, "error_type": type(exc).__name__})
                raise RuntimeError("Failed to load brand kit snapshot for review") from exc
            if not kit_response.data:
                raise RuntimeError("Brand kit snapshot is unavailable")
            kit_snapshot = kit_response.data[0]
            visual_guidelines = kit_snapshot.get("visual_guidelines") or {}
            if not isinstance(visual_guidelines, dict):
                raise RuntimeError("Visual guidelines must be a JSON object")

            kit_fingerprint = {
                "kit_id": pipeline_input.kit_id,
                "version": kit_snapshot.get("version"),
                "rules": [__import__("dataclasses").asdict(item) for item in rules],
                "facts": [__import__("dataclasses").asdict(item) for item in facts],
                "visual_guidelines": visual_guidelines,
            }
            if sha256_json(kit_fingerprint) != preview_record["kit_sha256"]:
                raise RuntimeError("Brand kit changed after preview confirmation")

            provider_visual_guidelines = preview_payload.get("redacted_visual_guidelines") or {}
            if asset_ids:
                if preview_payload.get("vision_provider_request") is not None and not preview_record["image_consent_at"]:
                    raise RuntimeError("Original image consent was not recorded for this review")
                expected_manifest = preview_payload.get("asset_manifest") or []
                if {str(item["id"]) for item in expected_manifest} != {str(item) for item in asset_ids}:
                    raise RuntimeError("Visual asset set differs from the confirmed preview")

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
                    revision_text=redacted_revision_text,
                    purpose=redacted_purpose,
                    channel=redacted_channel,
                    visual_guidelines=visual_guidelines,
                    org_id=UUID(pipeline_input.org_id),
                    approved_logo_hashes=visual_guidelines.get("logo", {}).get("approved_hashes", []) if visual_guidelines else [],
                    provider_visual_guidelines=provider_visual_guidelines,
                    placeholder_map=reverse_map,
                    provider_request_override=(
                        ProviderRequest.model_validate(preview_payload["vision_provider_request"])
                        if preview_payload.get("vision_provider_request") else None
                    ),
                    expected_asset_checksums={
                        str(item["id"]): str(item["checksum"])
                        for item in (preview_payload.get("asset_manifest") or [])
                    },
                )

            # Visual findings are kept as-is (they have asset_id and region, not quote/offsets)
            # They will be passed directly to the validator which now handles visual candidates
            visual_deterministic_candidates = list(visual_result.deterministic_findings)

            # 6. Run text model analysis. Visual candidates stay in their own
            # typed collections and are passed separately to the shared validator.
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
                        redacted_revision_text,
                        redacted_rules,
                        redacted_facts,
                        redacted_purpose,
                        redacted_channel,
                        placeholder_map=reverse_map,
                        provider_request_override=ProviderRequest.model_validate(
                            preview_payload["text_provider_request"]
                        ),
                    )
                llm_findings_raw = len(text_model_candidates)
                warnings.extend(model_warnings)

                model_candidates = text_model_candidates

                # Combine warnings
                warnings.extend(visual_result.warnings)
            except (RateLimitedError, TimeoutError, UnavailableError, BadOutputError, BlockedError, ProviderError) as e:
                llm_status = "failed"
                logger.warning(
                    "llm_failed_fallback_to_deterministic",
                    extra={"review_id": review_id, "error_type": type(e).__name__},
                )
                warnings.append(f"model unavailable: deterministic checks only ({type(e).__name__})")
                # Visual analysis ran independently; preserve its valid findings.
                model_candidates = []
                warnings.extend(visual_result.warnings)
            except Exception as e:
                llm_status = "failed"
                logger.error(
                    "unexpected_llm_error",
                    extra={"review_id": review_id, "error_type": type(e).__name__},
                )
                warnings.append(f"model error: deterministic checks only")
                model_candidates = []
                warnings.extend(visual_result.warnings)

            # Count text and visual model output once, despite separate validation paths.
            llm_findings_raw = len(model_candidates) + len(visual_result.model_findings)

            # 7. Run validation
            validation_result = await self._run_validation(
                pipeline_input.revision_text,
                pipeline_input.kit_id,
                deterministic_candidates,
                model_candidates,
                rules,
                facts,
                model_offered_rules=set([r.rule_key for r in rules if r.check_kind == "llm"]),
                model_offered_facts=model_offered_facts,
                visual_deterministic_candidates=visual_deterministic_candidates,
                visual_model_candidates=visual_result.model_findings,
                visual_model_offered_rules=get_visual_guideline_ref_keys(visual_guidelines),
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
                redaction_summary=redaction_summary,
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
            logger.error(
                "pipeline_failed",
                extra={"review_id": review_id, "elapsed_ms": int((time.time() - start_time) * 1000), "error_type": type(e).__name__},
            )

            # Try to persist failure with claim_token for fencing
            try:
                safe_error = f"Review processing failed ({type(e).__name__})"
                await self._persist_failure(review_id, safe_error, claim_token, preview_id)
            except Exception:
                logger.error("failed_to_persist_failure", extra={"review_id": review_id})

            return PipelineOutput(
                validated_findings=[],
                llm_status="failed",
                warnings=[f"Pipeline error: {type(e).__name__}"],
                llm_findings_raw=0,
                llm_findings_dropped=0,
                validator_stats={},
                model=None,
                prompt_version=None,
                error=f"Review processing failed ({type(e).__name__})",
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

