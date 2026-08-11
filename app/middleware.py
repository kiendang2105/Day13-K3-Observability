from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

from .logging_config import get_logger

REQUEST_ID_HEADER = "x-request-id"
RESPONSE_TIME_HEADER = "x-response-time-ms"

# An inbound ID is only trusted when it is short and free of control characters,
# so a caller cannot inject header/log separators through it.
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def new_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


def resolve_correlation_id(request: Request) -> str:
    incoming = request.headers.get(REQUEST_ID_HEADER)
    if incoming and SAFE_REQUEST_ID.match(incoming):
        return incoming
    return new_correlation_id()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear_contextvars()

        correlation_id = resolve_correlation_id(request)
        bind_contextvars(correlation_id=correlation_id)

        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000

            # Access log o bien he thong. response_sent.latency_ms chi dem tu luc
            # LabAgent.run bat dau, nen khong thay thoi gian request nam cho truoc
            # do. Duoi su co rag_slow, hai con so lech nhau 5 lan - xem
            # submission/REPORT.md muc 6.
            get_logger().info(
                "request_completed",
                service="http",
                correlation_id=correlation_id,
                latency_ms=round(elapsed_ms),
                payload={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                },
            )
        finally:
            clear_contextvars()

        response.headers[REQUEST_ID_HEADER] = correlation_id
        response.headers[RESPONSE_TIME_HEADER] = f"{elapsed_ms:.2f}"

        return response
