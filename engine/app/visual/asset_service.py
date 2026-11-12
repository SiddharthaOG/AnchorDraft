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
class VisualAssetUploadResult:
    asset_id: UUID
    storage_path: str
    metadata: "VisualAssetMetadata"
    asset_record: dict
    created: bool


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
            logger.warning("perceptual_hash_failed", extra={"error_type": type(e).__name__})

        # Extract dominant colors (simple k-means style using PIL)
        try:
            metadata.dominant_colors = self._extract_dominant_colors(img)
        except Exception as e:
            logger.warning("dominant_colors_failed", extra={"error_type": type(e).__name__})

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
        filename: str = "image",
    ) -> VisualAssetUploadResult:
        """Upload or reuse a visual asset; only newly uploaded objects are cleaned up."""
        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValueError(f"Unsupported MIME type: {mime_type}")
        if not file_bytes or len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError("Image is empty or exceeds the 10 MB limit")

        clean_bytes = self.strip_exif(file_bytes, mime_type)
        metadata = self.extract_extended_metadata(clean_bytes, mime_type)
        existing = self.get_asset_by_checksum(org_id, metadata.checksum)
        if existing:
            return self._upload_result(existing, metadata, created=False)

        client = self._get_client()
        asset_id = uuid4()
        storage_path = f"{org_id}/{asset_id}{ALLOWED_MIME_TYPES[mime_type]}"
        bucket = client.storage.from_("visual-assets")
        uploaded = False
        record_creation_attempted = False
        try:
            bucket.upload(
                path=storage_path,
                file=clean_bytes,
                file_options={"content-type": mime_type, "cache-control": "3600", "upsert": "false"},
            )
            uploaded = True
            record_creation_attempted = True
            asset_record = self.create_asset_record(
                org_id=org_id, user_id=user_id, storage_path=storage_path,
                mime_type=mime_type, metadata=metadata,
            )
            actual_id = UUID(str(asset_record["id"]))
            actual_path = asset_record["storage_path"]
            created = actual_id == asset_id and actual_path == storage_path
            if not created:
                # A concurrent request won the checksum race. Remove only this request's object.
                try:
                    bucket.remove([storage_path])
                except Exception as cleanup_error:
                    logger.error(
                        "visual_asset_race_object_cleanup_failed",
                        extra={"path": storage_path, "error_type": type(cleanup_error).__name__},
                    )
                    raise RuntimeError(f"Failed to remove duplicate-race storage object {storage_path}") from cleanup_error
                return self._upload_result(asset_record, metadata, created=False)
            return self._upload_result(asset_record, metadata, created=True)
        except Exception:
            if uploaded:
                try:
                    # The guarded RPC distinguishes an uncreated object from a DB row
                    # that is linked/shared. Never delete storage if authorization is uncertain.
                    removed = self.cleanup_new_asset(org_id, asset_id, storage_path, user_id) if record_creation_attempted else False
                    if not removed:
                        bucket.remove([storage_path])
                except Exception as cleanup_error:
                    logger.error(
                        "visual_asset_upload_cleanup_failed",
                        extra={"path": storage_path, "error_type": type(cleanup_error).__name__},
                    )
            raise

    @staticmethod
    def _upload_result(asset_record: dict, metadata: VisualAssetMetadata, created: bool) -> VisualAssetUploadResult:
        if not isinstance(asset_record, dict) or not asset_record.get("id") or not asset_record.get("storage_path"):
            raise RuntimeError("Visual asset record is missing its ID or storage path")
        return VisualAssetUploadResult(
            asset_id=UUID(str(asset_record["id"])),
            storage_path=asset_record["storage_path"],
            metadata=metadata,
            asset_record=asset_record,
            created=created,
        )

    def get_asset_by_checksum(self, org_id: UUID, checksum: str) -> Optional[dict]:
        """Get an existing asset; database errors are not treated as cache misses."""
        response = (
            self._get_client().table("visual_assets").select("*")
            .eq("org_id", str(org_id)).eq("checksum", checksum).limit(1).execute()
        )
        return response.data[0] if response.data else None

    def create_asset_record(
        self, org_id: UUID, user_id: UUID, storage_path: str,
        mime_type: str, metadata: VisualAssetMetadata,
    ) -> dict:
        """Create through the actor-aware RPC and fetch the resulting row."""
        client = self._get_client()
        try:
            response = client.rpc("create_visual_asset", {
                "_org_id": str(org_id),
                "_actor_user_id": str(user_id),
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
            raw_id = response.data
            if isinstance(raw_id, list):
                raw_id = raw_id[0] if raw_id else None
            if isinstance(raw_id, dict):
                raw_id = raw_id.get("create_visual_asset") or raw_id.get("id")
            if not raw_id:
                raise ValueError("create_visual_asset returned an empty UUID")
            asset_id = UUID(str(raw_id))
            row = (
                client.table("visual_assets").select("*")
                .eq("id", str(asset_id)).eq("org_id", str(org_id)).limit(1).execute()
            )
            if not row.data:
                raise LookupError(f"Created visual asset {asset_id} could not be fetched")
            required = {"id", "org_id", "storage_path", "mime_type", "width", "height", "checksum", "metadata"}
            missing = required.difference(row.data[0])
            if missing:
                raise ValueError(f"Visual asset row is missing fields: {sorted(missing)}")
            return row.data[0]
        except Exception as exc:
            raise RuntimeError(f"Failed to create/fetch visual asset record: {exc}") from exc

    def cleanup_new_asset(self, org_id: UUID, asset_id: UUID, storage_path: str, user_id: UUID) -> bool:
        """Atomically delete only an unlinked asset owned by this org, then its object."""
        try:
            response = self._get_client().rpc("cleanup_new_visual_asset", {
                "_org_id": str(org_id),
                "_asset_id": str(asset_id),
                "_storage_path": storage_path,
                "_actor_user_id": str(user_id),
            }).execute()
            removed_path = response.data
            if isinstance(removed_path, list):
                removed_path = removed_path[0] if removed_path else None
            if isinstance(removed_path, dict):
                removed_path = removed_path.get("cleanup_new_visual_asset")
            if removed_path:
                self._get_client().storage.from_("visual-assets").remove([removed_path])
                return True
            return False
        except Exception as exc:
            raise RuntimeError(f"Safe cleanup refused or failed for visual asset {asset_id}: {exc}") from exc

    def get_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Generate a non-empty signed URL or raise."""
        try:
            response = self._get_client().storage.from_("visual-assets").create_signed_url(
                path=storage_path, expires_in=expires_in,
            )
            signed_url = None
            if isinstance(response, dict):
                signed_url = response.get("signedURL") or response.get("signedUrl")
            if not isinstance(signed_url, str) or not signed_url.strip():
                raise ValueError("Storage returned no signed URL")
            return signed_url
        except Exception as exc:
            raise RuntimeError(f"Failed to create signed URL for {storage_path}: {exc}") from exc

    def delete_asset(self, org_id: UUID, asset_id: UUID) -> bool:
        """Delete only an unlinked asset through the guarded cleanup RPC."""
        response = (
            self._get_client().table("visual_assets").select("storage_path,uploaded_by")
            .eq("id", str(asset_id)).eq("org_id", str(org_id)).limit(1).execute()
        )
        if not response.data:
            return False
        return self.cleanup_new_asset(
            org_id, asset_id, response.data[0]["storage_path"], UUID(response.data[0]["uploaded_by"])
        )


# Global instance
_visual_asset_service: Optional[VisualAssetService] = None


def get_visual_asset_service() -> VisualAssetService:
    """Get the global visual asset service instance."""
    global _visual_asset_service
    if _visual_asset_service is None:
        _visual_asset_service = VisualAssetService()
    return _visual_asset_service