import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.messaging import publisher
from app.metrics import PrometheusMiddleware, metrics_response
from app.routers import auth, couriers, health, orders

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await publisher.connect()
    yield
    await publisher.close()


app = FastAPI(
    title="Order Service",
    description="Handles users, authentication, orders and courier assignment for the food-delivery platform.",
    version="1.0.0",
    lifespan=lifespan,
    # See restaurant-service/app/main.py for why this is a unique path
    # rather than the FastAPI default "/openapi.json".
    openapi_url="/order-openapi.json",
)

app.add_middleware(PrometheusMiddleware)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(couriers.router)


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return metrics_response()
