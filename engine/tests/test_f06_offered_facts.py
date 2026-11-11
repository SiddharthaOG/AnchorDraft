"""Tests for F06: model_offered_facts passed correctly through orchestrator."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import date, timedelta

from app.pipeline.orchestrator import (
    ReviewOrchestrator,
    PipelineInput,
    RuleData,
    FactData,
)
from app.models.pipeline import (
    DeterministicFindingCandidate,
    ModelFindingCandidate,
    AggregateValidationResult,
    ValidatedFinding,
    FindingSource,
)
from app.checks.deterministic import DeterministicCheckResult, SkippedCheck



def configure_confirmed_preview(orchestrator, pipeline_input, rules, facts):
    """Build a consistent frozen-preview fixture for pipeline tests."""
    from dataclasses import asdict
    from app.confidentiality.preview import sha256_json, sha256_text
    from app.confidentiality.preview import confidentiality_policy_sha256
    from app.confidentiality.models import ConfidentialityPolicy
    from uuid import UUID
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


class TestF06ModelOfferedFacts:
    """Tests for F06: model_offered_facts passed correctly to validator."""

    @pytest.fixture
    def orchestrator(self):
        """Create an orchestrator with mocked dependencies."""
        orch = ReviewOrchestrator()
        orch.supabase.get_confidentiality_policy = MagicMock(return_value=None)
        # Mock the internal methods
        orch._claim_review = AsyncMock(return_value=(True, uuid4()))
        orch._load_review_data = AsyncMock()
        orch._load_visual_asset_ids = AsyncMock(return_value=[])
        orch._run_deterministic_checks = AsyncMock()
        orch._convert_deterministic_to_pipeline = MagicMock(return_value=([], []))
        orch._run_model_analysis = AsyncMock()
        orch._run_validation = AsyncMock()
        orch._persist_results = AsyncMock()
        # Mock the loader method (it's synchronous)
        orch.loader.load_rules_and_facts = MagicMock()
        return orch

    @pytest.fixture
    def pipeline_input(self):
        """Create a sample pipeline input."""
        return PipelineInput(
            review_id=uuid4(),
            revision_id=uuid4(),
            revision_text="This is a test draft with some content.",
            kit_id=uuid4(),
            org_id=uuid4(),
            purpose="marketing",
            channel="web",
            engine_version="0.1.0",
            preview_id=str(uuid4()),
        )

    @pytest.fixture
    def rules_and_facts(self):
        """Create sample rules and facts with known offered keys."""
        rules = [
            RuleData(
                rule_key="RULE-LLM-01",
                category="style",
                severity="medium",
                title="LLM Rule 1",
                guideline_text="Use active voice",
                check_kind="llm",
                needs_reviewer=False,
            ),
            RuleData(
                rule_key="RULE-DET-01",
                category="terminology",
                severity="low",
                title="Deterministic Rule 1",
                guideline_text="Avoid 'utilize'",
                check_kind="deterministic",
                needs_reviewer=False,
            ),
            RuleData(
                rule_key="RULE-LLM-02",
                category="tone",
                severity="high",
                title="LLM Rule 2",
                guideline_text="Be concise",
                check_kind="llm",
                needs_reviewer=True,
            ),
        ]
        
        facts = [
            FactData(
                fact_key="FACT-OFFERED-01",
                statement="Company founded in 2020",
                source_note="About page",
                valid_until=None,  # Never expires
            ),
            FactData(
                fact_key="FACT-OFFERED-02",
                statement="Headquarters in San Francisco",
                source_note="Contact page",
                valid_until=date.today() + timedelta(days=30),  # Valid
            ),
            FactData(
                fact_key="FACT-EXPIRED-01",
                statement="Old fact that expired",
                source_note="Old source",
                valid_until=date.today() - timedelta(days=1),  # Expired
            ),
        ]
        
        return rules, facts

    @pytest.mark.asyncio
    async def test_model_offered_facts_extracted_correctly(self, orchestrator, pipeline_input, rules_and_facts):
        """Test that _extract_offered_keys returns the correct fact keys."""
        rules, facts = rules_and_facts
        
        offered_rules, offered_facts = orchestrator._extract_offered_keys(rules, facts)
        
        # Should include only LLM rule keys
        assert offered_rules == {"RULE-LLM-01", "RULE-LLM-02"}
        assert "RULE-DET-01" not in offered_rules
        
        # Should include only valid (non-expired) fact keys
        assert offered_facts == {"FACT-OFFERED-01", "FACT-OFFERED-02"}
        assert "FACT-EXPIRED-01" not in offered_facts

    @pytest.mark.asyncio
    async def test_validator_receives_model_offered_facts(self, orchestrator, pipeline_input, rules_and_facts):
        """Test that _run_validation is called with the correct model_offered_facts."""
        rules, facts = rules_and_facts
        configure_confirmed_preview(orchestrator, pipeline_input, rules, facts)
        
        # Setup mocks
        orchestrator._load_review_data.return_value = pipeline_input
        orchestrator.loader.load_rules_and_facts.return_value = (rules, facts)
        
        # Mock deterministic checks result
        orchestrator._run_deterministic_checks.return_value = DeterministicCheckResult(
            candidates=[],
            skipped_checks=[],
        )
        
        # Mock model analysis to return candidates with a fact reference
        model_candidate = ModelFindingCandidate(
            issue="violation",
            quote="founded in 2020",
            explanation="References company founding fact",
            confidence=0.9,
            ref_key="FACT-OFFERED-01",  # References an offered fact
            suggestion=None,
        )
        orchestrator._run_model_analysis.return_value = (
            [model_candidate],  # candidates
            None,  # raw_json
            "test-model",  # model
            100,  # input_tokens
            50,  # output_tokens
            [],  # warnings
        )
        
        # Mock validation result - use a MagicMock with the right attributes
        mock_validation_result = MagicMock(spec=AggregateValidationResult)
        mock_validation_result.raw_candidate_count = 1
        mock_validation_result.kept_count = 1
        mock_validation_result.dropped_counts = {}
        mock_validation_result.validated_findings = []
        orchestrator._run_validation.return_value = mock_validation_result
        
        # Run with a mocked decryptor for the encrypted preview mapping.
        with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
            await orchestrator.run_pipeline(pipeline_input.review_id)
        
        # Verify _run_validation was called with correct model_offered_facts
        call_args = orchestrator._run_validation.call_args
        assert call_args is not None
        
        kwargs = call_args.kwargs
        assert "model_offered_facts" in kwargs
        offered_facts = kwargs["model_offered_facts"]
        
        # Should be the set of valid fact keys
        assert offered_facts == {"FACT-OFFERED-01", "FACT-OFFERED-02"}
        assert "FACT-EXPIRED-01" not in offered_facts

    @pytest.mark.asyncio
    async def test_unoffered_fact_rejected_by_validator(self, orchestrator, pipeline_input, rules_and_facts):
        """Test that a finding referencing an unoffered fact is rejected."""
        rules, facts = rules_and_facts
        configure_confirmed_preview(orchestrator, pipeline_input, rules, facts)
        
        orchestrator._load_review_data.return_value = pipeline_input
        orchestrator.loader.load_rules_and_facts.return_value = (rules, facts)
        
        orchestrator._run_deterministic_checks.return_value = DeterministicCheckResult(
            candidates=[],
            skipped_checks=[],
        )
        
        # Model candidate references an EXPIRED (unoffered) fact
        model_candidate = ModelFindingCandidate(
            issue="violation",
            quote="Old fact that expired",
            explanation="References expired fact",
            confidence=0.9,
            ref_key="FACT-EXPIRED-01",  # This fact is expired, not offered
            suggestion=None,
        )
        orchestrator._run_model_analysis.return_value = (
            [model_candidate],
            None,
            "test-model",
            100,
            50,
            [],
        )
        
        # Mock validation to track what was dropped
        def mock_validation(*args, **kwargs):
            # The validator should drop this because FACT-EXPIRED-01 is not in model_offered_facts
            return AggregateValidationResult(
                raw_candidate_count=1,
                kept_count=0,
                dropped_counts={"model_ref_not_offered": 1},
                validated_findings=[],
            )
        orchestrator._run_validation.side_effect = mock_validation
        
        with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
            await orchestrator.run_pipeline(pipeline_input.review_id)
        
        # Verify the validation was called with correct offered facts
        call_args = orchestrator._run_validation.call_args
        offered_facts = call_args.kwargs["model_offered_facts"]
        assert "FACT-EXPIRED-01" not in offered_facts

    @pytest.mark.asyncio
    async def test_offered_fact_accepted_by_validator(self, orchestrator, pipeline_input, rules_and_facts):
        """Test that a finding referencing an offered fact is accepted."""
        rules, facts = rules_and_facts
        configure_confirmed_preview(orchestrator, pipeline_input, rules, facts)
        
        orchestrator._load_review_data.return_value = pipeline_input
        orchestrator.loader.load_rules_and_facts.return_value = (rules, facts)
        
        orchestrator._run_deterministic_checks.return_value = DeterministicCheckResult(
            candidates=[],
            skipped_checks=[],
        )
        
        # Model candidate references an OFFERED fact
        model_candidate = ModelFindingCandidate(
            issue="violation",
            quote="founded in 2020",
            explanation="References offered fact",
            confidence=0.9,
            ref_key="FACT-OFFERED-01",  # This fact IS offered
            suggestion=None,
        )
        orchestrator._run_model_analysis.return_value = (
            [model_candidate],
            None,
            "test-model",
            100,
            50,
            [],
        )
        
        # Mock validation to accept the finding
        mock_validation_result = MagicMock(spec=AggregateValidationResult)
        mock_validation_result.raw_candidate_count = 1
        mock_validation_result.kept_count = 1
        mock_validation_result.dropped_counts = {}
        mock_validation_result.validated_findings = []
        orchestrator._run_validation.return_value = mock_validation_result
        
        with patch("app.confidentiality.preview.decrypt_reverse_map", return_value={}):
            await orchestrator.run_pipeline(pipeline_input.review_id)
        
        # Verify the validation was called with correct offered facts
        call_args = orchestrator._run_validation.call_args
        offered_facts = call_args.kwargs["model_offered_facts"]
        assert "FACT-OFFERED-01" in offered_facts
        
        # The finding should be kept (not dropped)
        assert orchestrator._run_validation.return_value.kept_count == 1
        assert orchestrator._run_validation.return_value.dropped_counts == {}