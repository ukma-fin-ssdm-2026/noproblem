"""Prometheus-метрики HTTP-шару та ідемпотентності."""

import time

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Кількість HTTP-запитів.",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "Тривалість обробки HTTP-запиту, секунди.",
    ["method", "route"],
    # Щільні межі навколо SLO 150 мс.
    buckets=(0.025, 0.05, 0.1, 0.125, 0.15, 0.175, 0.2, 0.3, 0.5, 1, 2.5, 5),
)
HTTP_RESPONSE_SIZE = Histogram(
    "http_response_size_bytes",
    "Розмір тіла HTTP-відповіді, байти.",
    ["method", "route"],
    buckets=(100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000),
)
IDEMPOTENT_REPLAYS = Counter(
    "idempotent_replays_total",
    "Повтори запиту з тим самим Idempotency-Key, віддані зі збереженого "
    "результату.",
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500
        size = 0
        try:
            response = await call_next(request)
            status_code = response.status_code
            size = int(response.headers.get("content-length", 0))
            return response
        finally:
            elapsed = time.perf_counter() - start
            route = getattr(request.scope.get("route"), "path", "unmatched")
            HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, route).observe(elapsed)
            HTTP_RESPONSE_SIZE.labels(request.method, route).observe(size)


def install_metrics(app: FastAPI) -> None:
    """Підключає збір метрик і ендпоінт /metrics."""
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
