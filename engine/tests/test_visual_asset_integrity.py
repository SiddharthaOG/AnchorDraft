"""Regression tests for visual asset ownership, upload lifecycle, and fail-closed analysis.

These are unit/mocked tests plus migration-contract assertions; they do not execute SQL
against a live Supabase/PostgreSQL database.
"""
import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.visual.asset_service import (
    VisualAssetMetadata,
    VisualAssetService,
    VisualAssetUploadResult,
)
from app.visual.analyzer import VisualAnalyzer


def metadata():
    return VisualAssetMetadata(20, 10, "image/png", "a" * 64, [], [], "hash")


def asset_row(asset_id, org_id, path):
    return {
        "id": str(asset_id), "org_id": str(org_id), "storage_path": path,
        "mime_type": "image/png", "width": 20, "height": 10,
        "checksum": "a" * 64, "metadata": {"palette": [], "dominant_colors": [], "perceptual_hash": "hash"},
    }


def service_with_client():
    service = VisualAssetService()
    client = MagicMock()
    bucket = client.storage.from_.return_value
    service._client = client
    return service, client, bucket


def test_existing_checksum_reuses_dict_without_upload():
    service, client, bucket = service_with_client()
    org_id, user_id, asset_id = uuid4(), uuid4(), uuid4()
    existing = asset_row(asset_id, org_id, f"{org_id}/{asset_id}.png")
    service.strip_exif = MagicMock(return_value=b"canonical")
    service.extract_extended_metadata = MagicMock(return_value=metadata())
    service.get_asset_by_checksum = MagicMock(return_value=existing)

    result = service.upload_asset(org_id, user_id, b"source", "image/png", "x.png")

    assert isinstance(result, VisualAssetUploadResult)
    assert result.created is False
    assert result.storage_path == existing["storage_path"]
    assert result.asset_id == asset_id
    bucket.upload.assert_not_called()
    client.rpc.assert_not_called()


def test_create_asset_record_passes_actor_and_normalizes_uuid():
    service, client, _ = service_with_client()
    org_id, actor_id, asset_id = uuid4(), uuid4(), uuid4()
    path = f"{org_id}/{asset_id}.png"
    row = asset_row(asset_id, org_id, path)
    client.rpc.return_value.execute.return_value.data = str(asset_id)
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [row]

    result = service.create_asset_record(org_id, actor_id, path, "image/png", metadata())

    assert result["id"] == str(asset_id)
    args = client.rpc.call_args.args
    assert args[0] == "create_visual_asset"
    assert args[1]["_actor_user_id"] == str(actor_id)
    assert args[1]["_org_id"] == str(org_id)


def test_checksum_race_removes_only_our_new_object_and_reuses_row():
    service, _, bucket = service_with_client()
    org_id, user_id, new_id, existing_id = uuid4(), uuid4(), uuid4(), uuid4()
    existing = asset_row(existing_id, org_id, f"{org_id}/{existing_id}.png")
    service.strip_exif = MagicMock(return_value=b"canonical")
    service.extract_extended_metadata = MagicMock(return_value=metadata())
    service.get_asset_by_checksum = MagicMock(return_value=None)
    service.create_asset_record = MagicMock(return_value=existing)

    result = service.upload_asset(org_id, user_id, b"source", "image/png", "x.png")

    assert result.created is False
    assert result.asset_id == existing_id
    bucket.upload.assert_called_once()
    removed_path = bucket.remove.call_args.args[0][0]
    assert removed_path.startswith(f"{org_id}/")
    assert removed_path != existing["storage_path"]


def test_upload_record_failure_removes_new_storage_object_and_preserves_error():
    service, _, bucket = service_with_client()
    org_id, user_id = uuid4(), uuid4()
    service.strip_exif = MagicMock(return_value=b"canonical")
    service.extract_extended_metadata = MagicMock(return_value=metadata())
    service.get_asset_by_checksum = MagicMock(return_value=None)
    service.create_asset_record = MagicMock(side_effect=RuntimeError("database unavailable"))

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.upload_asset(org_id, user_id, b"source", "image/png", "x.png")
    bucket.upload.assert_called_once()
    bucket.remove.assert_called_once()


def test_cleanup_refuses_rpc_failure_and_does_not_remove_storage():
    service, client, bucket = service_with_client()
    client.rpc.return_value.execute.side_effect = RuntimeError("linked asset")
    with pytest.raises(RuntimeError, match="Safe cleanup refused"):
        service.cleanup_new_asset(uuid4(), uuid4(), "org/asset.png", uuid4())
    bucket.remove.assert_not_called()


def test_cleanup_removes_only_path_returned_by_guarded_rpc():
    service, client, bucket = service_with_client()
    client.rpc.return_value.execute.return_value.data = "org/asset.png"
    service.cleanup_new_asset(uuid4(), uuid4(), "org/asset.png", uuid4())
    bucket.remove.assert_called_once_with(["org/asset.png"])


def test_signed_url_failure_raises():
    service, client, _ = service_with_client()
    client.storage.from_.return_value.create_signed_url.side_effect = RuntimeError("storage down")
    with pytest.raises(RuntimeError, match="Failed to create signed URL"):
        service.get_signed_url("org/asset.png")


@pytest.mark.asyncio
async def test_analyzer_fails_closed_when_any_requested_asset_is_missing():
    analyzer = VisualAnalyzer()
    missing = uuid4()
    analyzer.load_asset_bytes = MagicMock(side_effect=ValueError("missing"))
    with pytest.raises(ValueError, match=str(missing)):
        await analyzer.analyze_assets(
            asset_ids=[missing], revision_text="text", purpose="purpose",
            channel="web", visual_guidelines={}, org_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_asset_record_lookup_and_storage_download_run_off_event_loop():
    analyzer = VisualAnalyzer()
    main_thread = threading.get_ident()
    record_thread = []
    download_thread = []
    org_id, asset_id = uuid4(), uuid4()
    row = asset_row(asset_id, org_id, f"{org_id}/{asset_id}.png")
    client = MagicMock()
    client.storage.from_.return_value.download.side_effect = lambda path: (
        download_thread.append(threading.get_ident()) or b"image-bytes"
    )
    analyzer.supabase.get_visual_asset = lambda *_: (
        record_thread.append(threading.get_ident()) or row
    )
    analyzer.supabase._get_client = lambda: client

    await analyzer.load_asset_bytes(asset_id, org_id)

    assert record_thread and record_thread[0] != main_thread
    assert download_thread and download_thread[0] != main_thread


@pytest.mark.asyncio
async def test_revision_rpc_failure_propagates():
    analyzer = VisualAnalyzer()
    analyzer.supabase.get_revision = MagicMock(return_value={"content_id": str(uuid4())})
    analyzer.supabase.get_content = MagicMock(return_value={"org_id": str(uuid4())})
    with pytest.raises(ValueError, match="expected organization"):
        await analyzer.load_visual_assets_for_review(uuid4(), uuid4())


def test_sql_migrations_enforce_required_database_contracts():
    root = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    base_visual_sql = (root / "20261111000001_visual_assets.sql").read_text(encoding="utf-8")
    asset_sql = (root / "20261113000001_visual_asset_integrity.sql").read_text(encoding="utf-8")
    link_sql = (root / "20261112000001_visual_asset_content_link.sql").read_text(encoding="utf-8")
    review_sql = (root / "20261113000002_exact_visual_revision_evidence.sql").read_text(encoding="utf-8")
    lease_sql = (root / "20261107000001_review_lease.sql").read_text(encoding="utf-8")
    historical_visual_sql = (root / "20261112000002_update_engine_complete_review_for_visual.sql").read_text(encoding="utf-8")
    security_sql = (root / "20261113000003_visual_rpc_service_role_only.sql").read_text(encoding="utf-8")

    assert "revoke all on function public.get_visual_asset(uuid) from public, anon, authenticated, service_role" in security_sql.lower()
    assert "revoke all on function public.get_visual_asset_signed_url(uuid, integer)" in security_sql.lower()
    assert "revoke all on function public.list_visual_assets(uuid, integer, integer)" in security_sql.lower()
    assert "revoke all on function public.get_visual_assets_for_content(uuid)" in security_sql.lower()
    assert "alter column quote drop not null" in base_visual_sql.lower()
    assert "alter column start_offset drop not null" in base_visual_sql.lower()
    assert "alter column end_offset drop not null" in base_visual_sql.lower()
    assert "_actor_user_id uuid" in asset_sql
    assert "_checksum !~ '^[0-9a-fA-F]{64}$'" in asset_sql
    assert "(case _mime_type when 'image/png'" in asset_sql
    assert "revoke all on function public.get_visual_assets_for_revision(uuid, uuid)" in link_sql
    assert "grant execute on function public.get_visual_assets_for_revision(uuid, uuid) to service_role" in link_sql
    assert "get_visual_assets_for_revision(uuid)" not in link_sql
    assert "on conflict (org_id, checksum) do nothing" in asset_sql.lower()
    assert "creator','owner" in asset_sql
    assert "cleanup_new_visual_asset(uuid,uuid,text,uuid)" in asset_sql
    assert "m.user_id = _actor_user_id" in asset_sql
    assert "m.roles && array['creator','owner']::public.app_role[]" in asset_sql
    assert "revoke all on function public.create_visual_asset" in asset_sql.lower()
    assert "to service_role" in asset_sql
    assert "different revision" in asset_sql
    assert "revoke insert, update, delete on public.visual_assets from anon, authenticated" in asset_sql.lower()
    assert "_actor_user_id uuid" in asset_sql[asset_sql.index("create or replace function public.cleanup_new_visual_asset"):asset_sql.index("-- Prevent direct authenticated writes")]
    assert "visual_asset_contents" in asset_sql
    assert "split_part(name, '/', 1)" in asset_sql
    assert "drop function if exists public.create_visual_asset(uuid,text,text,int,int,text,jsonb)" in asset_sql.lower()
    assert "drop function if exists public.engine_fail_review" not in asset_sql.lower()
    assert "for update" in review_sql.lower()
    assert "claim_token_mismatch" in review_sql
    assert "visual_asset_not_linked_to_review_revision" in review_sql
    assert "vac.revision_id = _review.revision_id" in review_sql
    assert "vac.content_id = _content_id" in review_sql
    assert "jsonb_object_keys" in review_sql
    assert "jsonb_typeof(_region->_region_key) <> 'number'" in review_sql
    assert "drop function public.engine_fail_review" not in review_sql.lower()
    assert "create or replace function public.engine_fail_review" not in review_sql.lower()
    assert "create or replace function public.engine_fail_review(" in lease_sql
    assert "_claim_token uuid" in lease_sql
    assert "for update" in lease_sql.lower()
    assert "claim_token_mismatch" in lease_sql
    assert "set status = 'failed'" in lease_sql
    assert "claim_token = null" in lease_sql
    assert "claimed_at = null" in lease_sql
    assert "grant execute on function public.engine_fail_review(uuid,text,uuid) to service_role" in lease_sql
    assert "drop function if exists public.engine_fail_review(uuid, text)" in historical_visual_sql
    assert "create or replace function public.engine_fail_review(" in historical_visual_sql
    executable_review_sql = review_sql.split("-- engine_fail_review preservation audit:", 1)[0]
    assert "engine_fail_review" not in executable_review_sql.lower()


class _FakeUpload:
    content_type = "image/png"
    filename = "test.png"

    def __init__(self):
        self._chunks = [b"image-bytes", b""]

    async def read(self, size):
        return self._chunks.pop(0)

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_visual_upload_success_passes_actor_and_returns_metadata(monkeypatch):
    from app.api import imports
    from app.auth import supabase as supabase_module
    org_id, actor_id, asset_id = uuid4(), uuid4(), uuid4()
    row = asset_row(asset_id, org_id, f"{org_id}/{asset_id}.png")
    result = VisualAssetUploadResult(asset_id, row["storage_path"], metadata(), row, True)
    service = MagicMock()
    service.validate_upload.return_value = (True, "")
    service.upload_asset.return_value = result
    service.get_signed_url.return_value = "https://signed.example/image"
    db = MagicMock()
    monkeypatch.setattr(imports, "get_visual_asset_service", lambda: service)
    monkeypatch.setattr(supabase_module, "get_supabase_client", lambda: db)
    user = SimpleNamespace(org_id=str(org_id), user_id=str(actor_id))

    response = await imports.import_visual(_FakeUpload(), uuid4(), uuid4(), user)

    assert response["asset_id"] == str(asset_id)
    assert response["signed_url"].startswith("https://")
    assert db.link_visual_asset_to_content.call_args.kwargs["actor_user_id"] == str(actor_id)
    service.cleanup_new_asset.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("created", [True, False])
async def test_visual_upload_link_failure_only_cleans_new_asset(monkeypatch, created):
    from app.api import imports
    from app.auth import supabase as supabase_module
    org_id, actor_id, asset_id = uuid4(), uuid4(), uuid4()
    row = asset_row(asset_id, org_id, f"{org_id}/{asset_id}.png")
    result = VisualAssetUploadResult(asset_id, row["storage_path"], metadata(), row, created)
    service = MagicMock()
    service.validate_upload.return_value = (True, "")
    service.upload_asset.return_value = result
    service.get_signed_url.return_value = "https://signed.example/image"
    db = MagicMock()
    db.link_visual_asset_to_content.side_effect = RuntimeError("link rejected")
    monkeypatch.setattr(imports, "get_visual_asset_service", lambda: service)
    monkeypatch.setattr(supabase_module, "get_supabase_client", lambda: db)
    user = SimpleNamespace(org_id=str(org_id), user_id=str(actor_id))

    with pytest.raises(RuntimeError, match="link rejected"):
        await imports.import_visual(_FakeUpload(), uuid4(), uuid4(), user)
    if created:
        service.cleanup_new_asset.assert_called_once()
    else:
        service.cleanup_new_asset.assert_not_called()


@pytest.mark.asyncio
async def test_visual_upload_signed_url_failure_cleans_only_new_asset(monkeypatch):
    from app.api import imports
    org_id, actor_id, asset_id = uuid4(), uuid4(), uuid4()
    row = asset_row(asset_id, org_id, f"{org_id}/{asset_id}.png")
    result = VisualAssetUploadResult(asset_id, row["storage_path"], metadata(), row, True)
    service = MagicMock()
    service.validate_upload.return_value = (True, "")
    service.upload_asset.return_value = result
    service.get_signed_url.side_effect = RuntimeError("signing failed")
    monkeypatch.setattr(imports, "get_visual_asset_service", lambda: service)
    user = SimpleNamespace(org_id=str(org_id), user_id=str(actor_id))

    with pytest.raises(RuntimeError, match="signing failed"):
        await imports.import_visual(_FakeUpload(), uuid4(), uuid4(), user)
    service.cleanup_new_asset.assert_called_once()


@pytest.mark.asyncio
async def test_revision_rpc_database_error_propagates():
    analyzer = VisualAnalyzer()
    org_id = uuid4()
    analyzer.supabase = MagicMock()
    analyzer.supabase.get_revision.return_value = {"content_id": str(uuid4())}
    analyzer.supabase.get_content.return_value = {"org_id": str(org_id)}
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = RuntimeError("rpc unavailable")
    analyzer.supabase._get_client.return_value = client
    with pytest.raises(RuntimeError, match="rpc unavailable"):
        await analyzer.load_visual_assets_for_review(uuid4(), org_id)


@pytest.mark.asyncio
async def test_missing_revision_is_a_genuine_empty_asset_result():
    analyzer = VisualAnalyzer()
    analyzer.supabase = MagicMock()
    analyzer.supabase.get_revision.return_value = None
    assert await analyzer.load_visual_assets_for_review(uuid4(), uuid4()) == []


@pytest.mark.asyncio
async def test_vision_provider_unavailable_keeps_deterministic_findings():
    from app.models.pipeline import UnavailableError
    analyzer = VisualAnalyzer()
    asset_id, org_id = uuid4(), uuid4()
    analyzer.load_asset_bytes = AsyncMock(return_value=(b"image", "image/png", metadata()))
    analyzer._run_vision_analysis = AsyncMock(side_effect=UnavailableError("provider offline"))
    with patch("app.visual.analyzer.run_deterministic_visual_checks", return_value=["deterministic"]):
        result = await analyzer.analyze_assets(
            asset_ids=[asset_id], revision_text="draft", purpose="purpose",
            channel="web", visual_guidelines={"logo": {}}, org_id=org_id,
        )
    assert result.deterministic_findings == ["deterministic"]
    assert result.llm_status == "failed"
    assert "deterministic findings preserved" in result.warnings[0]


def test_supabase_visual_asset_lookup_scopes_by_org():
    from app.auth.supabase import SupabaseClient
    db = SupabaseClient()
    client = MagicMock()
    db._client = client
    row = asset_row(uuid4(), uuid4(), "org/asset.png")
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [row]
    found = db.get_visual_asset(row["id"], row["org_id"])
    assert found == row
    query = client.table.return_value.select.return_value.eq.return_value
    assert query.eq.call_args.args == ("org_id", row["org_id"])


@pytest.mark.asyncio
async def test_visual_pipeline_failure_uses_claim_token_failure_path(monkeypatch):
    from app.pipeline import orchestrator as module
    from app.pipeline.orchestrator import ReviewOrchestrator
    review_id, token, org_id, revision_id = str(uuid4()), uuid4(), str(uuid4()), str(uuid4())
    pipeline_input = SimpleNamespace(
        revision_id=revision_id, org_id=org_id, revision_text="draft",
        kit_id="kit", purpose="purpose", channel="web",
    )
    obj = ReviewOrchestrator.__new__(ReviewOrchestrator)
    obj._claim_review = AsyncMock(return_value=(True, token))
    obj._load_review_data = AsyncMock(return_value=pipeline_input)
    obj.loader = MagicMock()
    obj.loader.load_rules_and_facts.return_value = ([], [])
    obj.supabase = MagicMock()
    obj.supabase._get_client.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"visual_guidelines": {}}
    ]
    obj._load_visual_asset_ids = AsyncMock(return_value=[uuid4()])
    obj._run_deterministic_checks = AsyncMock(return_value=SimpleNamespace())
    obj._convert_deterministic_to_pipeline = MagicMock(return_value=([], []))
    obj._persist_failure = AsyncMock()
    monkeypatch.setattr(module, "run_visual_analysis", AsyncMock(side_effect=RuntimeError("asset download failed")))

    output = await obj.run_pipeline(review_id)

    assert output.error == "asset download failed"
    obj._persist_failure.assert_awaited_once_with(review_id, "asset download failed", token)


@pytest.mark.asyncio
async def test_visual_guidelines_lookup_failure_fails_closed_and_persists_failure():
    from app.pipeline.orchestrator import ReviewOrchestrator

    review_id, token, org_id, revision_id = str(uuid4()), uuid4(), str(uuid4()), str(uuid4())
    pipeline_input = SimpleNamespace(
        revision_id=revision_id, org_id=org_id, revision_text="draft",
        kit_id="kit", purpose="purpose", channel="web",
    )
    obj = ReviewOrchestrator.__new__(ReviewOrchestrator)
    obj._claim_review = AsyncMock(return_value=(True, token))
    obj._load_review_data = AsyncMock(return_value=pipeline_input)
    obj.loader = MagicMock()
    obj.loader.load_rules_and_facts.return_value = ([], [])
    obj.supabase = MagicMock()
    obj.supabase._get_client.return_value.table.return_value.select.return_value.eq.return_value.execute.side_effect = RuntimeError(
        "database unavailable"
    )
    obj._load_visual_asset_ids = AsyncMock(return_value=[uuid4()])
    obj._persist_failure = AsyncMock()

    output = await obj.run_pipeline(review_id)

    assert output.error == "Failed to load visual guidelines for review"
    obj._persist_failure.assert_awaited_once_with(
        review_id, "Failed to load visual guidelines for review", token
    )


def test_storage_upload_failure_does_not_attempt_database_or_storage_cleanup():
    service, client, bucket = service_with_client()
    org_id, user_id = uuid4(), uuid4()
    service.strip_exif = MagicMock(return_value=b"canonical")
    service.extract_extended_metadata = MagicMock(return_value=metadata())
    service.get_asset_by_checksum = MagicMock(return_value=None)
    bucket.upload.side_effect = RuntimeError("storage upload rejected")
    with pytest.raises(RuntimeError, match="storage upload rejected"):
        service.upload_asset(org_id, user_id, b"source", "image/png", "x.png")
    bucket.remove.assert_not_called()
    client.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_visual_upload_storage_failure_does_not_cleanup_nonexistent_result(monkeypatch):
    from app.api import imports
    org_id, actor_id = uuid4(), uuid4()
    service = MagicMock()
    service.validate_upload.return_value = (True, "")
    service.upload_asset.side_effect = RuntimeError("storage upload rejected")
    monkeypatch.setattr(imports, "get_visual_asset_service", lambda: service)
    user = SimpleNamespace(org_id=str(org_id), user_id=str(actor_id))
    with pytest.raises(RuntimeError, match="storage upload rejected"):
        await imports.import_visual(_FakeUpload(), uuid4(), uuid4(), user)
    service.cleanup_new_asset.assert_not_called()
