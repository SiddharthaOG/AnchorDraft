"""Deterministic visual analysis for brand compliance checks."""

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Optional
from uuid import UUID

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class VisualGuideline:
    """Visual brand guidelines configuration."""
    # Logo configuration
    logo: Optional[dict] = None
    # Palette configuration
    palette: Optional[dict] = None
    # Contrast configuration
    contrast: Optional[dict] = None


@dataclass
class VisualFindingCandidate:
    """A candidate finding from deterministic visual analysis."""
    ref_key: str
    category: str
    severity: str
    asset_id: UUID
    region: dict  # Normalized bounding box: x, y, w, h (0-1)
    explanation: str
    suggestion: Optional[str] = None
    confidence: Optional[float] = None
    needs_reviewer: bool = False


def parse_visual_guidelines(guidelines_json: dict) -> VisualGuideline:
    """Parse visual guidelines from JSON."""
    return VisualGuideline(
        logo=guidelines_json.get("logo"),
        palette=guidelines_json.get("palette"),
        contrast=guidelines_json.get("contrast"),
    )


def rgb_to_lab(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB to CIELAB color space for perceptual distance."""
    # Normalize to 0-1
    r_lin = r / 255.0
    g_lin = g / 255.0
    b_lin = b / 255.0

    # sRGB to linear RGB
    def to_linear(c):
        if c <= 0.04045:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    r_lin = to_linear(r_lin)
    g_lin = to_linear(g_lin)
    b_lin = to_linear(b_lin)

    # Linear RGB to XYZ (D65)
    x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
    y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
    z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041

    # XYZ to LAB (D65 white point)
    x_ref, y_ref, z_ref = 0.95047, 1.00000, 1.08883

    def f(t):
        if t > 0.008856:
            return t ** (1/3)
        return 7.787 * t + 16/116

    fx = f(x / x_ref)
    fy = f(y / y_ref)
    fz = f(z / z_ref)

    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)

    return L, a, b


def delta_e_cie76(lab1: tuple, lab2: tuple) -> float:
    """Calculate CIE76 Delta E color difference."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    return np.sqrt((L1 - L2)**2 + (a1 - a2)**2 + (b1 - b2)**2)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c*2 for c in hex_color)
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def luminance(r: int, g: int, b: int) -> float:
    """Calculate relative luminance per WCAG 2.1."""
    def to_linear(c):
        # c is 0-255, normalize to 0-1
        c = c / 255.0
        if c <= 0.03928:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    r_lin = to_linear(r)
    g_lin = to_linear(g)
    b_lin = to_linear(b)

    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def contrast_ratio(lum1: float, lum2: float) -> float:
    """Calculate contrast ratio between two luminances."""
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def extract_dominant_colors_kmeans(img: Image.Image, k: int = 5) -> list[dict]:
    """Extract dominant colors using k-means clustering on pixel values."""
    # Convert to numpy array
    img_array = np.array(img.convert('RGB'))
    pixels = img_array.reshape(-1, 3).astype(np.float32)

    # Simple k-means (using numpy for speed)
    # Initialize centroids randomly
    np.random.seed(42)  # Deterministic
    indices = np.random.choice(len(pixels), k, replace=False)
    centroids = pixels[indices]

    for _ in range(10):  # Max 10 iterations
        # Assign pixels to nearest centroid
        distances = np.linalg.norm(pixels[:, np.newaxis] - centroids, axis=2)
        labels = np.argmin(distances, axis=1)

        # Update centroids
        new_centroids = np.zeros_like(centroids)
        for i in range(k):
            mask = labels == i
            if np.any(mask):
                new_centroids[i] = pixels[mask].mean(axis=0)

        if np.allclose(centroids, new_centroids):
            break
        centroids = new_centroids

    # Count cluster sizes
    labels = np.argmin(np.linalg.norm(pixels[:, np.newaxis] - centroids, axis=2), axis=1)
    counts = np.bincount(labels, minlength=k)
    total = len(pixels)

    # Sort by frequency
    order = np.argsort(-counts)
    centroids = centroids[order]
    counts = counts[order]

    colors = []
    for i, centroid in enumerate(centroids):
        if counts[i] == 0:
            continue
        r, g, b = centroid.astype(int)
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        percentage = counts[i] / total
        colors.append({
            "hex": hex_color,
            "rgb": [int(r), int(g), int(b)],
            "percentage": round(counts[i] / total, 3),
        })

    return colors


def check_palette_compliance(
    asset_id: UUID,
    img: Image.Image,
    palette_config: dict,
) -> list[VisualFindingCandidate]:
    """Check image colors against brand palette."""
    findings = []

    if not palette_config:
        return findings

    colors = palette_config.get("colors", [])
    tolerance = palette_config.get("tolerance", 10)  # Default Delta E tolerance
    allow_neutrals = palette_config.get("allow_neutrals", True)

    if not colors:
        return findings

    # Extract dominant colors from image
    dominant_colors = extract_dominant_colors_kmeans(img, k=8)

    for dom_color in dominant_colors:
        dom_rgb = dom_color["rgb"]
        dom_lab = rgb_to_lab(*dom_rgb)
        dom_percentage = dom_color["percentage"]

        # Skip very small color areas (< 2%)
        if dom_percentage < 0.02:
            continue

        # Check if color is neutral (low saturation)
        r, g, b = dom_color["rgb"]
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        saturation = (max_val - min_val) / max_val if max_val > 0 else 0

        if allow_neutrals and saturation < 0.1:
            continue  # Skip neutrals if allowed

        # Find closest brand color
        min_delta_e = float('inf')
        closest_brand = None

        for brand_color in colors:
            brand_hex = brand_color.get("hex", "")
            brand_tolerance = brand_color.get("tolerance", 10)
            try:
                brand_rgb = hex_to_rgb(brand_hex)
                brand_lab = rgb_to_lab(*brand_rgb)
                delta_e = delta_e_cie76(dom_lab, brand_lab)
                if delta_e < min_delta_e:
                    min_delta_e = delta_e
                    closest_brand = brand_color
            except Exception:
                continue

        # If no close brand color found within tolerance, flag it
        if closest_brand is None or min_delta_e > tolerance:
            # Find region where this color appears (simplified: whole image)
            findings.append(VisualFindingCandidate(
                ref_key="PALETTE-01",
                category="palette",
                severity="medium",
                asset_id=None,  # Will be set by caller
                region={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                explanation=(
                    f"Dominant color {dom_color['hex']} ({dom_percentage:.0%} of image) "
                    f"exceeds brand palette tolerance (Delta E: {min_delta_e:.1f} > {tolerance})"
                ),
                suggestion=f"Use approved brand color {closest_brand['hex'] if closest_brand else 'from palette'}",
                confidence=0.7,
                needs_reviewer=True,
            ))

    return findings


def check_contrast_compliance(
    asset_id: UUID,
    img: Image.Image,
    contrast_config: dict,
) -> list[VisualFindingCandidate]:
    """Check contrast ratios in image against WCAG guidelines."""
    findings = []

    if not contrast_config:
        return findings

    min_ratio = contrast_config.get("min_ratio", 4.5)
    ignore_backgrounds = contrast_config.get("ignore_backgrounds", ["#FFFFFF", "#000000"])

    # Convert to grayscale for analysis
    gray = img.convert('L')
    gray_array = np.array(gray)

    # Simple approach: sample regions and check local contrast
    # This is a simplified check - full implementation would need text detection
    height, width = gray_array.shape

    # Sample grid of regions
    grid_size = 8
    cell_h = height // grid_size
    cell_w = width // grid_size

    ignore_luminances = [luminance(*hex_to_rgb(bg)) for bg in ignore_backgrounds]

    for gy in range(grid_size):
        for gx in range(grid_size):
            y1 = gy * cell_h
            y2 = min((gy + 1) * cell_h, height)
            x1 = gx * cell_w
            x2 = min((gx + 1) * cell_w, width)

            if y2 <= y1 or x2 <= x1:
                continue

            cell = gray_array[y1:y2, x1:x2]
            if cell.size == 0:
                continue

            # Get min/max luminance in cell
            min_val = cell.min() / 255.0
            max_val = cell.max() / 255.0

            # Skip if region matches ignored backgrounds
            cell_lum = (min_val + max_val) / 2
            if any(abs(cell_lum - ig) < 0.05 for ig in ignore_luminances):
                continue

            # Calculate contrast
            if min_val > 0:
                ratio = (max_val + 0.05) / (min_val + 0.05)
            else:
                ratio = float('inf')

            if ratio < min_ratio and min_val > 0.02:  # Not pure black
                # Normalize region coordinates
                region = {
                    "x": x1 / width,
                    "y": y1 / height,
                    "w": (x2 - x1) / width,
                    "h": (y2 - y1) / height,
                }

                findings.append(VisualFindingCandidate(
                    ref_key="CONTRAST-01",
                    category="contrast",
                    severity="high" if ratio < 3.0 else "medium",
                    asset_id=None,  # Will be set by caller
                    region=region,
                    explanation=(
                        f"Contrast ratio {ratio:.1f}:1 in region falls below WCAG {contrast_config.get('level', 'AA')} "
                        f"minimum of {min_ratio}:1"
                    ),
                    suggestion="Increase contrast between foreground and background",
                    confidence=0.6,  # Lower confidence due to simplified detection
                    needs_reviewer=True,
                ))

    return findings


def perceptual_hash(img: Image.Image) -> str:
    """Compute perceptual hash (dHash) of image."""
    try:
        import imagehash
        return str(imagehash.dhash(img))
    except Exception:
        return ""


def hamming_distance(hash1: str, hash2: str) -> int:
    """Calculate Hamming distance between two hex hash strings."""
    if len(hash1) != len(hash2):
        return 64  # Max distance
    return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')


def check_logo_compliance(
    asset_id: UUID,
    img: Image.Image,
    logo_config: dict,
    approved_hashes: list[str],
) -> list[VisualFindingCandidate]:
    """Check logo usage compliance against approved variants."""
    findings = []

    if not logo_config:
        return findings

    required = logo_config.get("required", False)
    clear_space_ratio = logo_config.get("clear_space_ratio", 0.1)
    min_size_px = logo_config.get("min_size_px", 32)

    # Compute perceptual hash of submitted image
    submitted_hash = perceptual_hash(img)

    # Check against approved logo hashes
    best_match_distance = 64
    for approved_hash in approved_hashes:
        dist = hamming_distance(submitted_hash, approved_hash)
        if dist < best_match_distance:
            best_match_distance = dist

    # Threshold for "same logo" (adjustable)
    logo_threshold = 10  # Hamming distance threshold

    if best_match_distance > logo_threshold:
        # Logo doesn't match any approved variant
        if required:
            findings.append(VisualFindingCandidate(
                ref_key="LOGO-01",
                category="logo",
                severity="high",
                asset_id=None,
                region={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                explanation=(
                    f"Logo does not match any approved variant "
                    f"(perceptual hash distance: {best_match_distance})"
                ),
                suggestion="Use an approved logo variant from brand kit",
                confidence=0.75,
                needs_reviewer=True,
            ))
        return findings

    # If we have a match, check clear space and minimum size
    # This is simplified - full implementation would need logo localization
    # For now, we just report the match with moderate confidence
    findings.append(VisualFindingCandidate(
        ref_key="LOGO-02",
        category="logo",
        severity="low",
        asset_id=None,
        region={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        explanation=(
            f"Logo matches approved variant (hash distance: {best_match_distance}). "
            f"Manual verification of clear space and minimum size recommended."
        ),
        suggestion="Verify clear space ratio and minimum size in context",
        confidence=0.6,
        needs_reviewer=False,
    ))

    return findings


def run_deterministic_visual_checks(
    asset_id: UUID,
    file_bytes: bytes,
    mime_type: str,
    guidelines: VisualGuideline,
    approved_logo_hashes: list[str] = None,
) -> list[VisualFindingCandidate]:
    """
    Run all deterministic visual checks on an asset.

    Args:
        asset_id: UUID of the visual asset.
        file_bytes: Raw image bytes.
        mime_type: MIME type of the image.
        guidelines: Parsed visual guidelines.
        approved_logo_hashes: List of approved logo perceptual hashes.

    Returns:
        List of VisualFindingCandidate objects.
    """
    all_findings = []

    # Load image
    try:
        img = Image.open(BytesIO(file_bytes))
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
    except Exception as e:
        logger.error("visual_check_load_failed", extra={"asset_id": str(asset_id), "error_type": type(e).__name__})
        return []

    # Run checks based on guidelines
    if guidelines.palette:
        findings = check_palette_compliance(asset_id, img, guidelines.palette)
        for f in findings:
            f.asset_id = asset_id
        all_findings.extend(findings)

    if guidelines.contrast:
        findings = check_contrast_compliance(asset_id, img, guidelines.contrast)
        for f in findings:
            f.asset_id = asset_id
        all_findings.extend(findings)

    if guidelines.logo:
        logo_approved_hashes = approved_logo_hashes or guidelines.logo.get("approved_hashes", [])
        findings = check_logo_compliance(asset_id, img, guidelines.logo, logo_approved_hashes)
        for f in findings:
            f.asset_id = asset_id
        all_findings.extend(findings)

    return all_findings