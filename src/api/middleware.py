"""
FastAPI middleware for observability.

- CorrelationIdMiddleware: injects/propagates X-Request-ID, binds to structlog
- PrometheusMiddleware:    records request count + latency histograms
"""

from __future__ import annotations

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
import structlog

from src.core.metrics import http_requests_total, http_request_duration_seconds


# ---------------------------------------------------------------------------
# Correlation ID
# ---------------------------------------------------------------------------

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Extract or generate ``X-Request-ID`` and bind it to structlog context vars.

    The header is echoed back in the response so callers can correlate logs.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Bind for the duration of the request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------

class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record HTTP request counters and latency histograms."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        # Normalise path to avoid cardinality explosion from path params
        path = self._normalise_path(request.url.path)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        status_code = str(response.status_code)

        http_requests_total.labels(method=method, endpoint=path, status_code=status_code).inc()
        http_request_duration_seconds.labels(method=method, endpoint=path).observe(elapsed)

        return response

    @staticmethod
    def _normalise_path(path: str) -> str:
        """
        Replace UUID‐shaped segments with ``{id}`` to keep Prometheus label
        cardinality manageable.
        """
        parts = path.strip("/").split("/")
        normalised = []
        for part in parts:
            # UUID pattern (8-4-4-4-12 hex)
            if len(part) == 36 and part.count("-") == 4:
                normalised.append("{id}")
            else:
                normalised.append(part)
        return "/" + "/".join(normalised)
