"""Text import API endpoints."""
import io
from fastapi import APIRouter, Depends, File, UploadFile, status

from app.auth.dependencies import require_creator_or_owner
from app.core.config import get_settings
from app.core.errors import TooLargeError, UnsupportedMediaTypeError, ValidationError

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


async def extract_pdf_text(file_bytes: bytes) -> tuple[str, int, list[str]]:
    """Extract text from PDF bytes."""
    import pypdf
    warnings = []
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
                warnings.append(f"no text found on page {i + 1} (possibly scanned)")
        except Exception:
            warnings.append(f"error extracting page {i + 1}")
        # No raw exception details exposed

    text = "\n\n".join(text_parts)
    return text, len(reader.pages), warnings


async def extract_docx_text(file_bytes: bytes) -> tuple[str, int, list[str]]:
    """Extract text from DOCX bytes (including tables)."""
    import docx
    warnings = []
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
    return text, estimated_pages, warnings


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


router = APIRouter()


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