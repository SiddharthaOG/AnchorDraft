"""Visual-provider confidentiality boundary tests."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.confidentiality import ConfidentialityEngine, ConfidentialityPolicy
from app.models.pipeline import ProviderRequest, ProviderResult, UnavailableError
from app.visual.analyzer import VisualAnalyzer
from app.llm.provider_factory import (ProviderWithFallback, ProviderSettings, ProviderType, get_vision_provider_with_fallback)


class VisionProvider:
    model = "vision-test"

    def __init__(self, result):
        self.result = result
        self.request = None
        self.images = None

    async def generate_findings(self, request, images):
        self.request = request
        self.images = images
        return self.result


@pytest.mark.asyncio
async def test_vision_provider_receives_redacted_text_and_guidelines_and_restores_finding_text():
    org_id = uuid4()
    raw_email = "private.person@example.com"
    raw_guidelines = {
        "voice": {"description": f"Never display {raw_email}"},
        "logo": {"approved_hashes": ["aabbcc"]},
    }
    policy = ConfidentialityPolicy(org_id=org_id)
    engine = ConfidentialityEngine()
    batch = engine.redact_fields({
        "draft": f"Contact {raw_email}",
        "purpose": f"Promote {raw_email}",
        "guideline": raw_guidelines["voice"]["description"],
    }, policy)
    redacted_guidelines = {
        "voice": {"description": batch.fields["guideline"]},
        "logo": {"approved_hashes": ["aabbcc"]},
    }
    asset_id = uuid4()
    image_bytes = b"\x89PNG\r\noriginal-image-bytes"
    result = ProviderResult(
        raw_json=json.dumps({"findings": [{
            "ref_key": "VIS-01",
            "issue": "violation",
            "quote": batch.fields["draft"],
            "asset_id": str(asset_id),
            "region": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
            "explanation": f"Contains {next(iter(batch.placeholder_map))}",
            "suggestion": f"Remove {next(iter(batch.placeholder_map))}",
            "confidence": 0.9,
        }]}),
        input_tokens=20,
        output_tokens=10,
        model="vision-test",
        latency_ms=10,
        finish_reason="stop",
    )
    provider = VisionProvider(result)
    analyzer = VisualAnalyzer.__new__(VisualAnalyzer)

    with patch("app.visual.analyzer.get_vision_provider_with_fallback", return_value=provider):
        findings = await analyzer._run_vision_analysis(
            assets_data=[{
                "asset_id": asset_id,
                "file_bytes": image_bytes,
                "mime_type": "image/png",
            }],
            revision_text=batch.fields["draft"],
            purpose=batch.fields["purpose"],
            channel="web",
            visual_guidelines=redacted_guidelines,
            approved_hashes=["aabbcc"],
            placeholder_map=dict(batch.placeholder_map),
        )

    provider_payload = provider.request.system_instruction + "\n" + provider.request.user_content
    assert raw_email not in provider_payload
    assert raw_email not in json.dumps(redacted_guidelines)
    assert any(token in provider_payload for token in batch.placeholder_map)
    # Images are deliberately not transformed: Step 3 must disclose and gate this.
    assert provider.images[0]["data"] == image_bytes
    assert findings[0].quote == f"Contact {raw_email}"
    assert raw_email in findings[0].explanation
    assert raw_email in findings[0].suggestion


@pytest.mark.asyncio
async def test_vision_provider_receives_exact_frozen_preview_request():
    asset_id = uuid4()
    image_bytes = b"approved-image-bytes"
    approved_request = ProviderRequest(
        system_instruction="approved-vision-system",
        user_content="approved-redacted-vision-prompt",
        output_schema={"type": "object"},
        randomness=0.12,
        output_limit=888,
        timeout_seconds=42,
    )
    result = ProviderResult(
        raw_json='{"findings":[]}',
        input_tokens=15,
        output_tokens=1,
        model="vision-frozen",
        latency_ms=5,
        finish_reason="stop",
    )
    provider = VisionProvider(result)
    analyzer = VisualAnalyzer.__new__(VisualAnalyzer)

    with patch("app.visual.analyzer.get_vision_provider_with_fallback", return_value=provider):
        await analyzer._run_vision_analysis(
            assets_data=[{
                "asset_id": asset_id,
                "file_bytes": image_bytes,
                "mime_type": "image/png",
            }],
            revision_text="redacted draft",
            purpose="redacted purpose",
            channel="web",
            visual_guidelines={},
            approved_hashes=[],
            placeholder_map={},
            provider_request_override=approved_request,
        )

    assert provider.request is approved_request
    assert provider.images[0]["data"] == image_bytes


class FailingVisionProvider:
    model = "primary-vision-test"

    def __init__(self):
        self.request = None
        self.images = None

    async def generate_findings(self, request, images):
        self.request = request
        self.images = images
        raise UnavailableError("temporary vision outage")


@pytest.mark.asyncio
async def test_vision_fallback_receives_the_same_approved_request_and_images():
    approved_request = ProviderRequest(
        system_instruction="approved-system",
        user_content="approved-redacted-content",
        output_schema={"type": "object", "properties": {"findings": {"type": "array"}}},
        randomness=0.13,
        output_limit=1234,
        timeout_seconds=30,
    )
    images = [{"asset_id": str(uuid4()), "data": b"stored-image", "mime_type": "image/png"}]
    primary = FailingVisionProvider()
    fallback = VisionProvider(ProviderResult(
        raw_json='{"findings":[]}',
        input_tokens=10,
        output_tokens=1,
        model="fallback-vision-test",
        latency_ms=4,
        finish_reason="stop",
    ))
    wrapper = ProviderWithFallback(primary=primary, fallback=fallback)

    result = await wrapper.generate_findings(approved_request, images)

    assert result.model == "fallback-vision-test"
    assert primary.request.model_dump(exclude={"timeout_seconds"}) == approved_request.model_dump(exclude={"timeout_seconds"})
    assert fallback.request.model_dump(exclude={"timeout_seconds"}) == approved_request.model_dump(exclude={"timeout_seconds"})
    assert fallback.request.timeout_seconds <= approved_request.timeout_seconds
    assert primary.images is images
    assert fallback.images is images


@pytest.mark.asyncio
async def test_vision_factory_uses_vision_capable_fake_adapter_in_local_mode(monkeypatch):
    from app.visual.vision_providers import FakeVisionProvider

    monkeypatch.setattr(
        "app.llm.provider_factory.load_provider_settings",
        lambda: ProviderSettings(
            provider_type=ProviderType.FAKE,
            fallback_enabled=False,
        ),
    )
    wrapper = get_vision_provider_with_fallback()
    assert isinstance(wrapper._primary, FakeVisionProvider)

    request = ProviderRequest(
        system_instruction="system",
        user_content="redacted visual prompt",
        output_schema={"type": "object", "properties": {"findings": {"type": "array"}}},
        randomness=0.1,
        output_limit=100,
        timeout_seconds=10,
    )
    result = await wrapper.generate_findings(
        request,
        [{"asset_id": str(uuid4()), "data": b"image", "mime_type": "image/png"}],
    )
    assert json.loads(result.raw_json) == {"findings": []}
