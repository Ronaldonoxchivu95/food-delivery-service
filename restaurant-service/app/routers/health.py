import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.database import get_db

router = APIRouter(tags=["health"])
logger = logging.getLogger("restaurant_service.health")


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False

    redis_ok = True
    try:
        await get_redis().ping()
    except Exception:  # noqa: BLE001
        redis_ok = False

    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "service": "restaurant-service",
        "dependencies": {"database": db_ok, "redis": redis_ok},
    }
