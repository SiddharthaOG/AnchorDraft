"""Error handling and mapping from database exceptions to HTTP responses."""
from fastapi import Request, status
from fastapi.responses import JSONResponse
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
        super().__init__(ErrorCode.TOO_LARGE, message, status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)


class UnsupportedMediaTypeError(AppException):
    def __init__(self, message: str = "Unsupported media type"):
        super().__init__(ErrorCode.UNSUPPORTED_MEDIA_TYPE, message, status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)


class ValidationError(AppException):
    def __init__(self, message: str = "Validation error"):
        super().__init__(ErrorCode.VALIDATION_ERROR, message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


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
        super().__init__(
            ErrorCode.INTERNAL_ERROR,
            message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Database error message prefixes
DB_ERROR_PREFIXES = {
    "unauthenticated": (ErrorCode.UNAUTHENTICATED, status.HTTP_401_UNAUTHORIZED),
    "forbidden": (ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN),
    "not_found": (ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND),
    "conflict:": (ErrorCode.CONFLICT, status.HTTP_409_CONFLICT),
    "validation:": (ErrorCode.VALIDATION_ERROR, status.HTTP_422_UNPROCESSABLE_ENTITY),
}


def map_db_exception(exc: Exception, request_id: str) -> JSONResponse:
    """Map a database exception to an HTTP response."""
    message = str(exc)

    # Check for database error prefixes
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
            elif prefix == "validation:":
                field = message[len(prefix):]
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content=ErrorResponse(
                        error=APIError(
                            code=ErrorCode.VALIDATION_ERROR,
                            reason=field,
                            message=f"Validation error: {field}",
                            request_id=request_id,
                        )
                    ).model_dump(),
                )
            else:
                return JSONResponse(
                    status_code=status_code,
                    content=ErrorResponse(
                        error=APIError(
                            code=code,
                            message=message,
                            request_id=request_id,
                        )
                    ).model_dump(),
                )

    # Default to internal error
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
    """Handle AppException."""
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=APIError(
                code=exc.code,
                reason=exc.reason,
                message=exc.message,
                request_id=request_id,
                retry_after_seconds=exc.retry_after_seconds,
            )
        ).model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions by first attempting database exception mapping."""
    request_id = getattr(request.state, "request_id", "")

    # First attempt to map as database exception
    db_response = map_db_exception(exc, request_id)
    # If the exception was successfully mapped (not an internal error), return it
    if db_response.status_code != 500:
        return db_response

    # Log unexpected exceptions for debugging (no sensitive data)
    logger.exception("Unhandled exception: %s", type(exc).__name__)

    # Return safe generic error
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=APIError(
                code="internal_error",
                message="Internal server error",
                request_id=request_id,
            )
        ).model_dump(),
    )
