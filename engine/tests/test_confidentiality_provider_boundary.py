"""Provider-boundary tests: raw sensitive values must never leave the engine."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.confidentiality import ConfidentialityEngine, ConfidentialityPolicy
from app.llm.prompt_builder import RuleData
from app.models.pipeline import ProviderRequest, ProviderResult
from app.pipeline.orchestrator import ReviewOrchestrator


@pytest.mark.asyncio
async def test_model_provider_receives_redacted_fields_and_quotes_restore_before_validation():
    org_id = UUID("11111111-1111-1111-1111-111111111111")
    source = "Contact person@example.com using sk_live_12345678901234567890."
    purpose = "Follow up with person@example.com"
    guideline = "Never publish person@example.com or sk_live_12345678901234567890."

    policy = ConfidentialityPolicy(org_id=org_id, custom_terms=("Project Apollo",))
    batch = ConfidentialityEngine().redact_fields(
        {
            "draft": source,
            "purpose": purpose,
            "channel": "email",
            "rule_key": "person@example.com",
            "rule_title": "Protect person@example.com",
            "rule_guideline": guideline,
        },
        policy,
    )

    redacted_rule = RuleData(
        rule_key=batch.fields["rule_key"],
        category="privacy",
        severity="high",
        title=batch.fields["rule_title"],
        guideline_text=batch.fields["rule_guideline"],
        check_kind="llm",
    )

    placeholders = list(batch.placeholder_map)
    assert placeholders
    redacted_quote = batch.fields["draft"]
    raw_finding = {
        "findings": [
            {
                "ref_key": batch.fields["rule_key"],
                "issue": "violation",
                "quote": redacted_quote,
                "explanation": f"Sensitive value {placeholders[0]} must not be exposed.",
                "suggestion": f"Replace {placeholders[0]} with a generic contact label.",
                "confidence": 0.95,
            }
        ]
    }
    provider_result = ProviderResult(
        raw_json=json.dumps(raw_finding),
        input_tokens=100,
        output_tokens=40,
        model="test-provider",
        latency_ms=12,
        finish_reason="stop",
    )
    provider = MagicMock()
    provider.generate_findings = AsyncMock(return_value=provider_result)

    orchestrator = ReviewOrchestrator()
    with patch("app.pipeline.orchestrator.get_provider_with_fallback", return_value=provider):
        candidates, _, model, _, _, _, _ = await orchestrator._run_model_analysis(
            batch.fields["draft"],
            [redacted_rule],
            [],
            batch.fields["purpose"],
            batch.fields["channel"],
            placeholder_map=dict(batch.placeholder_map),
        )

    sent_request = provider.generate_findings.await_args.args[0]
    sent_payload = sent_request.system_instruction + "\n" + sent_request.user_content
    for sensitive_value in (
        "person@example.com",
        "sk_live_12345678901234567890",
    ):
        assert sensitive_value not in sent_payload
    assert any(placeholder in sent_payload for placeholder in placeholders)

    assert model == "test-provider"
    assert len(candidates) == 1
    assert candidates[0].ref_key == "person@example.com"
    assert candidates[0].quote == source
    assert "person@example.com" in candidates[0].explanation
    assert "person@example.com" in candidates[0].suggestion


@pytest.mark.asyncio
async def test_text_provider_receives_exact_frozen_preview_request():
    rule = RuleData(
        rule_key="RULE-01",
        category="tone",
        severity="medium",
        title="Keep the tone concise",
        guideline_text="Use short sentences",
        check_kind="llm",
    )
    approved_request = ProviderRequest(
        system_instruction="approved-system-prompt",
        user_content="approved-redacted-user-prompt",
        output_schema={"type": "object", "properties": {"findings": {"type": "array"}}},
        randomness=0.17,
        output_limit=777,
        timeout_seconds=31,
    )
    provider_result = ProviderResult(
        raw_json='{"findings":[]}',
        input_tokens=12,
        output_tokens=2,
        model="frozen-request-provider",
        latency_ms=3,
        finish_reason="stop",
    )
    provider = MagicMock()
    provider.generate_findings = AsyncMock(return_value=provider_result)
    orchestrator = ReviewOrchestrator()

    with patch("app.pipeline.orchestrator.get_provider_with_fallback", return_value=provider):
        await orchestrator._run_model_analysis(
            "redacted draft",
            [rule],
            [],
            "redacted purpose",
            "web",
            placeholder_map={},
            provider_request_override=approved_request,
        )

    sent_request = provider.generate_findings.await_args.args[0]
    assert sent_request is approved_request
    assert sent_request.model_dump() == approved_request.model_dump()
