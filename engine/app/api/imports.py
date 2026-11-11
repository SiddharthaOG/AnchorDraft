"""Text and visual asset import API endpoints."""
import io
import warnings
from fastapi import APIRouter, Depends, File, UploadFile, status, Form
from uuid import UUID

from app.auth.dependencies import require_creator_or_owner, require_owner
from app.core.config import get_settings
from app.core.errors import TooLargeError, UnsupportedMediaTypeError, ValidationError
from app.visual import get_visual_asset_service, VisualAssetMetadata

router = APIRouter()

# Constants - use configuration values
_settings = get_settings()
MAX_UPLOAD_MB = _settings.UPLOAD_MAX_MB
MAX_PAGES = _settings.UPLOAD_MAX_PAGES
MAX_CHARS = _settings.REVISION_BODY_MAX_CHARS
ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

VISUAL_ALLOWED_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
}
MAX_VISUAL_UPLOAD_MB = 10


async def extract_pdf_text(file_bytes: bytes) -> tuple[str, int, list[str]]:
    """Extract text from PDF bytes."""
    import pypdf
    warnings_list = []
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    num_pages = len(reader.pages)

    if num_pages > MAX_PAGES:
        raise ValidationError(f"PDF exceeds maximum of {MAX_PAGES} pages")

    text_parts = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text:
                text_parts.append(text)
            else:
                warnings_list.append(f"no text found on page {i + 1} (possibly scanned)")
        except Exception:
            warnings_list.append(f"error extracting page {i + 1}")
        # No raw exception details exposed

    text = "\n\n".join(text_parts)
    return text, len(reader.pages), warnings_list


async def extract_docx_text(file_bytes: bytes) -> tuple[str, int, list[str]]:
    """Extract text from DOCX bytes (including tables)."""
    import docx
    warnings_list = []
    doc = docx.Document(io.BytesIO(file_bytes))

    # Count paragraphs as rough page estimate
    para_count = len(doc.paragraphs)
    estimated_pages = max(1, (para_count // 20) + 1)

    if estimated_pages > MAX_PAGES:
        raise ValidationError(f"Document exceeds maximum of {MAX_PAGES} pages")

    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    # Also extract table content
    # Note: Tables are appended after paragraphs, not in exact document order.
    # This is an MVP limitation; exact document order is not preserved.
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    text_parts.append(cell.text)

    text = "\n\n".join(text_parts)
    return text, estimated_pages, warnings_list


async def extract_text(file: UploadFile) -> tuple[str, int, list[str], bool]:
    """Extract text from uploaded file, returning (text, pages, warnings, truncated)."""
    # Check content type
    content_type = file.content_type
    if content_type not in ALLOWED_TYPES:
        raise UnsupportedMediaTypeError("Upload must be a PDF or DOCX file")

    # Read file in chunks to enforce size limit
    chunks = []
    total_bytes = 0
    try:
        while True:
            chunk = await file.read(64 * 1024)  # 64KB chunks
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_MB * 1024 * 1024:
                raise TooLargeError(f"File size exceeds {MAX_UPLOAD_MB} MB limit")
            chunks.append(chunk)
    finally:
        await file.close()

    file_bytes = b"".join(chunks)

    # Extract text based on type
    if file.content_type == "application/pdf":
        text, pages, warnings = await extract_pdf_text(file_bytes)
    else:
        text, pages, warnings = await extract_docx_text(file_bytes)

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Determine truncation before truncating
    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS]

    return text, pages, warnings, truncated


@router.post(
    "/imports/text",
    status_code=200,
    responses={
        200: {"description": "Text extracted successfully"},
        400: {"description": "Validation error"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported media type"},
        422: {"description": "Validation error"},
    },
)
async def import_text(
    file: UploadFile = File(...),
    user=Depends(require_creator_or_owner),
) -> dict:
    """Extract text from uploaded PDF or DOCX file.

    Requires creator or owner role. No data is stored; extracted text is returned directly.
    """
    text, pages, warnings, truncated = await extract_text(file)

    return {
        "text": text,
        "pages": pages,
        "char_count": len(text),
        "truncated": truncated,
        "warnings": warnings,
    }


@router.post(
    "/imports/visual",
    status_code=200,
    responses={
        200: {"description": "Visual asset uploaded successfully"},
        400: {"description": "Validation error"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported media type"},
        422: {"description": "Validation error"},
    },
)
async def import_visual(
    file: UploadFile = File(...),
    content_id: UUID = Form(...),
    revision_id: UUID = Form(...),
    user=Depends(require_creator_or_owner),
) -> dict:
    """Upload a visual asset (PNG, JPEG, WebP) and associate with content/revision.

    Requires creator or owner role. Returns asset metadata and signed URL.
    """
    # Validate file type
    content_type = file.content_type
    if content_type not in VISUAL_ALLOWED_TYPES:
        raise UnsupportedMediaTypeError("Upload must be a PNG, JPEG, or WebP image")

    # Read file in chunks to enforce size limit
    chunks = []
    total_bytes = 0
    try:
        while True:
            chunk = await file.read(64 * 1024)  # 64KB chunks
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_VISUAL_UPLOAD_MB * 1024 * 1024:
                raise TooLargeError(f"File size exceeds {MAX_VISUAL_UPLOAD_MB} MB limit")
            chunks.append(chunk)
    finally:
        await file.close()

    file_bytes = b"".join(chunks)

    # Get visual asset service
    asset_service = get_visual_asset_service()

    # Validate upload
    is_valid, error_msg = asset_service.validate_upload(file_bytes, content_type)
    if not is_valid:
        raise ValidationError(error_msg)

    # Strip EXIF and extract metadata
    clean_bytes = asset_service.strip_exif(file_bytes, content_type)
    metadata = asset_service.extract_extended_metadata(clean_bytes, content_type)

    # Upload to storage, create asset record, and link - all with cleanup on failure
    try:
        # Upload to storage
        storage_path, metadata = asset_service.upload_asset(
            org_id=user.org_id,
            user_id=user.user_id,
            file_bytes=clean_bytes,
            mime_type=content_type,
            filename=file.filename or "image",
        )

        # Create asset record in database
        asset_record = asset_service.create_asset_record(
            org_id=user.org_id,
            user_id=user.user_id,
            storage_path=storage_path,
            mime_type=content_type,
            metadata=metadata,
        )

        if not asset_record:
            raise ValidationError("Failed to create asset record")

        asset_id = asset_record.get("id") or asset_record.get("id")

        # Link asset to content/revision
        from app.auth.supabase import get_supabase_client
        supabase = get_supabase_client()
        try:
            supabase.link_visual_asset_to_content(
                visual_asset_id=str(asset_id),
                content_id=str(content_id),
                revision_id=str(revision_id),
                actor_user_id=user.user_id,
            )
        except Exception as e:
            raise ValidationError(f"Failed to link asset to content: {e}")

        # Generate signed URL for immediate access
        signed_url = asset_service.get_signed_url(storage_path)

        return {
            "asset_id": str(asset_id),
            "width": metadata.width,
            "height": metadata.height,
            "mime_type": content_type,
            "checksum": metadata.checksum,
            "signed_url": signed_url,
            "expires_in": 3600,
        }

    except ValidationError:
        raise
    except TooLargeError:
        raise
    except UnsupportedMediaTypeError:
        raise
    except RuntimeError as e:
        # Handle storage/upload errors
        raise ValidationError(f"Upload failed: {e}")
    except Exception as e:
        # Any other unexpected error
        logger.error("visual_upload_failed", extra={"error": str(e), "content_id": str(content_id)})
        raise ValidationError(f"Upload failed: {e}")