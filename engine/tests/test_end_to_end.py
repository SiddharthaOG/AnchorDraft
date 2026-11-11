"""End-to-end and failure-path tests for the review engine.

This module tests the complete review pipeline behavior including:
- Provider fallback and failure classification
- Citation and finding integrity
- Persistence and claim ownership
- Recovery behavior
- API integration

Full pipeline orchestration tests require a real database and are covered
by integration tests in test_pipeline_orchestrator.py.
"""

import json
import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.pipeline.orchestrator import ReviewOrchestrator, PipelineInput
from app.llm import (
    FakeProvider,
    FakeProviderConfig,
    ProviderWithFallback,
    get_provider_with_fallback,
    create_rate_limited_failure,
    create_timeout_failure,
    create_unavailable_failure,
    create_bad_output_failure,
    create_blocked_failure,
)
from app.llm.provider_factory import ProviderSettings, ProviderType
from app.models.pipeline import (
    ProviderRequest,
    ProviderResult,
    ModelFindingCandidate,
    DeterministicFindingCandidate,
    ValidatedFinding,
    AggregateValidationResult,
    RateLimitedError,
    TimeoutError,
    UnavailableError,
    BadOutputError,
    BlockedError,
    ProviderError,
)
from app.llm.prompt_builder import (
    build_provider_request,
    PromptInput,
    RuleData,
    FactData,
    filter_rules_for_model,
    filter_valid_facts,
    render_rules_block,
    render_facts_block,
)
from app.validator import run_citation_validator, ValidationContext, RuleRecord, FactRecord
from app.checks import run_deterministic_checks, TermMapCheck, PhraseListCheck
from app.checks.deterministic import RuleConfig


# ============================================================================
# Test Fixtures and Helpers
# ============================================================================

def make_rule_data(
    rule_key: str = "TERM-01",
    category: str = "terminology",
    severity: str = "medium",
    title: str = "Test Rule",
    guideline_text: str = "Test guideline",
    check_kind: str = "llm",
    needs_reviewer: bool = False,
) -> RuleData:
    return RuleData(
        rule_key=rule_key,
        category=category,
        severity=severity,
        title=title,
        guideline_text=guideline_text,
        check_kind=check_kind,
        needs_reviewer=needs_reviewer,
    )


def make_fact_data(
    fact_key: str = "FACT-01",
    statement: str = "Test fact",
    source_note: str = "Test source",
    valid_until = None,
) -> FactData:
    return FactData(
        fact_key=fact_key,
        statement=statement,
        source_note=source_note,
        valid_until=valid_until,
    )


def make_det_candidate(
    ref_key: str = "TERM-01",
    quote: str = "utilize",
    explanation: str = "Avoid using utilize",
    suggestion: str = "use",
    start_offset: int = 10,
    end_offset: int = 17,
    rule_category: str = "terminology",
    severity: str = "low",
    needs_reviewer: bool = False,
    confidence: float = None,
) -> DeterministicFindingCandidate:
    return DeterministicFindingCandidate(
        ref_key=ref_key,
        quote=quote,
        start_offset=start_offset,
        end_offset=end_offset,
        explanation=explanation,
        suggestion=suggestion,
        rule_category=rule_category,
        severity=severity,
        needs_reviewer=needs_reviewer,
        confidence=confidence,
    )


def make_model_candidate(
    ref_key: str = "TERM-01",
    issue: str = "violation",
    quote: str = "utilize",
    explanation: str = "Avoid using utilize",
    suggestion: str = "use",
    confidence: float = 0.9,
) -> ModelFindingCandidate:
    return ModelFindingCandidate(
        ref_key=ref_key,
        issue=issue,
        quote=quote,
        explanation=explanation,
        suggestion=suggestion,
        confidence=confidence,
    )


def make_valid_finding(
    source: str = "deterministic",
    ref_key: str = "TERM-01",
    category: str = "terminology",
    severity: str = "low",
    quote: str = "utilize",
    start_offset: int = 10,
    end_offset: int = 17,
    explanation: str = "Avoid using utilize",
    suggestion: str = "use",
    confidence: float = 0.9,
    needs_human: bool = False,
    needs_reviewer: bool = False,
) -> ValidatedFinding:
    return ValidatedFinding(
        source=source,
        ref_key=ref_key,
        category=category,
        severity=severity,
        quote=quote,
        start_offset=start_offset,
        end_offset=end_offset,
        explanation=explanation,
        suggestion=suggestion,
        confidence=confidence,
        needs_human=needs_human,
        needs_reviewer=needs_reviewer,
    )



def configure_confirmed_preview(orchestrator, pipeline_input, rules, facts):
    """Build a consistent frozen-preview fixture for pipeline tests."""
    from dataclasses import asdict
    from app.confidentiality.preview import sha256_json, sha256_text
    from app.confidentiality.preview import confidentiality_policy_sha256
    from app.confidentiality.models import ConfidentialityPolicy
    from app.models.pipeline import ProviderRequest
    from unittest.mock import AsyncMock, MagicMock
    import uuid

    pipeline_input.preview_id = str(uuid.uuid4())
    redacted_rules = [asdict(item) for item in rules]
    redacted_facts = [
        {**asdict(item), "valid_until": item.valid_until.isoformat() if item.valid_until else None}
        for item in facts
    ]
    payload = {
        "text_provider_request": ProviderRequest(
            system_instruction="system", user_content="redacted request",
            output_schema={}, randomness=0.1, output_limit=100, timeout_seconds=1,
        ).model_dump(mode="json"),
        "vision_provider_request": None,
        "redacted_fields": {
            "draft_text": pipeline_input.revision_text,
            "purpose": pipeline_input.purpose,
            "channel": pipeline_input.channel,
        },
        "redacted_rules": redacted_rules,
        "redacted_facts": redacted_facts,
        "asset_manifest": [],
        "redacted_visual_guidelines": {},
        "has_visual_provider_request": False,
    }
    fingerprint = {
        "kit_id": str(pipeline_input.kit_id), "version": 1,
        "rules": redacted_rules, "facts": redacted_facts, "visual_guidelines": {},
    }
    record = {
        "org_id": str(pipeline_input.org_id),
        "user_id": str(uuid.uuid4()),
        "review_requested_by": None,
        "revision_id": str(pipeline_input.revision_id),
        "kit_id": str(pipeline_input.kit_id),
        "payload": payload,
        "asset_manifest": [],
        "payload_sha256": sha256_json(payload),
        "revision_sha256": sha256_text(pipeline_input.revision_text),
        "kit_sha256": sha256_json(fingerprint),
        "policy_version": 1,
        "policy_sha256": confidentiality_policy_sha256(
            ConfidentialityPolicy(org_id=UUID(str(pipeline_input.org_id)))
        ),
        "reverse_map_ciphertext": "test-encrypted-map",
        "redaction_summary": {
            "total_matches": 0, "by_type": {},
            "original_chars": len(pipeline_input.revision_text),
            "redacted_chars": len(pipeline_input.revision_text),
            "policy_version": 1,
        },
        "image_consent_at": None,
    }
    record["review_requested_by"] = record["user_id"]
    orchestrator._load_confirmed_preview = AsyncMock(return_value=record)
    orchestrator._load_visual_asset_ids = AsyncMock(return_value=[])
    fake_client = MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"version": 1, "visual_guidelines": {}}
    ]
    orchestrator.supabase._get_client = MagicMock(return_value=fake_client)


# ============================================================================
# C. Provider Fallback and Failure Classification Tests
# ============================================================================

class TestProviderFallbackAndFailureClassification:
    """Tests for provider fallback and failure classification."""

    @pytest.mark.asyncio
    async def test_primary_provider_success(self):
        """Test primary provider success path."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="primary-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(ProviderRequest(
            system_instruction="test",
            user_content="test",
            output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        ))
        
        assert result.model == "primary-model"
        primary.generate_findings.assert_called_once()
        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_on_rate_limited(self):
        """Test fallback on RateLimitedError."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=RateLimitedError("Rate limited"))
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="fallback-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(ProviderRequest(
            system_instruction="test",
            user_content="test",
            output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        ))
        
        assert result.model == "fallback-model"
        primary.generate_findings.assert_called_once()
        fallback.generate_findings.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(self):
        """Test fallback on TimeoutError."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=TimeoutError("Timeout"))
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="fallback-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(ProviderRequest(
            system_instruction="test",
            user_content="test",
            output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        ))
        
        assert result.model == "fallback-model"
        fallback.generate_findings.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_unavailable(self):
        """Test fallback on UnavailableError."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=UnavailableError("Unavailable"))
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="fallback-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(ProviderRequest(
            system_instruction="test",
            user_content="test",
            output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        ))
        
        assert result.model == "fallback-model"
        fallback.generate_findings.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_fallback_on_blocked(self):
        """Test that BlockedError does NOT trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=BlockedError("Safety block"))
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="fallback-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        
        with pytest.raises(BlockedError):
            await wrapper.generate_findings(ProviderRequest(
                system_instruction="test",
                user_content="test",
                output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
                randomness=0.1,
                output_limit=4096,
                timeout_seconds=45,
            ))
        
        primary.generate_findings.assert_called_once()
        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_fallback_on_bad_output(self):
        """Test that BadOutputError does NOT trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=BadOutputError("Bad JSON"))
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="fallback-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        
        with pytest.raises(BadOutputError):
            await wrapper.generate_findings(ProviderRequest(
                system_instruction="test",
                user_content="test",
                output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
                randomness=0.1,
                output_limit=4096,
                timeout_seconds=45,
            ))
        
        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_fallback_on_config_error(self):
        """Test that config errors do not trigger fallback."""
        from app.llm.provider_factory import ProviderConfigError
        
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=ProviderConfigError("Config error"))
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="fallback-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        
        with pytest.raises(ProviderConfigError):
            await wrapper.generate_findings(ProviderRequest(
                system_instruction="test",
                user_content="test",
                output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
                randomness=0.1,
                output_limit=4096,
                timeout_seconds=45,
            ))
        
        fallback.generate_findings.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_fail_raises_combined_error(self):
        """Test that both failing raises combined error."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=RateLimitedError("Rate limited"))
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(side_effect=UnavailableError("Unavailable"))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        
        with pytest.raises(ProviderError, match="Both providers failed"):
            await wrapper.generate_findings(ProviderRequest(
                system_instruction="test",
                user_content="test",
                output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
                randomness=0.1,
                output_limit=4096,
                timeout_seconds=45,
            ))

    @pytest.mark.asyncio
    async def test_no_fallback_available_raises_original(self):
        """Test that primary error is raised when no fallback available."""
        primary = MagicMock()
        primary.model = "primary-model"
        primary.generate_findings = AsyncMock(side_effect=RateLimitedError("Rate limited"))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=None)
        
        with pytest.raises(RateLimitedError):
            await wrapper.generate_findings(ProviderRequest(
                system_instruction="test",
                user_content="test",
                output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
                randomness=0.1,
                output_limit=4096,
                timeout_seconds=45,
            ))

    @pytest.mark.asyncio
    async def test_fallback_on_provider_error_with_retry_after(self):
        """Test fallback on generic ProviderError with retry_after."""
        primary = MagicMock()
        primary.model = "primary-model"
        error = ProviderError("Rate limited")
        error.retry_after = 30
        primary.generate_findings = AsyncMock(side_effect=error)
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="fallback-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        result = await wrapper.generate_findings(ProviderRequest(
            system_instruction="test",
            user_content="test",
            output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=45,
        ))
        
        assert result.model == "fallback-model"
        fallback.generate_findings.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_fallback_on_generic_provider_error_transient_message(self):
        """Test that generic ProviderError with transient message does NOT trigger fallback."""
        primary = MagicMock()
        primary.model = "primary-model"
        error = ProviderError("Connection timeout")
        primary.generate_findings = AsyncMock(side_effect=error)
        
        fallback = MagicMock()
        fallback.model = "fallback-model"
        fallback.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json='{"findings": []}',
            input_tokens=100,
            output_tokens=50,
            model="fallback-model",
            latency_ms=100,
            finish_reason="stop",
        ))
        
        wrapper = ProviderWithFallback(primary=primary, fallback=fallback)
        
        with pytest.raises(ProviderError, match="Connection timeout"):
            await wrapper.generate_findings(ProviderRequest(
                system_instruction="test",
                user_content="test",
                output_schema={"type": "object", "properties": {"findings": {"type": "array"}}, "required": ["findings"]},
                randomness=0.1,
                output_limit=4096,
                timeout_seconds=45,
            ))
        
        fallback.generate_findings.assert_not_called()


# ============================================================================
# D. Citation and Finding Integrity Tests
# ============================================================================

class TestCitationAndFindingIntegrity:
    """Tests for citation integrity through the shared validator."""

    def test_reference_exists_and_offered_to_model(self):
        """Test that references must exist and be offered to the model."""
        candidate = ModelFindingCandidate(
            ref_key="UNKNOWN-01",
            issue="violation",
            quote="test",
            explanation="Test",
            confidence=0.9,
        )
        context = ValidationContext(
            all_rules=[RuleRecord(rule_key="TERM-01", category="terminology", severity="medium",
                                  needs_reviewer=False, check_kind="llm")],
            all_facts=[],
            model_offered_rule_keys={"TERM-01"},
            model_offered_fact_keys=set(),
        )
        result = run_citation_validator("text", [], [candidate], context)
        
        assert result.dropped_counts.get("unknown_ref", 0) == 1
        assert len(result.validated_findings) == 0

    def test_reference_fits_issue_type(self):
        """Test that reference type matches issue type."""
        candidate = ModelFindingCandidate(
            ref_key="FACT-01",
            issue="violation",
            quote="test",
            explanation="Test",
            confidence=0.9,
        )
        context = ValidationContext(
            all_rules=[],
            all_facts=[FactRecord(fact_key="FACT-01", statement="Test fact", valid_until=None)],
            model_offered_rule_keys=set(),
            model_offered_fact_keys={"FACT-01"},
        )
        result = run_citation_validator("text", [], [candidate], context)
        
        assert result.dropped_counts.get("ref_mismatch", 0) == 1

    def test_quote_actually_occurs_in_draft(self):
        """Test that quotes must actually occur in the draft."""
        candidate = ModelFindingCandidate(
            ref_key="TERM-01",
            issue="violation",
            quote="nonexistent",
            explanation="Test",
            confidence=0.9,
        )
        context = ValidationContext(
            all_rules=[RuleRecord(rule_key="TERM-01", category="terminology", severity="medium",
                                  needs_reviewer=False, check_kind="llm")],
            all_facts=[],
            model_offered_rule_keys={"TERM-01"},
            model_offered_fact_keys=set(),
        )
        result = run_citation_validator("We should use this.", [], [candidate], context)
        
        assert result.dropped_counts.get("quote_not_found", 0) == 1

    def test_offsets_computed_server_side(self):
        """Test that offsets are computed server-side and match quote."""
        candidate = DeterministicFindingCandidate(
            ref_key="TERM-01",
            quote="utilize",
            start_offset=10,
            end_offset=17,
            explanation="Avoid using utilize",
            suggestion="use",
            rule_category="terminology",
            severity="medium",
        )
        context = ValidationContext(
            all_rules=[RuleRecord(rule_key="TERM-01", category="terminology", severity="medium",
                                  needs_reviewer=False, check_kind="deterministic")],
            all_facts=[],
            model_offered_rule_keys=set(),
            model_offered_fact_keys=set(),
        )
        text = "We should utilize this feature."
        result = run_citation_validator(text, [candidate], [], context)
        
        assert len(result.validated_findings) == 1
        finding = result.validated_findings[0]
        assert finding.quote == "utilize"
        assert text[finding.start_offset:finding.end_offset] == "utilize"

    def test_invalid_candidates_dropped(self):
        """Test that invalid candidates are dropped with correct reason."""
        candidates = [
            ModelFindingCandidate(ref_key="UNKNOWN", issue="violation", quote="test",
                                  explanation="Test", confidence=0.9),
            ModelFindingCandidate(ref_key="TERM-01", issue="violation", quote="nonexistent",
                                  explanation="Test", confidence=0.9),
        ]
        context = ValidationContext(
            all_rules=[RuleRecord(rule_key="TERM-01", category="terminology", severity="medium",
                                  needs_reviewer=False, check_kind="llm")],
            all_facts=[],
            model_offered_rule_keys={"TERM-01"},
            model_offered_fact_keys=set(),
        )
        result = run_citation_validator("text", [], candidates, context)
        
        assert result.dropped_counts.get("unknown_ref", 0) == 1
        assert result.dropped_counts.get("quote_not_found", 0) == 1
        assert len(result.validated_findings) == 0

    def test_duplicate_findings_handled_correctly(self):
        """Test that duplicate findings are handled correctly."""
        det1 = DeterministicFindingCandidate(
            ref_key="TERM-01", quote="utilize", start_offset=10, end_offset=17,
            explanation="Test", suggestion="use", rule_category="terminology", severity="medium"
        )
        det2 = DeterministicFindingCandidate(
            ref_key="TERM-01", quote="utilize", start_offset=10, end_offset=17,
            explanation="Test", suggestion="use", rule_category="terminology", severity="medium"
        )
        context = ValidationContext(
            all_rules=[RuleRecord(rule_key="TERM-01", category="terminology", severity="medium",
                                  needs_reviewer=False, check_kind="deterministic")],
            all_facts=[],
            model_offered_rule_keys=set(),
            model_offered_fact_keys=set(),
        )
        text = "We should utilize this."
        result = run_citation_validator(text, [det1, det2], [], context)
        
        assert len(result.validated_findings) == 1
        assert result.dropped_counts.get("duplicate", 0) == 1

    def test_finding_cap_respected(self):
        """Test that finding cap of 25 is respected."""
        rules = [RuleRecord(rule_key=f"TERM-{i:02d}", category="terminology", severity="medium",
                            needs_reviewer=False, check_kind="deterministic") for i in range(30)]
        candidates = [
            DeterministicFindingCandidate(
                ref_key=f"TERM-{i:02d}", quote=f"term{i}", start_offset=i*10, end_offset=i*10+5,
                explanation="Test", suggestion="use", rule_category="terminology", severity="medium"
            ) for i in range(30)
        ]
        context = ValidationContext(
            all_rules=rules,
            all_facts=[],
            model_offered_rule_keys=set(),
            model_offered_fact_keys=set(),
        )
        text = " ".join([f"term{i}" for i in range(30)])
        result = run_citation_validator(text, candidates, [], context)
        
        assert len(result.validated_findings) == 25
        assert result.dropped_counts.get("too_many", 0) == 5

    def test_rule_fact_metadata_preserved(self):
        """Test that rule/fact metadata and reviewer requirements are preserved."""
        candidate = DeterministicFindingCandidate(
            ref_key="TERM-01", quote="test", start_offset=0, end_offset=4,
            explanation="Test", suggestion="use", rule_category="terminology", severity="high",
            needs_reviewer=True,
        )
        context = ValidationContext(
            all_rules=[RuleRecord(rule_key="TERM-01", category="terminology", severity="high",
                                  needs_reviewer=True, check_kind="deterministic")],
            all_facts=[],
            model_offered_rule_keys=set(),
            model_offered_fact_keys=set(),
        )
        result = run_citation_validator("test", [candidate], [], context)
        
        assert len(result.validated_findings) == 1
        finding = result.validated_findings[0]
        assert finding.category == "terminology"
        assert finding.severity == "high"
        assert finding.needs_reviewer is True

    def test_fact_reference_gets_needs_reviewer(self):
        """Test that fact references get needs_reviewer=True."""
        candidate = ModelFindingCandidate(
            ref_key="FACT-01", issue="contradicts_fact", quote="test",
            explanation="Contradicts fact", confidence=0.9,
        )
        context = ValidationContext(
            all_rules=[],
            all_facts=[FactRecord(fact_key="FACT-01", statement="Test fact", valid_until=None)],
            model_offered_rule_keys=set(),
            model_offered_fact_keys={"FACT-01"},
        )
        result = run_citation_validator("test", [], [candidate], context)
        
        assert len(result.validated_findings) == 1
        finding = result.validated_findings[0]
        assert finding.category == "fact"
        assert finding.severity == "medium"
        assert finding.needs_reviewer is True

    def test_deterministic_processed_before_model(self):
        """Test that deterministic candidates are processed before model candidates."""
        det = DeterministicFindingCandidate(
            ref_key="TERM-01", quote="utilize", start_offset=10, end_offset=17,
            explanation="Test", suggestion="use", rule_category="terminology", severity="medium"
        )
        model = ModelFindingCandidate(
            ref_key="TERM-01", issue="violation", quote="utilize",
            explanation="Test", confidence=0.9,
        )
        context = ValidationContext(
            all_rules=[RuleRecord(rule_key="TERM-01", category="terminology", severity="medium",
                                  needs_reviewer=False, check_kind="llm")],
            all_facts=[],
            model_offered_rule_keys={"TERM-01"},
            model_offered_fact_keys=set(),
        )
        text = "We should utilize this."
        result = run_citation_validator(text, [det], [model], context)
        
        # Deterministic should be kept, model should be dropped as duplicate
        assert len(result.validated_findings) == 1
        assert result.validated_findings[0].source == "deterministic"
        assert result.dropped_counts.get("duplicate", 0) == 1


# ============================================================================
# E. Persistence and Claim Ownership Tests
# ============================================================================

class TestPersistenceAndClaimOwnership:
    """Tests for persistence payloads and claim-token propagation."""

    @pytest.mark.asyncio
    async def test_successful_completion_persists_with_claim_token(self):
        """Test that successful completion persists review with claim token."""
        from app.pipeline.orchestrator import ReviewOrchestrator
        
        review_id = str(uuid4())
        claim_token = uuid4()
        
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        orchestrator = ReviewOrchestrator()
        orchestrator._get_db_pool = AsyncMock(return_value=mock_pool)
        
        validation_result = AggregateValidationResult(
            validated_findings=[
                ValidatedFinding(
                    source="deterministic",
                    ref_key="TERM-01",
                    category="terminology",
                    severity="medium",
                    quote="utilize",
                    start_offset=10,
                    end_offset=17,
                    explanation="Avoid using utilize",
                    suggestion="use",
                    confidence=None,
                    needs_human=False,
                    needs_reviewer=False,
                )
            ],
            kept_count=1,
            raw_candidate_count=1,
            dropped_counts={},
        )
        
        await orchestrator._persist_results(
            review_id=review_id,
            validation_result=validation_result,
            llm_status="ok",
            warnings=[],
            llm_findings_raw=0,
            llm_findings_dropped=0,
            validator_stats={"raw": 1, "kept": 1, "dropped": {}},
            model="fake-model",
            prompt_version="p1",
            claim_token=claim_token,
        )
        
        # Verify execute was called with correct SQL and claim_token
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "engine_complete_review" in call_args[0][0]
        # Parameters: query, review_id, status, llm_status, warnings, llm_findings_raw, 
        # llm_findings_dropped, validator_stats, model, prompt_version, findings_json, claim_token
        assert call_args[0][11] == claim_token

    @pytest.mark.asyncio
    async def test_failure_persistence_uses_failure_rpc(self):
        """Test that failure persistence uses the failure RPC with claim token."""
        from app.pipeline.orchestrator import ReviewOrchestrator
        
        review_id = str(uuid4())
        claim_token = uuid4()
        error = "Pipeline error"
        
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        orchestrator = ReviewOrchestrator()
        orchestrator._get_db_pool = AsyncMock(return_value=mock_pool)
        
        await orchestrator._persist_failure(review_id, error, claim_token)
        
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "engine_fail_review" in call_args[0][0]
        assert call_args[0][3] == claim_token

    @pytest.mark.asyncio
    async def test_active_claim_token_propagated_on_success(self):
        """Test that active claim token is propagated to completion RPC."""
        from app.pipeline.orchestrator import ReviewOrchestrator
        
        review_id = str(uuid4())
        claim_token = uuid4()
        
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        orchestrator = ReviewOrchestrator()
        orchestrator._get_db_pool = AsyncMock(return_value=mock_pool)
        
        validation_result = AggregateValidationResult(
            validated_findings=[],
            kept_count=0,
            raw_candidate_count=0,
            dropped_counts={},
        )
        
        await orchestrator._persist_results(
            review_id=review_id,
            validation_result=validation_result,
            llm_status="ok",
            warnings=[],
            llm_findings_raw=0,
            llm_findings_dropped=0,
            validator_stats={},
            model="fake-model",
            prompt_version="p1",
            claim_token=claim_token,
        )
        
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][11] == claim_token

    @pytest.mark.asyncio
    async def test_null_claim_token_rejected_on_complete(self):
        """Test that NULL claim token is rejected on completion."""
        from app.pipeline.orchestrator import ReviewOrchestrator
        
        review_id = str(uuid4())
        
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("claim_token_required"))
        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        orchestrator = ReviewOrchestrator()
        orchestrator._get_db_pool = AsyncMock(return_value=mock_pool)
        
        validation_result = AggregateValidationResult(
            validated_findings=[],
            kept_count=0,
            raw_candidate_count=0,
            dropped_counts={},
        )
        
        with pytest.raises(Exception) as exc_info:
            await orchestrator._persist_results(
                review_id=review_id,
                validation_result=validation_result,
                llm_status="ok",
                warnings=[],
                llm_findings_raw=0,
                llm_findings_dropped=0,
                validator_stats={},
                model="fake-model",
                prompt_version="p1",
                claim_token=None,  # NULL token
            )
        
        assert "claim_token" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_mismatched_claim_token_rejected(self):
        """Test that mismatched claim token is rejected."""
        from app.pipeline.orchestrator import ReviewOrchestrator
        
        review_id = str(uuid4())
        original_token = uuid4()
        different_token = uuid4()
        
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("claim_token_mismatch"))
        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        orchestrator = ReviewOrchestrator()
        orchestrator._get_db_pool = AsyncMock(return_value=mock_pool)
        
        validation_result = AggregateValidationResult(
            validated_findings=[],
            kept_count=0,
            raw_candidate_count=0,
            dropped_counts={},
        )
        
        with pytest.raises(Exception) as exc_info:
            await orchestrator._persist_results(
                review_id=review_id,
                validation_result=validation_result,
                llm_status="ok",
                warnings=[],
                llm_findings_raw=0,
                llm_findings_dropped=0,
                validator_stats={},
                model="fake-model",
                prompt_version="p1",
                claim_token=different_token,  # Different token
            )
        
        assert "claim_token_mismatch" in str(exc_info.value) or "claim_token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stale_worker_cannot_overwrite_newer_claim(self):
        """Test that a stale worker cannot overwrite a newer claim."""
        from engine.app.pipeline.orchestrator import ReviewOrchestrator
        
        review_id = str(uuid4())
        
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("claim_token_mismatch"))
        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        orchestrator = ReviewOrchestrator()
        orchestrator._get_db_pool = AsyncMock(return_value=mock_pool)
        
        token1 = uuid4()  # Worker A's token
        token2 = uuid4()  # Worker B's token (different)
        
        validation_result = AggregateValidationResult(
            validated_findings=[],
            kept_count=0,
            raw_candidate_count=0,
            dropped_counts={},
        )
        
        with pytest.raises(Exception) as exc_info:
            await orchestrator._persist_results(
                review_id=review_id,
                validation_result=validation_result,
                llm_status="ok",
                warnings=[],
                llm_findings_raw=0,
                llm_findings_dropped=0,
                validator_stats={},
                model="fake-model",
                prompt_version="p1",
                claim_token=token1,  # Old token
            )
        
        assert "claim_token_mismatch" in str(exc_info.value) or "claim_token" in str(exc_info.value)


# ============================================================================
# F. Recovery Behavior Tests
# ============================================================================

class TestRecoveryBehavior:
    """Tests for stale job recovery and stale-worker fencing."""

    @pytest.mark.asyncio
    async def test_stale_reviews_eligible_for_reclamation(self):
        """Test that stale running reviews are eligible for reclamation."""
        from app.pipeline.orchestrator import reclaim_stale_reviews
        
        mock_conn = MagicMock()
        mock_conn.fetchval = AsyncMock(return_value=3)
        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        with patch('app.pipeline.orchestrator.get_db_pool', return_value=mock_pool):
            reclaimed = await reclaim_stale_reviews(lease_minutes=30)
            assert reclaimed == 3
            mock_conn.fetchval.assert_called_once_with("SELECT reclaim_stale_reviews($1)", 30)

    @pytest.mark.asyncio
    async def test_lease_period_configuration(self):
        """Test that lease period is configurable (default 30 minutes)."""
        from app.pipeline.orchestrator import reclaim_stale_reviews
        
        mock_conn = MagicMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        
        with patch('app.pipeline.orchestrator.get_db_pool', return_value=mock_pool):
            # Default lease (30 minutes)
            await reclaim_stale_reviews()
            mock_conn.fetchval.assert_called_with("SELECT reclaim_stale_reviews($1)", 30)
            
            # Custom lease
            await reclaim_stale_reviews(lease_minutes=60)
            mock_conn.fetchval.assert_called_with("SELECT reclaim_stale_reviews($1)", 60)


# ============================================================================
# G. API Integration Tests (review-start endpoint)
# ============================================================================

class TestAPIIntegration:
    """Tests for the review-start endpoint and pipeline handoff."""

    @pytest.mark.asyncio
    async def test_idempotency_existing_queued_review(self):
        from app.api.reviews import start_review
        from app.auth.dependencies import AuthUser
        from app.models.api import ReviewStartRequest
        from fastapi import BackgroundTasks, HTTPException, Request
        from uuid import uuid4
        import pytest

        user = AuthUser(user_id=str(uuid4()), org_id=str(uuid4()), roles=["creator"])
        with pytest.raises(HTTPException) as exc:
            await start_review(
                background_tasks=BackgroundTasks(),
                request=MagicMock(spec=Request),
                payload=ReviewStartRequest(revision_id=uuid4()),
                user=user,
                request_id="test",
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "preview_required"

    async def test_idempotency_existing_running_review(self):
        from app.api.reviews import start_review
        from app.auth.dependencies import AuthUser
        from app.models.api import ReviewStartRequest
        from fastapi import BackgroundTasks, HTTPException, Request
        from uuid import uuid4
        import pytest

        user = AuthUser(user_id=str(uuid4()), org_id=str(uuid4()), roles=["creator"])
        with pytest.raises(HTTPException) as exc:
            await start_review(
                background_tasks=BackgroundTasks(),
                request=MagicMock(spec=Request),
                payload=ReviewStartRequest(revision_id=uuid4()),
                user=user,
                request_id="test",
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "preview_required"

    async def test_idempotency_existing_completed_review(self):
        from app.api.reviews import start_review
        from app.auth.dependencies import AuthUser
        from app.models.api import ReviewStartRequest
        from fastapi import BackgroundTasks, HTTPException, Request
        from uuid import uuid4
        import pytest

        user = AuthUser(user_id=str(uuid4()), org_id=str(uuid4()), roles=["creator"])
        with pytest.raises(HTTPException) as exc:
            await start_review(
                background_tasks=BackgroundTasks(),
                request=MagicMock(spec=Request),
                payload=ReviewStartRequest(revision_id=uuid4()),
                user=user,
                request_id="test",
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "preview_required"

class TestFullPipelineOrchestration:
    """Tests for Python review pipeline orchestration using mocked stages.

    The orchestration test verifies stage sequencing, result propagation,
    and claim-token handling. Internal deterministic checks, model analysis,
    validation, and persistence are mocked in this test.

    The underlying components have separate unit tests. This test does not
    claim to exercise the complete review engine end-to-end.
    """

    @pytest.mark.asyncio
    async def test_orchestrator_sequences_stages_and_propagates_claim_token(self):
        """Verify orchestration sequencing and claim-token propagation.

        This test verifies that ReviewOrchestrator.run_pipeline() coordinates
        the mocked pipeline stages, propagates their results, and passes claim
        ownership information to the persistence boundary.

        It does not independently test the implementations of the deterministic
        checker, model/provider analysis, citation validator, or persistence RPC.
        """
        from app.pipeline.orchestrator import ReviewOrchestrator, PipelineInput
        from app.llm.prompt_builder import PromptInput
        from app.llm.token_budget import TokenBudgetExceededError
        from app.checks.deterministic import DeterministicCheckResult, SkippedCheck
        from app.models.pipeline import ModelFindingCandidate
        from app.validator import AggregateValidationResult

        review_id = str(uuid4())
        revision_id = str(uuid4())
        kit_id = str(uuid4())
        org_id = str(uuid4())
        claim_token = uuid4()

        # --- Realistic revision text with violations ---
        revision_text = (
            "We should utilize this feature for better leverage. "
            "The product is 100% secure and guaranteed to work."
        )

        # --- Mock SupabaseDataLoader (data loading) ---
        mock_loader = MagicMock()
        mock_loader.load_review_input.return_value = PipelineInput(
            review_id=review_id,
            revision_id=revision_id,
            revision_text=revision_text,
            kit_id=kit_id,
            org_id=org_id,
            purpose="Marketing blog post",
            channel="blog",
            engine_version="0.1.0",
            preview_id=str(uuid4()),
        )
        # Rules: 2 deterministic (TERM-01, TERM-02), 2 LLM (CLAIM-01, TONE-01)
        mock_loader.load_rules_and_facts.return_value = (
            [
                RuleData(
                    rule_key="TERM-01",
                    category="terminology",
                    severity="medium",
                    title="Avoid utilize",
                    guideline_text="Use 'use' instead of 'utilize'",
                    check_kind="deterministic",
                    needs_reviewer=False,
                ),
                RuleData(
                    rule_key="TERM-02",
                    category="terminology",
                    severity="medium",
                    title="Avoid leverage",
                    guideline_text="Use 'use' instead of 'leverage'",
                    check_kind="deterministic",
                    needs_reviewer=False,
                ),
                RuleData(
                    rule_key="CLAIM-01",
                    category="claim",
                    severity="high",
                    title="Substantiate security claims",
                    guideline_text="All security claims must be substantiated by approved facts",
                    check_kind="llm",
                    needs_reviewer=True,
                ),
                RuleData(
                    rule_key="TONE-01",
                    category="tone",
                    severity="low",
                    title="Professional tone",
                    guideline_text="Avoid absolute guarantees",
                    check_kind="llm",
                    needs_reviewer=False,
                ),
            ],
            # Facts
            [
                FactData(
                    fact_key="FACT-01",
                    statement="Our product achieves 99.9% uptime per SLA",
                    source_note="SLA documentation v2.1",
                    valid_until=None,
                ),
            ],
        )
        mock_loader.load_validation_context.return_value = ValidationContext(
            all_rules=[
                RuleRecord(
                    rule_key="TERM-01",
                    category="terminology",
                    severity="medium",
                    needs_reviewer=False,
                    check_kind="deterministic",
                ),
                RuleRecord(
                    rule_key="TERM-02",
                    category="terminology",
                    severity="medium",
                    needs_reviewer=False,
                    check_kind="deterministic",
                ),
                RuleRecord(
                    rule_key="CLAIM-01",
                    category="claim",
                    severity="high",
                    needs_reviewer=True,
                    check_kind="llm",
                ),
                RuleRecord(
                    rule_key="TONE-01",
                    category="tone",
                    severity="low",
                    needs_reviewer=False,
                    check_kind="llm",
                ),
            ],
            all_facts=[
                FactRecord(
                    fact_key="FACT-01",
                    statement="Our product achieves 99.9% uptime per SLA",
                    valid_until=None,
                ),
            ],
            model_offered_rule_keys={"CLAIM-01", "TONE-01"},
            model_offered_fact_keys={"FACT-01"},
        )

        # --- Mock Database Pool (asyncpg connection) ---
        # claim_review: pg_advisory_xact_lock + UPDATE reviews
        # persist_results: SELECT engine_complete_review(...)
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(side_effect=[None, "UPDATE 1", None])  # lock, claim UPDATE, persist
        mock_conn.fetchval = AsyncMock(return_value=1)  # for claim_review UPDATE 1
        mock_conn.fetchrow = AsyncMock(return_value={"id": review_id})
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.transaction = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False))
        )

        mock_pool = MagicMock()
        mock_pool.pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        # --- Mock Provider (FakeProvider with controlled output) ---
        model_findings_json = json.dumps({
            "findings": [
                {
                    "ref_key": "CLAIM-01",
                    "issue": "contradicts_fact",
                    "quote": "100% secure",
                    "explanation": "Claim of 100% security contradicts the approved fact of 99.9% uptime",
                    "suggestion": "Use '99.9% uptime per SLA' instead",
                    "confidence": 0.92,
                },
                {
                    "ref_key": "TONE-01",
                    "issue": "violation",
                    "quote": "guaranteed",
                    "explanation": "Absolute guarantee violates professional tone guideline",
                    "suggestion": "highly reliable",
                    "confidence": 0.85,
                },
            ]
        })
        mock_provider = MagicMock()
        mock_provider.model = "fake-model"
        mock_provider.generate_findings = AsyncMock(return_value=ProviderResult(
            raw_json=model_findings_json,
            input_tokens=500,
            output_tokens=200,
            model="fake-model",
            latency_ms=350,
            finish_reason="stop",
        ))

        # --- Mocked stage outputs ---
        det_result = DeterministicCheckResult(
            candidates=[
                DeterministicFindingCandidate(
                    ref_key="TERM-01",
                    quote="utilize",
                    start_offset=10,
                    end_offset=17,
                    explanation="Avoid using utilize",
                    suggestion="use",
                    rule_category="terminology",
                    severity="medium",
                ),
                DeterministicFindingCandidate(
                    ref_key="TERM-02",
                    quote="leverage",
                    start_offset=31,
                    end_offset=39,
                    explanation="Avoid using leverage",
                    suggestion="use",
                    rule_category="terminology",
                    severity="medium",
                ),
            ],
            skipped_checks=[],
        )

        model_candidates = [
            ModelFindingCandidate(
                ref_key="CLAIM-01",
                issue="contradicts_fact",
                quote="100% secure",
                explanation="Claim of 100% security contradicts the approved fact of 99.9% uptime",
                suggestion="Use '99.9% uptime per SLA' instead",
                confidence=0.92,
            ),
            ModelFindingCandidate(
                ref_key="TONE-01",
                issue="violation",
                quote="guaranteed",
                explanation="Absolute guarantee violates professional tone guideline",
                suggestion="highly reliable",
                confidence=0.85,
            ),
        ]
        model_skipped = []
        model_name = "fake-model"
        prompt_version = "p1"
        input_tokens = 500
        output_tokens = 200
        model_warnings = []

        from app.models.pipeline import ValidatedFinding
        validated_findings = [
            ValidatedFinding(
                source="deterministic",
                ref_key="TERM-01",
                category="terminology",
                severity="medium",
                quote="utilize",
                start_offset=10,
                end_offset=17,
                explanation="Avoid using utilize",
                suggestion="use",
                confidence=None,
                needs_human=False,
                needs_reviewer=False,
            ),
            ValidatedFinding(
                source="deterministic",
                ref_key="TERM-02",
                category="terminology",
                severity="medium",
                quote="leverage",
                start_offset=31,
                end_offset=39,
                explanation="Avoid using leverage",
                suggestion="use",
                confidence=None,
                needs_human=False,
                needs_reviewer=False,
            ),
            ValidatedFinding(
                source="llm",
                ref_key="CLAIM-01",
                category="fact",
                severity="medium",
                quote="100% secure",
                start_offset=44,
                end_offset=56,
                explanation="Claim of 100% security contradicts the approved fact of 99.9% uptime",
                suggestion="Use '99.9% uptime per SLA' instead",
                confidence=0.92,
                needs_human=False,
                needs_reviewer=True,
            ),
            ValidatedFinding(
                source="llm",
                ref_key="TONE-01",
                category="tone",
                severity="low",
                quote="guaranteed",
                start_offset=67,
                end_offset=77,
                explanation="Absolute guarantee violates professional tone guideline",
                suggestion="highly reliable",
                confidence=0.85,
                needs_human=False,
                needs_reviewer=False,
            ),
        ]
        validation_result = AggregateValidationResult(
            validated_findings=validated_findings,
            kept_count=4,
            raw_candidate_count=4,
            dropped_counts={},
        )

        # --- Orchestrator with mocks ---
        orchestrator = ReviewOrchestrator()
        orchestrator.loader = mock_loader
        orchestrator._get_db_pool = AsyncMock(return_value=mock_pool)
        orchestrator.supabase = MagicMock()
        orchestrator.supabase.get_confidentiality_policy.return_value = None
        pipeline_rules, pipeline_facts = mock_loader.load_rules_and_facts.return_value
        configure_confirmed_preview(orchestrator, mock_loader.load_review_input.return_value, pipeline_rules, pipeline_facts)

        with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
          with patch('engine.app.pipeline.orchestrator.get_provider_with_fallback', return_value=mock_provider):
              with patch.object(orchestrator, '_run_deterministic_checks', new_callable=AsyncMock, return_value=det_result) as mock_det_checks:
                  with patch.object(orchestrator, '_run_model_analysis', new_callable=AsyncMock, return_value=(
                      model_candidates, model_skipped, model_name, prompt_version,
                      input_tokens, output_tokens, model_warnings
                  )) as mock_model:
                      with patch.object(orchestrator, '_run_validation', new_callable=AsyncMock, return_value=validation_result) as mock_validate:
                          with patch.object(orchestrator, '_persist_results', new_callable=AsyncMock) as mock_persist:
                              # Run the complete pipeline
                              output = await orchestrator.run_pipeline(review_id)

        # --- Assertions ---

        # 1. Pipeline completes successfully
        assert output is not None
        assert output.error is None
        assert output.llm_status == "ok"

        # 2. Both deterministic and model findings are validated and persisted
        assert len(output.validated_findings) == 4
        det_findings = [f for f in output.validated_findings if f.source == "deterministic"]
        model_findings = [f for f in output.validated_findings if f.source == "llm"]

        # Should have 2 deterministic findings (TERM-01, TERM-02)
        assert len(det_findings) == 2
        det_ref_keys = {f.ref_key for f in det_findings}
        assert det_ref_keys == {"TERM-01", "TERM-02"}

        # Should have 2 model findings (CLAIM-01, TONE-01)
        assert len(model_findings) == 2
        model_ref_keys = {f.ref_key for f in model_findings}
        assert model_ref_keys == {"CLAIM-01", "TONE-01"}

        # 3. Verify deterministic findings have correct metadata
        for f in det_findings:
            assert f.source == "deterministic"
            assert f.confidence is None
            assert f.needs_human is False
            assert f.category == "terminology"
            assert f.quote in ("utilize", "leverage")

        # 4. Verify model findings have correct metadata
        claim_finding = next(f for f in model_findings if f.ref_key == "CLAIM-01")
        tone_finding = next(f for f in model_findings if f.ref_key == "TONE-01")

        assert claim_finding.source == "llm"
        assert claim_finding.category == "fact"
        assert claim_finding.severity == "medium"  # default for facts
        assert claim_finding.needs_reviewer is True  # fact references need reviewer
        assert claim_finding.quote == "100% secure"
        assert claim_finding.confidence == 0.92

        assert tone_finding.source == "llm"
        assert tone_finding.category == "tone"
        assert tone_finding.quote == "guaranteed"
        assert tone_finding.confidence == 0.85

        # 5. Verify internal methods were called in correct sequence
        mock_det_checks.assert_called_once()
        mock_model.assert_called_once()
        mock_validate.assert_called_once()

        # 6. Verify persistence was called with correct claim token
        mock_persist.assert_called_once()
        persist_args = mock_persist.call_args
        assert persist_args.kwargs['claim_token'] is not None
        assert persist_args.kwargs['llm_status'] == "ok"
        assert persist_args.kwargs['llm_findings_raw'] == 2
        assert persist_args.kwargs['llm_findings_dropped'] == 0

        # 7. Verify validator stats
        assert output.validator_stats['kept'] == 4
        assert output.validator_stats['raw'] == 4
        assert sum(output.validator_stats['dropped'].values()) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])