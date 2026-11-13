from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.visual.analyzer as analyzer_module


@pytest.mark.asyncio
async def test_run_visual_analysis_forwards_preview_security_context(monkeypatch):
    expected_request = object()
    expected_checksums = {"asset-1": "sha256-confirmed"}
    expected_guidelines = {"tone": "redacted-placeholder"}
    analyzer = SimpleNamespace(analyze_assets=AsyncMock(return_value="ok"))
    monkeypatch.setattr(analyzer_module, "VisualAnalyzer", lambda: analyzer)

    result = await analyzer_module.run_visual_analysis(
        asset_ids=[],
        revision_text="redacted draft",
        purpose="redacted purpose",
        channel="web",
        visual_guidelines={"tone": "original confidential value"},
        org_id="org-id",
        provider_visual_guidelines=expected_guidelines,
        placeholder_map={"[TERM_1]": "sensitive value"},
        provider_request_override=expected_request,
        expected_asset_checksums=expected_checksums,
    )

    assert result == "ok"
    analyzer.analyze_assets.assert_awaited_once()
    forwarded = analyzer.analyze_assets.await_args.kwargs
    assert forwarded["provider_visual_guidelines"] is expected_guidelines
    assert forwarded["provider_request_override"] is expected_request
    assert forwarded["expected_asset_checksums"] is expected_checksums
    assert forwarded["placeholder_map"] == {"[TERM_1]": "sensitive value"}
