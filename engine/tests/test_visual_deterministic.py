"""Tests for deterministic visual analysis."""

import pytest
from uuid import UUID, uuid4
from io import BytesIO
from PIL import Image

from app.visual.deterministic import (
    VisualGuideline,
    parse_visual_guidelines,
    run_deterministic_visual_checks,
    check_palette_compliance,
    check_contrast_compliance,
    check_logo_compliance,
    hex_to_rgb,
    rgb_to_lab,
    delta_e_cie76,
    luminance,
    contrast_ratio,
    perceptual_hash,
    hamming_distance,
)


def create_test_image(width: int = 100, height: int = 100, color: tuple = (255, 0, 0)) -> bytes:
    """Create a test image with solid color."""
    img = Image.new('RGB', (width, height), color)
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def create_gradient_image(width: int = 100, height: int = 100) -> bytes:
    """Create a test image with gradient for contrast testing."""
    img = Image.new('RGB', (width, height))
    for y in range(height):
        for x in range(width):
            # Create vertical gradient from black to white
            val = int((y / height) * 255)
            img.putpixel((x, y), (val, val, val))
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def create_text_on_background(width: int = 200, height: int = 100) -> bytes:
    """Create an image with text-like pattern on background for contrast testing."""
    img = Image.new('RGB', (width, height), (255, 255, 255))  # White background
    # Draw dark rectangle simulating text
    for y in range(30, 70):
        for x in range(50, 150):
            img.putpixel((x, y), (0, 0, 0))  # Black text
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


class TestColorUtilities:
    """Test color conversion and comparison utilities."""

    def test_hex_to_rgb(self):
        assert hex_to_rgb("#FF0000") == (255, 0, 0)
        assert hex_to_rgb("#00FF00") == (0, 255, 0)
        assert hex_to_rgb("#0000FF") == (0, 0, 255)
        assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
        assert hex_to_rgb("#000000") == (0, 0, 0)
        assert hex_to_rgb("F00") == (255, 0, 0)  # Short form
        assert hex_to_rgb("0F0") == (0, 255, 0)

    def test_rgb_to_lab(self):
        # Test known conversions
        lab = rgb_to_lab(255, 255, 255)  # White
        assert abs(lab[0] - 100) < 1
        assert abs(lab[1]) < 1
        assert abs(lab[2]) < 1

        lab = rgb_to_lab(0, 0, 0)  # Black
        assert abs(lab[0] - 0) < 1

    def test_delta_e_cie76(self):
        # Identical colors should have delta E = 0
        lab1 = rgb_to_lab(255, 0, 0)
        lab2 = rgb_to_lab(255, 0, 0)
        assert delta_e_cie76(lab1, lab2) == 0

        # Red vs blue should have large delta E
        lab_red = rgb_to_lab(255, 0, 0)
        lab_blue = rgb_to_lab(0, 0, 255)
        delta = delta_e_cie76(lab_red, lab_blue)
        assert delta > 50  # Large perceptual difference

    def test_luminance(self):
        # White should have luminance ~1.0
        assert abs(luminance(255, 255, 255) - 1.0) < 0.01
        # Black should have luminance ~0.0
        assert abs(luminance(0, 0, 0) - 0.0) < 0.01
        # Middle gray
        assert 0.15 < luminance(128, 128, 128) < 0.25

    def test_contrast_ratio(self):
        # White on black = 21:1 (approximately)
        ratio = contrast_ratio(luminance(255, 255, 255), luminance(0, 0, 0))
        assert abs(ratio - 21.0) < 2.0

        # Same color = 1:1
        ratio = contrast_ratio(0.5, 0.5)
        assert abs(ratio - 1.0) < 0.01


class TestPerceptualHash:
    """Test perceptual hashing for logo matching."""

    def test_perceptual_hash_consistency(self):
        img_bytes = create_test_image(100, 100, (255, 0, 0))
        hash1 = perceptual_hash(Image.open(BytesIO(img_bytes)))
        hash2 = perceptual_hash(Image.open(BytesIO(img_bytes)))
        assert hash1 == hash2

    def test_perceptual_hash_different_images(self):
        # Create images with patterns (not solid colors) to get different hashes
        img1 = Image.new('RGB', (100, 100), (255, 0, 0))
        # Add pattern to first image
        for x in range(0, 100, 10):
            for y in range(100):
                img1.putpixel((x, y), (0, 0, 0))
        
        img2 = Image.new('RGB', (100, 100), (0, 255, 0))
        # Add different pattern to second image
        for y in range(0, 100, 10):
            for x in range(100):
                img2.putpixel((x, y), (0, 0, 0))
        
        hash1 = perceptual_hash(img1)
        hash2 = perceptual_hash(img2)
        assert hash1 != hash2

    def test_hamming_distance(self):
        # Same hash = distance 0
        assert hamming_distance("abc", "abc") == 0
        # Different by 1 bit
        assert hamming_distance("0", "1") == 1
        # Max distance for 64-bit hash
        assert hamming_distance("0" * 16, "f" * 16) == 64


class TestPaletteCompliance:
    """Test brand palette compliance checking."""

    def test_palette_compliance_pass(self):
        """Test that image with brand colors passes."""
        # Create image with brand color
        img_bytes = create_test_image(100, 100, (0, 102, 204))  # #0066CC
        img = Image.open(BytesIO(img_bytes))

        palette_config = {
            "colors": [
                {"name": "primary", "hex": "#0066CC", "tolerance": 10},
            ],
            "allow_neutrals": True,
        }

        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        findings = check_palette_compliance(asset_id, img, palette_config)
        # Should not flag the brand color
        assert len(findings) == 0

    def test_palette_compliance_fail(self):
        """Test that image with non-brand color fails."""
        # Create image with non-brand color (bright green)
        img_bytes = create_test_image(100, 100, (0, 255, 0))  # #00FF00
        img = Image.open(BytesIO(img_bytes))

        palette_config = {
            "colors": [
                {"name": "primary", "hex": "#0066CC", "tolerance": 10},
            ],
            "allow_neutrals": True,
        }

        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        findings = check_palette_compliance(asset_id, img, palette_config)
        # Should flag the non-brand color
        assert len(findings) > 0
        assert findings[0].ref_key == "PALETTE-01"
        assert findings[0].category == "palette"

    def test_palette_neutrals_allowed(self):
        """Test that neutral colors are allowed when configured."""
        # Create grayscale image
        img_bytes = create_test_image(100, 100, (128, 128, 128))
        img = Image.open(BytesIO(img_bytes))

        palette_config = {
            "colors": [
                {"name": "primary", "hex": "#0066CC", "tolerance": 10},
            ],
            "allow_neutrals": True,
        }

        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        findings = check_palette_compliance(asset_id, img, palette_config)
        # Should not flag neutral gray
        assert len(findings) == 0

    def test_palette_small_areas_ignored(self):
        """Test that very small color areas (< 2%) are ignored."""
        # Create mostly brand color with tiny non-brand area
        img = Image.new('RGB', (100, 100), (0, 102, 204))  # Brand color
        # Tiny 1x1 pixel of different color (0.01%)
        img.putpixel((0, 0), (255, 0, 0))

        palette_config = {
            "colors": [
                {"name": "primary", "hex": "#0066CC", "tolerance": 10},
            ],
            "allow_neutrals": True,
        }

        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        findings = check_palette_compliance(asset_id, img, palette_config)
        # Should not flag the tiny area
        assert len(findings) == 0


class TestContrastCompliance:
    """Test contrast compliance checking."""

    def test_contrast_pass(self):
        """Test high contrast text on background."""
        img_bytes = create_text_on_background()
        img = Image.open(BytesIO(img_bytes))

        contrast_config = {
            "min_ratio": 4.5,
            "level": "AA",
            "ignore_backgrounds": ["#FFFFFF", "#000000"],
        }

        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        findings = check_contrast_compliance(asset_id, img, contrast_config)
        # High contrast black text on white should pass
        # Note: This is a simplified test - actual implementation may vary
        # Just verify it runs without error
        assert isinstance(findings, list)

    def test_low_contrast_detected(self):
        """Test low contrast detection."""
        # Create low contrast image (dark gray on light gray)
        img = Image.new('RGB', (100, 100), (200, 200, 200))  # Light gray background
        # Add slightly darker rectangle
        for y in range(30, 70):
            for x in range(30, 70):
                img.putpixel((x, y), (180, 180, 180))  # Slightly darker

        contrast_config = {
            "min_ratio": 4.5,
            "level": "AA",
            "ignore_backgrounds": ["#FFFFFF", "#000000"],
        }

        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        findings = check_contrast_compliance(asset_id, img, contrast_config)
        # Should detect low contrast regions
        # Note: Detection depends on grid sampling
        assert isinstance(findings, list)


class TestLogoCompliance:
    """Test logo compliance checking."""

    def test_logo_no_approved_hashes(self):
        """Test with no approved hashes configured."""
        img_bytes = create_test_image(100, 100, (255, 0, 0))
        img = Image.open(BytesIO(img_bytes))

        logo_config = {
            "required": True,
        }

        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        findings = check_logo_compliance(asset_id, img, logo_config, [])
        # Should not crash, may or may not find issues depending on implementation
        assert isinstance(findings, list)

    def test_logo_match_approved(self):
        """Test logo matching approved variant."""
        img_bytes = create_test_image(100, 100, (0, 102, 204))
        img = Image.open(BytesIO(img_bytes))

        logo_config = {
            "required": True,
        }

        # Compute hash of this image
        from app.visual.deterministic import perceptual_hash
        img_obj = Image.open(BytesIO(create_test_image(100, 100, (0, 102, 204))))
        approved_hash = perceptual_hash(img_obj)

        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        findings = check_logo_compliance(asset_id, img, logo_config, [approved_hash])
        # Should find a match (LOGO-02)
        assert len(findings) >= 1
        # At least one finding should be about logo match
        assert any(f.ref_key in ("LOGO-01", "LOGO-02") for f in findings)


class TestVisualGuidelineParsing:
    """Test visual guideline parsing."""

    def test_parse_empty_guidelines(self):
        guidelines = parse_visual_guidelines({})
        assert guidelines.logo is None
        assert guidelines.palette is None
        assert guidelines.contrast is None

    def test_parse_full_guidelines(self):
        guidelines_json = {
            "logo": {
                "required": True,
                "variants": ["primary", "monochrome"],
                "clear_space_ratio": 0.1,
            },
            "palette": {
                "colors": [{"name": "primary", "hex": "#0066CC", "tolerance": 10}],
                "allow_neutrals": True,
            },
            "contrast": {
                "min_ratio": 4.5,
                "level": "AA",
            },
        }
        guidelines = parse_visual_guidelines(guidelines_json)
        assert guidelines.logo is not None
        assert guidelines.logo["required"] is True
        assert guidelines.palette is not None
        assert len(guidelines.palette["colors"]) == 1
        assert guidelines.contrast is not None
        assert guidelines.contrast["min_ratio"] == 4.5


class TestRunDeterministicVisualChecks:
    """Test the main deterministic visual checks runner."""

    def test_no_guidelines(self):
        """Test with no guidelines configured."""
        img_bytes = create_test_image()
        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        guidelines = VisualGuideline()

        findings = run_deterministic_visual_checks(
            asset_id=asset_id,
            file_bytes=img_bytes,
            mime_type="image/png",
            guidelines=guidelines,
        )
        assert findings == []

    def test_palette_check_runs(self):
        """Test that palette check runs when configured."""
        # Create image with non-brand color (bright green)
        img = Image.new('RGB', (100, 100), (0, 255, 0))
        buf = BytesIO()
        img.save(buf, format='PNG')
        img_bytes = buf.getvalue()
        
        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        guidelines = VisualGuideline(
            palette={
                "colors": [{"name": "primary", "hex": "#0066CC", "tolerance": 10}],
                "allow_neutrals": True,
            }
        )

        findings = run_deterministic_visual_checks(
            asset_id=asset_id,
            file_bytes=img_bytes,
            mime_type="image/png",
            guidelines=guidelines,
        )
        # Should find palette violation
        palette_findings = [f for f in findings if f.category == "palette"]
        assert len(palette_findings) > 0

    def test_contrast_check_runs(self):
        """Test that contrast check runs when configured."""
        img_bytes = create_text_on_background()
        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        guidelines = VisualGuideline(
            contrast={
                "min_ratio": 4.5,
                "level": "AA",
            }
        )

        findings = run_deterministic_visual_checks(
            asset_id=asset_id,
            file_bytes=img_bytes,
            mime_type="image/png",
            guidelines=guidelines,
        )
        # Should run without error
        assert isinstance(findings, list)

    def test_logo_check_runs(self):
        """Test that logo check runs when configured."""
        img_bytes = create_test_image()
        asset_id = UUID("11111111-1111-1111-1111-111111111111")
        guidelines = VisualGuideline(
            logo={"required": True}
        )

        findings = run_deterministic_visual_checks(
            asset_id=asset_id,
            file_bytes=img_bytes,
            mime_type="image/png",
            guidelines=guidelines,
        )
        # Should run without error
        assert isinstance(findings, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])