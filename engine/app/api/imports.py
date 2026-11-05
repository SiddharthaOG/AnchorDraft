"""Text import API endpoints."""
import io
from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import JSONResponse

from app.auth.dependencies import require_creator_or_owner
from app.core.errors import TooLargeError, UnsupportedMediaTypeError, ValidationError

router = APIRouter()

# Constants
MAX_UPLOAD_MB = 5
MAX_PAGES = 20
MAX_CHARS = 20000
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

    if num_pages > 20:
        raise ValidationError(f"PDF exceeds maximum of {20} pages")

    text_parts = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text:
                text_parts.append(text)
            else:
                warnings.append(f"no text found on page {i + 1} (possibly scanned)")
        except Exception as e:
            warnings.append(f"error extracting page {i + 1}: {str(e)}")

    text = "\n\n".join(text_parts)
    return text, len(reader.pages), warnings


async def extract_docx_text(file_bytes: bytes) -> tuple[str, int, list[str]]:
    """Extract text from DOCX bytes."""
    import docx
    warnings = []
    doc = docx.Document(io.BytesIO(file_bytes))

    # Count paragraphs as rough page estimate
    para_count = len(doc.paragraphs)
    estimated_pages = max(1, (para_count // 20) + 1)

    if estimated_pages > 20:
        raise ValidationError(f"Document exceeds maximum of {20} pages")

    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    text = "\n\n".join(text_parts)
    return text, estimated_pages, warnings


async def extract_text(file: UploadFile) -> tuple[str, int, list[str]]:
    """Extract text from uploaded file."""
    # Check content type
    content_type = file.content_type
    if content_type not in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        raise UnsupportedMediaTypeError("Upload must be a PDF or DOCX file")

    # Read file bytes
    file_bytes = await file.read()

    # Check size
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise TooLargeError(f"File size exceeds {MAX_UPLOAD_MB} MB limit")

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

    return text, pages, warnings


from app.auth.dependencies import require_creator_or_owner


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
    text, pages, warnings = await extract_text(file)

    return {
        "text": text,
        "pages": pages,
        "char_count": len(text),
        "truncated": len(text) >= MAX_CHARS,  # Check if original was truncated
        "warnings": warnings,
    }