"""Visual analyzer coordinating deterministic and model-assisted visual checks."""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Set
from uuid import UUID

from app.visual.asset_service import get_visual_asset_service, VisualAssetMetadata
from app.visual.deterministic import (
    VisualGuideline,
    VisualFindingCandidate,
    parse_visual_guidelines,
    run_deterministic_visual_checks,
)
from app.visual.vision_providers import (
    FakeVisionProvider,
    GeminiVisionProvider,
    GroqVisionProvider,
    VISION_SYSTEM_INSTRUCTION,
    VISUAL_OUTPUT_SCHEMA,
    build_vision_user_content,
)
from app.llm.provider_factory import get_provider_with_fallback
from app.llm.prompt_builder import generate_nonce
from app.models.pipeline import (
    ProviderRequest,
    ModelFindingCandidate,
    ProviderError,
    RateLimitedError,
    TimeoutError,
    UnavailableError,
    BadOutputError,
    BlockedError,
)
from app.auth.supabase import get_supabase_client

logger = logging.getLogger(__name__)


@dataclass
class VisualAnalysisResult:
    """Result of visual analysis for one or more assets."""
    deterministic_findings: List[VisualFindingCandidate]
    model_findings: List[ModelFindingCandidate]
    llm_status: str  # "ok", "skipped", "failed"
    warnings: List[str]
    raw_model_count: int
    dropped_model_count: int


class VisualAnalyzer:
    """Coordinates deterministic and model-assisted visual analysis."""

    def __init__(self):
        self.asset_service = get_visual_asset_service()
        self.supabase = get_supabase_client()

    async def load_visual_assets_for_review(self, revision_id: UUID, org_id: UUID) -> List[dict]:
        """Load visual assets explicitly associated with a revision.

        Uses the revision-specific RPC to retrieve only assets explicitly linked
        to this revision (or its parent content), enforcing organization isolation.
        """
        try:
            def fetch_assets():
                revision = self.supabase.get_revision(str(revision_id))
                if not revision:
                    return []
                content = self.supabase.get_content(str(revision["content_id"]))
                if not content or str(content.get("org_id")) != str(org_id):
                    raise ValueError("Revision does not belong to the expected organization")
                return self.supabase._get_client().rpc(
                    "get_visual_assets_for_revision",
                    {"_revision_id": str(revision_id), "_org_id": str(org_id)},
                ).execute()
            response = await asyncio.to_thread(fetch_assets)
            if isinstance(response, list):
                return response
            return response.data or []
        except Exception as e:
            logger.error("load_visual_assets_for_review_failed", extra={"revision_id": str(revision_id), "error": str(e)})
            # Don't silently return empty list on failure - propagate the error
            raise

    async def load_asset_bytes(self, asset_id: UUID, org_id: UUID) -> tuple[bytes, str, VisualAssetMetadata]:
        """Load asset bytes and metadata from storage.

        Args:
            asset_id: UUID of the visual asset to load.
            org_id: Organization ID for authorization check.

        Returns:
            Tuple of (file_bytes, mime_type, metadata).

        Raises:
            ValueError: If asset not found or access denied.
            RuntimeError: If storage download fails.
        """
        asset_record = await asyncio.to_thread(
            self.supabase.get_visual_asset, str(asset_id), str(org_id)
        )
        if not asset_record:
            raise ValueError(f"Visual asset {asset_id} not found")

        # Verify asset belongs to the expected organization
        storage_path = asset_record.get("storage_path")
        mime_type = asset_record.get("mime_type")
        if not storage_path or mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError(f"Visual asset {asset_id} has invalid storage metadata")

        # Download from storage using service-role client off the event loop.
        try:
            file_bytes = await asyncio.to_thread(
                lambda: self.supabase._get_client().storage.from_("visual-assets").download(storage_path)
            )
            if not isinstance(file_bytes, (bytes, bytearray)) or not file_bytes:
                raise ValueError("Storage returned empty or invalid image bytes")
        except Exception as e:
            logger.error("asset_download_failed", extra={"asset_id": str(asset_id), "error": str(e)})
            raise RuntimeError(f"Failed to download asset {asset_id}: {e}") from e

        # Build metadata from asset record
        raw_metadata = asset_record.get("metadata")
        if not isinstance(raw_metadata, dict):
            raise ValueError(f"Visual asset {asset_id} has malformed metadata")
        try:
            metadata = VisualAssetMetadata(
                width=int(asset_record["width"]),
                height=int(asset_record["height"]),
                mime_type=mime_type,
                checksum=str(asset_record["checksum"]),
                palette=raw_metadata.get("palette"),
                dominant_colors=raw_metadata.get("dominant_colors"),
                perceptual_hash=raw_metadata.get("perceptual_hash"),
            )
            if metadata.width <= 0 or metadata.height <= 0 or not metadata.checksum:
                raise ValueError("invalid dimensions or checksum")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Visual asset {asset_id} has malformed metadata: {exc}") from exc

        return bytes(file_bytes), mime_type, metadata

    async def analyze_assets(
        self,
        asset_ids: List[UUID],
        revision_text: str,
        purpose: str,
        channel: str,
        visual_guidelines: dict,
        org_id: UUID,
        approved_logo_hashes: List[str] = None,
    ) -> VisualAnalysisResult:
        """
        Analyze multiple visual assets for brand compliance.

        Args:
            asset_ids: List of visual asset UUIDs to analyze.
            revision_text: The text content of the revision.
            purpose: Creator's stated purpose.
            channel: Content channel.
            visual_guidelines: Parsed visual guidelines from brand kit.
            org_id: Organization ID supplied by the claimed review pipeline.
            approved_logo_hashes: List of approved logo perceptual hashes.

        Returns:
            VisualAnalysisResult with all findings.
        """
        if not asset_ids:
            return VisualAnalysisResult(
                deterministic_findings=[],
                model_findings=[],
                llm_status="skipped",
                warnings=["No visual assets to analyze"],
                raw_model_count=0,
                dropped_model_count=0,
            )

        all_deterministic = []
        all_model_candidates = []
        warnings = []

        # Load assets and run deterministic checks
        assets_data = []
        for asset_id in asset_ids:
            try:
                file_bytes, mime_type, metadata = await self.load_asset_bytes(asset_id, org_id)
                assets_data.append({
                    "asset_id": asset_id,
                    "file_bytes": file_bytes,
                    "mime_type": mime_type,
                    "metadata": metadata,
                })
            except Exception as e:
                logger.error("asset_load_failed", extra={"asset_id": str(asset_id), "error": str(e)})
                raise ValueError(f"Failed to load asset {asset_id}: {e}") from e

        # Run deterministic checks on all assets
        guidelines = parse_visual_guidelines(visual_guidelines)
        approved_hashes = approved_logo_hashes or visual_guidelines.get("logo", {}).get("approved_hashes", [])

        for asset_data in assets_data:
            det_findings = run_deterministic_visual_checks(
                asset_id=asset_data["asset_id"],
                file_bytes=asset_data["file_bytes"],
                mime_type=asset_data["mime_type"],
                guidelines=guidelines,
                approved_logo_hashes=approved_hashes,
            )
            all_deterministic.extend(det_findings)

        # If no visual guidelines for model analysis, skip
        if not visual_guidelines:
            return VisualAnalysisResult(
                deterministic_findings=all_deterministic,
                model_findings=[],
                llm_status="skipped",
                warnings=warnings + ["No visual guidelines configured for model analysis"],
                raw_model_count=0,
                dropped_model_count=0,
            )

        # Run model-assisted vision analysis
        try:
            model_findings = await self._run_vision_analysis(
                assets_data=assets_data,
                revision_text=revision_text,
                purpose=purpose,
                channel=channel,
                visual_guidelines=visual_guidelines,
                approved_hashes=approved_hashes,
            )
            all_model_candidates = model_findings
            llm_status = "ok"
        except (RateLimitedError, TimeoutError, UnavailableError, BadOutputError, BlockedError, ProviderError) as e:
            logger.warning("vision_analysis_failed", extra={"error_type": type(e).__name__, "error": str(e)})
            llm_status = "failed"
            warnings.append(f"Vision analysis failed: {type(e).__name__} - deterministic findings preserved")
            all_model_candidates = []
        except Exception as e:
            logger.exception("vision_analysis_unexpected_error", extra={"error": str(e)})
            llm_status = "failed"
            warnings.append(f"Vision analysis error: deterministic findings preserved")
            all_model_candidates = []

        return VisualAnalysisResult(
            deterministic_findings=all_deterministic,
            model_findings=all_model_candidates,
            llm_status=llm_status,
            warnings=warnings,
            raw_model_count=len(all_model_candidates),
            dropped_model_count=0,  # Will be updated after validation
        )

    async def _run_vision_analysis(
        self,
        assets_data: List[dict],
        revision_text: str,
        purpose: str,
        channel: str,
        visual_guidelines: dict,
        approved_hashes: List[str],
    ) -> List[ModelFindingCandidate]:
        """Run vision model analysis on assets."""
        provider = get_provider_with_fallback()

        # Check if provider supports vision (has generate_findings with images parameter)
        # For now, we'll use a simple check
        supports_vision = hasattr(provider, 'generate_findings') and 'images' in provider.generate_findings.__code__.co_varnames

        if not supports_vision:
            logger.info("vision_provider_not_supported", extra={"provider": provider.model})
            # Return empty - fallback to deterministic only
            return []

        # Prepare images for provider
        images = []
        asset_ids = []
        for asset_data in assets_data:
            images.append({
                "asset_id": str(asset_data["asset_id"]),
                "data": asset_data["file_bytes"],
                "mime_type": asset_data["mime_type"],
            })
            asset_ids.append(str(asset_data["asset_id"]))

        # Build vision request
        nonce = generate_nonce()
        system_instruction = VISION_SYSTEM_INSTRUCTION.format(max_findings=25)
        user_content = build_vision_user_content(
            draft_text=revision_text,
            purpose=purpose,
            channel=channel,
            visual_guidelines=visual_guidelines,
            asset_ids=asset_ids,
            nonce=nonce,
        )

        provider_request = ProviderRequest(
            system_instruction=system_instruction,
            user_content=user_content,
            output_schema=VISUAL_OUTPUT_SCHEMA,
            randomness=0.1,
            output_limit=4096,
            timeout_seconds=60,  # Longer timeout for vision
        )

        # Call provider with images
        result = await provider.generate_findings(provider_request, images)

        # Parse model findings
        parsed = json.loads(result.raw_json)
        raw_findings = parsed.get("findings", [])

        model_candidates = []
        for finding in raw_findings:
            try:
                candidate = ModelFindingCandidate.model_validate(finding)
                model_candidates.append(candidate)
            except Exception as e:
                logger.warning("visual_finding_validation_failed", extra={"error": str(e), "finding": finding})

        return model_candidates


async def run_visual_analysis(
    asset_ids: List[UUID],
    revision_text: str,
    purpose: str,
    channel: str,
    visual_guidelines: dict,
    org_id: UUID,
    approved_logo_hashes: List[str] = None,
) -> VisualAnalysisResult:
    """Convenience function to run visual analysis."""
    analyzer = VisualAnalyzer()
    return await analyzer.analyze_assets(
        asset_ids=asset_ids,
        revision_text=revision_text,
        purpose=purpose,
        channel=channel,
        visual_guidelines=visual_guidelines,
        org_id=org_id,
        approved_logo_hashes=approved_logo_hashes,
    )