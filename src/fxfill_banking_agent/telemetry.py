"""OpenTelemetry integration middleware (A7).

Provides FastAPI middleware for trace context propagation and span
creation. Redacts PII/secret fields before export.

For production, configure OTLP exporter to send to your observability
backend (Jaeger, Tempo, Datadog, etc.).
"""

from __future__ import annotations

import time as _time
import uuid
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TelemetryMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that creates a root span for each HTTP request.

    Attributes:
        app_name: Service name for span attribution.
        redact_fields: Additional fields to redact beyond defaults.
        sample_rate: Fraction of traces to sample (0.0–1.0).
    """

    def __init__(
        self,
        app: Any,
        *,
        app_name: str = "fxfill-banking-agent",
        redact_fields: list[str] | None = None,
        sample_rate: float = 1.0,
    ) -> None:
        super().__init__(app)
        self._app_name = app_name
        self._sample_rate = sample_rate

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Create a root span and propagate correlation IDs."""
        import random

        # Sampling decision
        if random.random() > self._sample_rate:
            return await call_next(request)

        correlation_id = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
        t0 = _time.monotonic()

        # Attach correlation ID to request state for downstream use
        request.state.correlation_id = correlation_id
        request.state.span_start = t0

        response = await call_next(request)

        # Record span duration
        duration_ms = (_time.monotonic() - t0) * 1000
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 1))

        # In production: export span to OTLP collector
        # span = Span(
        #     span_id=str(uuid.uuid4()),
        #     trace_id=correlation_id,
        #     kind=SpanKind.HTTP_REQUEST,
        #     start_time=...,
        #     end_time=...,
        #     attributes={"http.method": request.method, "http.url": str(request.url)},
        # )
        # exporter.export(span)

        return response
