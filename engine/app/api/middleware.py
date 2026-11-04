"""Middleware for X-Request-Id header."""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure every request has an X-Request-Id header."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Get or generate request ID
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())

        # Add to request state for downstream access
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add to response headers
        response.headers["X-Request-Id"] = request_id

        return response