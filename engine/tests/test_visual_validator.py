"""Regression tests for deterministic and model-generated visual finding validation."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.pipeline import BadOutputError, ProviderRequest, VisualModelFindingCandidate
from app.validator import RuleRecord, ValidationContext, run_citation_validator
from app.visual.deterministic import VisualFindingCandidate
from app.visual.vision_providers import (
    VISUAL_OUTPUT_SCHEMA,
    GeminiVisionProvider,
    GroqVisionProvider,
    build_vision_user_content,
    get_visual_guideline_ref_keys,
)


def make_context(*, offered_visual_rules=None):
    return ValidationContext(
        all_rules=[
            RuleRecord(
                rule_key="PALETTE-01",
                category="palette",
                severity="medium",
                needs_reviewer=True,
                check_kind="deterministic",
            )
        ],
        all_facts=[],
        model_offered_rule_keys=set(),
        model_offered_fact_keys=set(),
        visual_model_offered_rule_keys=set(offered_visual_rules or set()),
    )


def make_visual_model_candidate(**overrides):
    payload = {
        "ref_key": "PALETTE-01",
        "issue": "palette_violation",
        "quote": "blue primary action button",
        "asset_id": str(uuid4()),
        "region": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.2},
        "explanation": "The primary action uses a color outside the approved palette.",
        "suggestion": "Use an approved brand color.",
        "confidence": 0.91,
    }
    payload.update(overrides)
    return VisualModelFindingCandidate.model_validate(payload)


def test_visual_deterministic_candidates_are_processed_and_persistable():
    asset_id = uuid4()
    candidate = VisualFindingCandidate(
        ref_key="PALETTE-01",
        category="palette",
        severity="medium",
        asset_id=asset_id,
        region={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        explanation="The dominant color exceeds the brand palette tolerance.",
        suggestion="Use an approved brand color.",
        confidence=0.7,
        needs_reviewer=True,
    )

    result = run_citation_validator(
        revision_text="",
        deterministic_candidates=[],
        model_candidates=[],
        context=make_context(),
        visual_deterministic_candidates=[candidate],
    )

    assert result.raw_candidate_count == 1
    assert result.kept_count == 1
    assert result.dropped_counts == {}
    finding = result.validated_findings[0]
    assert finding.source == "deterministic"
    assert finding.asset_id == str(asset_id)
    assert finding.region == candidate.region
    assert finding.quote is None
    assert finding.start_offset is None
    assert finding.end_offset is None
    assert finding.needs_reviewer is True


def test_visual_model_candidate_schema_accepts_visual_evidence_and_issue_types():
    candidate = make_visual_model_candidate()

    assert candidate.issue == "palette_violation"
    assert candidate.asset_id is not None
    assert candidate.region == {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.2}
    assert VISUAL_OUTPUT_SCHEMA["properties"]["findings"]["items"]["properties"]["issue"]["enum"] == [
        "violation",
        "logo_misuse",
        "palette_violation",
        "contrast_violation",
        "unauthorized_logo",
    ]


@pytest.mark.parametrize("provider_type", [GroqVisionProvider, GeminiVisionProvider])
def test_vision_provider_adapters_accept_visual_candidate_schema(provider_type):
    finding = make_visual_model_candidate().model_dump(mode="json")
    content = json.dumps({"findings": [finding]})
    provider = object.__new__(provider_type)
    provider._model = "test-vision-model"
    request = ProviderRequest(
        system_instruction="Analyze the image.",
        user_content="Visual guidelines.",
        output_schema=VISUAL_OUTPUT_SCHEMA,
    )

    if provider_type is GroqVisionProvider:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
    else:
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(parts=[SimpleNamespace(text=content)]),
                    finish_reason="STOP",
                )
            ],
            usage_metadata=None,
        )

    result = provider._parse_response(response, request)
    assert json.loads(result.raw_json)["findings"][0]["asset_id"] == finding["asset_id"]


@pytest.mark.parametrize("provider_type", [GroqVisionProvider, GeminiVisionProvider])
def test_vision_provider_adapters_reject_invalid_visual_candidate(provider_type):
    finding = make_visual_model_candidate().model_dump(mode="json")
    finding["region"] = {"x": 0.9, "y": 0.1, "w": 0.2, "h": 0.2}
    content = json.dumps({"findings": [finding]})
    provider = object.__new__(provider_type)
    provider._model = "test-vision-model"
    request = ProviderRequest(
        system_instruction="Analyze the image.",
        user_content="Visual guidelines.",
        output_schema=VISUAL_OUTPUT_SCHEMA,
    )

    if provider_type is GroqVisionProvider:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )
    else:
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(parts=[SimpleNamespace(text=content)]),
                    finish_reason="STOP",
                )
            ],
            usage_metadata=None,
        )

    with pytest.raises(BadOutputError, match="validation failed"):
        provider._parse_response(response, request)


def test_visual_model_findings_are_processed_when_their_rule_was_offered():
    candidate = make_visual_model_candidate()
    result = run_citation_validator(
        revision_text="",
        deterministic_candidates=[],
        model_candidates=[],
        context=make_context(offered_visual_rules={"PALETTE-01"}),
        visual_model_candidates=[candidate],
    )

    assert result.raw_candidate_count == 1
    assert result.kept_count == 1
    finding = result.validated_findings[0]
    assert finding.source == "llm"
    assert finding.asset_id == str(candidate.asset_id)
    assert finding.region == candidate.region
    assert finding.quote is None
    assert finding.needs_reviewer is True


def test_visual_model_finding_is_rejected_when_rule_was_not_offered():
    candidate = make_visual_model_candidate()
    result = run_citation_validator(
        revision_text="",
        deterministic_candidates=[],
        model_candidates=[],
        context=make_context(),
        visual_model_candidates=[candidate],
    )

    assert result.kept_count == 0
    assert result.dropped_counts == {"unknown_ref": 1}


def test_visual_model_finding_cannot_duplicate_deterministic_finding_for_same_asset_and_rule():
    asset_id = uuid4()
    deterministic = VisualFindingCandidate(
        ref_key="PALETTE-01",
        category="palette",
        severity="medium",
        asset_id=asset_id,
        region={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        explanation="A deterministic palette check found an out-of-palette color.",
        confidence=0.7,
    )
    model = make_visual_model_candidate(asset_id=str(asset_id))

    result = run_citation_validator(
        revision_text="",
        deterministic_candidates=[],
        model_candidates=[],
        context=make_context(offered_visual_rules={"PALETTE-01"}),
        visual_deterministic_candidates=[deterministic],
        visual_model_candidates=[model],
    )

    assert result.kept_count == 1
    assert result.dropped_counts == {"duplicate": 1}
    assert result.validated_findings[0].source == "deterministic"


@pytest.mark.parametrize(
    "region",
    [
        {"x": 0.1, "y": 0.1, "w": 0.0, "h": 0.2},
        {"x": 0.9, "y": 0.1, "w": 0.2, "h": 0.2},
        {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "extra": 0.1},
        {"x": True, "y": 0.1, "w": 0.2, "h": 0.2},
    ],
)
def test_visual_model_candidate_rejects_invalid_regions(region):
    with pytest.raises(ValidationError):
        make_visual_model_candidate(region=region)


def test_visual_guidelines_prompt_discloses_only_the_supported_reference_keys():
    guidelines = {
        "palette": {"colors": [{"hex": "#123456"}]},
        "contrast": {"min_ratio": 4.5},
    }

    assert get_visual_guideline_ref_keys(guidelines) == {"PALETTE-01", "CONTRAST-01"}
    prompt = build_vision_user_content(
        draft_text="Draft",
        purpose="Campaign",
        channel="Web",
        visual_guidelines=guidelines,
        asset_ids=[str(uuid4())],
        nonce="test-nonce",
    )
    assert "PALETTE | REF_KEY: PALETTE-01" in prompt
    assert "CONTRAST | REF_KEY: CONTRAST-01" in prompt
    assert "LOGO-01" not in prompt


def test_visual_logo_guidelines_are_exposed_to_vision_model_with_description_and_variants():
    guidelines = {
        "logo": {
            "required": True,
            "description": "White wordmark with a leaf icon",
            "variants": ["primary", "monochrome"],
        }
    }

    assert get_visual_guideline_ref_keys(guidelines) == {"LOGO-01"}
    prompt = build_vision_user_content(
        draft_text="Draft",
        purpose="Campaign",
        channel="Web",
        visual_guidelines=guidelines,
        asset_ids=[str(uuid4())],
        nonce="logo-test",
    )
    assert "[LOGO | REF_KEY: LOGO-01]" in prompt
    assert "White wordmark with a leaf icon" in prompt
    assert "monochrome" in prompt
