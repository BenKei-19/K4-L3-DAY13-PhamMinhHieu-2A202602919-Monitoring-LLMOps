from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

REQUEST_ID_PATTERN = re.compile(r"req-[0-9a-f]{8}")


def new_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Clear context left over from a previous request before binding new values.
        clear_contextvars()

        # Reuse the caller's x-request-id only when it matches req-<8-hex>;
        # anything else is replaced so arbitrary header values never reach the logs.
        incoming_id = request.headers.get("x-request-id", "")
        if REQUEST_ID_PATTERN.fullmatch(incoming_id):
            correlation_id = incoming_id
        else:
            correlation_id = new_correlation_id()

        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["x-request-id"] = correlation_id
        response.headers["x-response-time-ms"] = f"{elapsed_ms:.1f}"
        return response
