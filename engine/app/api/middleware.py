"""Middleware for a validated X-Request-Id header."""
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a bounded, safe correlation ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        supplied_id = request.headers.get("X-Request-Id", "")
        request_id = (
            supplied_id
            if _REQUEST_ID_PATTERN.fullmatch(supplied_id)
            else str(uuid.uuid4())
        )

        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
