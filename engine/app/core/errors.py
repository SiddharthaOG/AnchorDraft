"""Error handling and mapping from database exceptions to HTTP responses."""
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Optional
import logging
from app.models.api import ErrorCode, ConflictReason, APIError, ErrorResponse


logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception with error details."""
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        reason: Optional[str] = None,
        retry_after_seconds: Optional[int] = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ):
        self.code = code
        self.message = message
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code
        super().__init__(message)


class UnauthenticatedError(AppException):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(ErrorCode.UNAUTHENTICATED, message, status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(ErrorCode.FORBIDDEN, message, status_code=status.HTTP_403_FORBIDDEN)


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(ErrorCode.NOT_FOUND, message, status_code=status.HTTP_404_NOT_FOUND)


class ConflictError(AppException):
    def __init__(self, reason: ConflictReason, message: str):
        super().__init__(ErrorCode.CONFLICT, message, reason=reason, status_code=status.HTTP_409_CONFLICT)


class TooLargeError(AppException):
    def __init__(self, message: str = "Request too large"):
        super().__init__(ErrorCode.TOO_LARGE, message, status_code=413)


class UnsupportedMediaTypeError(AppException):
    def __init__(self, message: str = "Unsupported media type"):
        super().__init__(ErrorCode.UNSUPPORTED_MEDIA_TYPE, message, status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)


class ValidationError(AppException):
    def __init__(self, message: str = "Validation error"):
        super().__init__(ErrorCode.VALIDATION_ERROR, message, status_code=422)


class RateLimitedError(AppException):
    def __init__(self, message: str = "Rate limited", retry_after_seconds: int = 60):
        super().__init__(
            ErrorCode.RATE_LIMITED,
            message,
            retry_after_seconds=retry_after_seconds,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class UpstreamUnavailableError(AppException):
    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class InternalError(AppException):
    def __init__(self, message: str = "Internal server error"):
        super().__init__(ErrorCode.INTERNAL_ERROR, message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Database error message prefixes
DB_ERROR_PREFIXES = {
    "unauthenticated": (ErrorCode.UNAUTHENTICATED, status.HTTP_401_UNAUTHORIZED),
    "forbidden": (ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN),
    "not_found": (ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND),
    "conflict:": (ErrorCode.CONFLICT, status.HTTP_409_CONFLICT),
    "validation:": (ErrorCode.VALIDATION_ERROR, 422),
}

HTTP_ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHENTICATED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    413: ErrorCode.TOO_LARGE,
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.UPSTREAM_UNAVAILABLE,
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalize framework and endpoint HTTP errors to the public API error contract."""
    detail = exc.detail
    detail_data = detail if isinstance(detail, dict) else {}
    nested_error = detail_data.get("error")
    nested_error = nested_error if isinstance(nested_error, dict) else {}

    code = HTTP_ERROR_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    raw_code = nested_error.get("code")
    if isinstance(raw_code, str):
        try:
            code = ErrorCode(raw_code)
        except ValueError:
            pass

    message = nested_error.get("message")
    if not isinstance(message, str):
        message = detail_data.get("message")
    if not isinstance(message, str):
        message = detail if isinstance(detail, str) else "Request could not be completed"

    reason = nested_error.get("reason") or detail_data.get("reason") or detail_data.get("code")
    retry_after = nested_error.get("retry_after_seconds") or detail_data.get("retry_after_seconds")
    if not isinstance(reason, str):
        reason = None
    if not isinstance(retry_after, int) or retry_after < 0:
        retry_after = None

    payload = ErrorResponse(
        error=APIError(
            code=code,
            reason=reason,
            message=message,
            request_id=_request_id(request),
            retry_after_seconds=retry_after,
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(mode="json"),
        headers=exc.headers,
    )


async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a stable validation error without echoing rejected input values."""
    locations = []
    for issue in exc.errors():
        location = ".".join(str(part) for part in issue.get("loc", ()) if part != "body")
        message = issue.get("msg")
        if location and isinstance(message, str):
            locations.append(f"{location}: {message}")

    message = "Request validation failed"
    if locations:
        message = f"{message} ({'; '.join(locations)})"

    payload = ErrorResponse(
        error=APIError(
            code=ErrorCode.VALIDATION_ERROR,
            reason="request_validation_error",
            message=message,
            request_id=_request_id(request),
        )
    )
    return JSONResponse(
        status_code=422,
        content=payload.model_dump(mode="json"),
    )


def map_db_exception(exc: Exception, request_id: str) -> JSONResponse:
    """Map a database exception to an HTTP response."""
    message = str(exc)

    for prefix, (code, status_code) in DB_ERROR_PREFIXES.items():
        if message.startswith(prefix):
            if prefix == "conflict:":
                reason = message[len(prefix):]
                return JSONResponse(
                    status_code=status_code,
                    content=ErrorResponse(
                        error=APIError(
                            code=ErrorCode.CONFLICT,
                            reason=reason,
                            message=f"Conflict: {reason}",
                            request_id=request_id,
                        )
                    ).model_dump(),
                )
            if prefix == "validation:":
                field = message[len(prefix):]
                return JSONResponse(
                    status_code=status_code,
                    content=ErrorResponse(
                        error=APIError(
                            code=ErrorCode.VALIDATION_ERROR,
                            reason=field,
                            message=f"Validation error: {field}",
                            request_id=request_id,
                        )
                    ).model_dump(),
                )
            return JSONResponse(
                status_code=status_code,
                content=ErrorResponse(
                    error=APIError(code=code, message=message, request_id=request_id)
                ).model_dump(),
            )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=APIError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Internal server error",
                request_id=request_id,
            )
        ).model_dump(),
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=APIError(
                code=exc.code,
                reason=exc.reason,
                message=exc.message,
                request_id=_request_id(request),
                retry_after_seconds=exc.retry_after_seconds,
            )
        ).model_dump(),
        headers={"Retry-After": str(exc.retry_after_seconds)} if exc.retry_after_seconds is not None else None,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions without exposing internal details."""
    request_id = _request_id(request)
    db_response = map_db_exception(exc, request_id)
    if db_response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR:
        db_response.headers["X-Request-Id"] = request_id
        return db_response

    logger.error("Unhandled exception", extra={"request_id": request_id, "error_type": type(exc).__name__})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=APIError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Internal server error",
                request_id=request_id,
            )
        ).model_dump(),
        headers={"X-Request-Id": request_id},
    )
