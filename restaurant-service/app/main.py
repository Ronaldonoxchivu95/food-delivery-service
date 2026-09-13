import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.cache import close_redis
from app.messaging import consumer
from app.metrics import PrometheusMiddleware, metrics_response
from app.routers import health, internal, menu, restaurants

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await consumer.start()
    yield
    await consumer.stop()
    await close_redis()


app = FastAPI(
    title="Restaurant Service",
    description="Manages restaurants and their menus for the food-delivery platform.",
    version="1.0.0",
    lifespan=lifespan,
    # Served behind Nginx at /restaurant-docs (rewritten to /docs). The
    # default "/openapi.json" is an absolute path the browser would request
    # from the domain root regardless of that rewrite, colliding with
    # order-service's own schema — so each service gets its own unique path,
    # matched by an explicit Nginx location block.
    openapi_url="/restaurant-openapi.json",
)

app.add_middleware(PrometheusMiddleware)

app.include_router(health.router)
app.include_router(restaurants.router)
app.include_router(menu.router)
app.include_router(internal.router)


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return metrics_response()
