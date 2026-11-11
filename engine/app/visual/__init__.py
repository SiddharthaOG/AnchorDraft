"""Visual brand compliance analysis package."""

from app.visual.asset_service import (
    VisualAssetService,
    VisualAssetMetadata,
    VisualAssetUploadResult,
    get_visual_asset_service,
)
from app.visual.deterministic import (
    VisualGuideline,
    VisualFindingCandidate,
    parse_visual_guidelines,
    run_deterministic_visual_checks,
    check_palette_compliance,
    check_contrast_compliance,
    check_logo_compliance,
)
from app.visual.analyzer import (
    VisualAnalyzer,
    VisualAnalysisResult,
    run_visual_analysis,
)
from app.visual.vision_providers import (
    GroqVisionProvider,
    GeminiVisionProvider,
    FakeVisionProvider,
    VISION_SYSTEM_INSTRUCTION,
    VISUAL_OUTPUT_SCHEMA,
    build_vision_user_content,
)

__all__ = [
    # Asset service
    "VisualAssetService",
    "VisualAssetMetadata",
    "VisualAssetUploadResult",
    "get_visual_asset_service",
    # Deterministic
    "VisualGuideline",
    "VisualFindingCandidate",
    "parse_visual_guidelines",
    "run_deterministic_visual_checks",
    "check_palette_compliance",
    "check_contrast_compliance",
    "check_logo_compliance",
    # Analyzer
    "VisualAnalyzer",
    "VisualAnalysisResult",
    "run_visual_analysis",
    # Vision providers
    "GroqVisionProvider",
    "GeminiVisionProvider",
    "FakeVisionProvider",
    "VISION_SYSTEM_INSTRUCTION",
    "VISUAL_OUTPUT_SCHEMA",
    "build_vision_user_content",
]