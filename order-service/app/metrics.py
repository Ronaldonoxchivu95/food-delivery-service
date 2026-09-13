import time

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"]
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)
ORDERS_CREATED_TOTAL = Counter(
    "orders_created_total", "Number of orders created", ["restaurant_id"]
)
ORDER_EVENTS_PUBLISHED_TOTAL = Counter(
    "order_events_published_total", "Order events published to RabbitMQ", ["event_type"]
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        endpoint = request.url.path
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method, endpoint=endpoint, status_code=response.status_code
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, endpoint=endpoint).observe(duration)
        return response


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
