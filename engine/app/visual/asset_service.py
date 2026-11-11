"""Visual asset service for handling image uploads, validation, and storage."""

import hashlib
import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional
from uuid import UUID, uuid4

from PIL import Image
from supabase import create_client, Client

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# Allowed MIME types and their corresponding file extensions
ALLOWED_MIME_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@dataclass
class VisualAssetMetadata:
    """Metadata extracted from an uploaded visual asset."""
    width: int
    height: int
    mime_type: str
    checksum: str
    # Optional extended metadata
    palette: Optional[list[dict]] = None
    dominant_colors: Optional[list[dict]] = None
    perceptual_hash: Optional[str] = None


class VisualAssetService:
    """Service for managing visual assets in Supabase Storage and database."""

    def __init__(self):
        self._client: Optional[Client] = None

    def _get_client(self) -> Client:
        """Get or create the Supabase service-role client."""
        if self._client is None:
            settings = get_settings()
            if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
                raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured")
            self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        return self._client

    def validate_upload(self, file_bytes: bytes, supplied_mime: str) -> tuple[bool, str]:
        """
        Validate an uploaded file.

        Args:
            file_bytes: The raw file bytes.
            supplied_mime: The MIME type supplied by the client.

        Returns:
            Tuple of (is_valid, error_message).
        """
        # Check file size
        if len(file_bytes) > MAX_FILE_SIZE:
            return False, f"File size exceeds maximum of {MAX_FILE_SIZE // (1024*1024)} MB"

        if len(file_bytes) == 0:
            return False, "File is empty"

        # Verify actual file signature (magic bytes)
        actual_mime = self._detect_mime_from_bytes(file_bytes)
        if actual_mime not in ALLOWED_MIME_TYPES:
            return False, f"Unsupported file type. Allowed: {', '.join(ALLOWED_MIME_TYPES.keys())}"

        # Check if supplied MIME matches actual (warning only, not blocking)
        if supplied_mime != actual_mime:
            logger.warning(
                "mime_mismatch",
                extra={"supplied": supplied_mime, "actual": actual_mime},
            )

        # Try to open as image to verify it's valid
        try:
            img = Image.open(BytesIO(file_bytes))
            img.verify()  # Verify image integrity
            # Re-open after verify() since it consumes the stream
            img = Image.open(BytesIO(file_bytes))
            img.load()  # Force load to catch any decompression errors
        except Exception as e:
            return False, f"Invalid image file: {type(e).__name__}"

        return True, ""

    def _detect_mime_from_bytes(self, file_bytes: bytes) -> str:
        """Detect MIME type from file signature (magic bytes)."""
        if len(file_bytes) < 12:
            return "application/octet-stream"

        # PNG: 89 50 4E 47 0D 0A 1A 0A
        if file_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"

        # JPEG: FF D8 FF
        if file_bytes[:3] == b'\xff\xd8\xff':
            return "image/jpeg"

        # WebP: RIFF....WEBP
        if file_bytes[:4] == b'RIFF' and file_bytes[8:12] == b'WEBP':
            return "image/webp"

        return "application/octet-stream"

    def compute_checksum(self, file_bytes: bytes) -> str:
        """Compute SHA-256 checksum of file bytes."""
        return hashlib.sha256(file_bytes).hexdigest()

    def extract_metadata(self, file_bytes: bytes, mime_type: str) -> VisualAssetMetadata:
        """Extract metadata from image bytes."""
        img = Image.open(BytesIO(file_bytes))
        width, height = img.size

        # Convert to RGB if needed for analysis
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background for transparency
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        metadata = VisualAssetMetadata(
            width=width,
            height=height,
            mime_type=mime_type,
            checksum=self.compute_checksum(file_bytes),
        )

        return metadata

    def extract_extended_metadata(self, file_bytes: bytes, mime_type: str) -> VisualAssetMetadata:
        """Extract extended metadata including palette and perceptual hash."""
        metadata = self.extract_metadata(file_bytes, mime_type)

        img = Image.open(BytesIO(file_bytes))
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Extract perceptual hash
        try:
            import imagehash
            metadata.perceptual_hash = str(imagehash.phash(img))
        except Exception as e:
            logger.warning("perceptual_hash_failed", extra={"error": str(e)})

        # Extract dominant colors (simple k-means style using PIL)
        try:
            metadata.dominant_colors = self._extract_dominant_colors(img)
        except Exception as e:
            logger.warning("dominant_colors_failed", extra={"error": str(e)})

        return metadata

    def _extract_dominant_colors(self, img: Image.Image, num_colors: int = 5) -> list[dict]:
        """Extract dominant colors from image using simple quantization."""
        # Resize for faster processing
        small_img = img.resize((100, 100), Image.Resampling.LANCZOS)
        # Reduce colors
        quantized = small_img.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
        # Get palette
        palette = quantized.getpalette()
        # Count color frequencies
        color_counts = {}
        for y in range(quantized.height):
            for x in range(quantized.width):
                idx = quantized.getpixel((x, y))
                color_counts[idx] = color_counts.get(idx, 0) + 1

        # Sort by frequency
        sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

        dominant = []
        for idx, count in sorted_colors[:num_colors]:
            r = palette[idx * 3]
            g = palette[idx * 3 + 1]
            b = palette[idx * 3 + 2]
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            percentage = count / (quantized.width * quantized.height)
            dominant.append({
                "hex": hex_color,
                "rgb": [r, g, b],
                "percentage": round(percentage, 3),
            })

        return dominant

    def strip_exif(self, file_bytes: bytes, mime_type: str) -> bytes:
        """Strip EXIF and other metadata from image."""
        img = Image.open(BytesIO(file_bytes))

        # Get image data without EXIF
        data = list(img.getdata())
        clean_img = Image.new(img.mode, img.size)
        clean_img.putdata(data)

        # Save to bytes
        output = BytesIO()
        if mime_type == "image/png":
            clean_img.save(output, format="PNG", optimize=True)
        elif mime_type == "image/jpeg":
            clean_img.save(output, format="JPEG", quality=90, optimize=True)
        elif mime_type == "image/webp":
            clean_img.save(output, format="WEBP", quality=90, method=6)
        else:
            return file_bytes  # Return original if unknown

        return output.getvalue()

    def upload_asset(
        self,
        org_id: UUID,
        user_id: UUID,
        file_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> tuple[str, VisualAssetMetadata]:
        """
        Upload a visual asset to Supabase Storage.

        Returns:
            Tuple of (storage_path, metadata).
        """
        client = self._get_client()

        # Strip EXIF
        clean_bytes = self.strip_exif(file_bytes, mime_type)

        # Extract metadata
        metadata = self.extract_extended_metadata(clean_bytes, mime_type)

        # Generate storage path: org_id/uuid.ext
        ext = ALLOWED_MIME_TYPES[mime_type]
        asset_id = uuid4()
        storage_path = f"{org_id}/{asset_id}{ext}"

        # Upload to Supabase Storage
        bucket = client.storage.from_("visual-assets")
        try:
            bucket.upload(
                path=storage_path,
                file=clean_bytes,
                file_options={
                    "content-type": mime_type,
                    "cache-control": "3600",
                },
            )
        except Exception as e:
            # Check if it's a duplicate (same checksum)
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                # Try to get existing asset
                existing = self.get_asset_by_checksum(org_id, metadata.checksum)
                if existing:
                    return existing.storage_path, metadata
            raise RuntimeError(f"Failed to upload to storage: {e}")

        return storage_path, metadata

    def get_asset_by_checksum(self, org_id: UUID, checksum: str) -> Optional[dict]:
        """Get existing asset by checksum (for deduplication)."""
        client = self._get_client()
        try:
            response = client.table("visual_assets").select("*").eq("org_id", str(org_id)).eq("checksum", checksum).execute()
            if response.data:
                return response.data[0]
        except Exception:
            pass
        return None

    def create_asset_record(
        self,
        org_id: UUID,
        user_id: UUID,
        storage_path: str,
        mime_type: str,
        metadata: VisualAssetMetadata,
    ) -> dict:
        """Create visual asset record in database via RPC."""
        client = self._get_client()
        try:
            response = client.rpc("create_visual_asset", {
                "_org_id": str(org_id),
                "_storage_path": storage_path,
                "_mime_type": mime_type,
                "_width": metadata.width,
                "_height": metadata.height,
                "_checksum": metadata.checksum,
                "_metadata": {
                    "palette": metadata.palette,
                    "dominant_colors": metadata.dominant_colors,
                    "perceptual_hash": metadata.perceptual_hash,
                },
            }).execute()
            if response.data:
                return response.data
        except Exception as e:
            logger.error("create_asset_record_failed", extra={"error": str(e)})
        return None

    def get_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Generate a signed URL for accessing the asset."""
        client = self._get_client()
        try:
            response = client.storage.from_("visual-assets").create_signed_url(
                path=storage_path,
                expires_in=expires_in,
            )
            if response and "signedURL" in response:
                return response["signedURL"]
        except Exception as e:
            logger.error("signed_url_failed", extra={"error": str(e), "path": storage_path})
        return ""

    def delete_asset(self, org_id: UUID, asset_id: UUID) -> bool:
        """Delete a visual asset from storage and database."""
        client = self._get_client()
        try:
            # Get asset record first
            response = client.table("visual_assets").select("storage_path").eq("id", str(asset_id)).eq("org_id", str(org_id)).execute()
            if not response.data:
                return False

            storage_path = response.data[0]["storage_path"]

            # Delete from storage
            bucket = client.storage.from_("visual-assets")
            bucket.remove([storage_path])

            # Delete from database (cascades to findings via FK)
            client.table("visual_assets").delete().eq("id", str(asset_id)).eq("org_id", str(org_id)).execute()

            return True
        except Exception as e:
            logger.error("delete_asset_failed", extra={"error": str(e), "asset_id": str(asset_id)})
            return False


# Global instance
_visual_asset_service: Optional[VisualAssetService] = None


def get_visual_asset_service() -> VisualAssetService:
    """Get the global visual asset service instance."""
    global _visual_asset_service
    if _visual_asset_service is None:
        _visual_asset_service = VisualAssetService()
    return _visual_asset_service