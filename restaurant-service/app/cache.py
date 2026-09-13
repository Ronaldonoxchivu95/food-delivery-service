"""Thin Redis caching helper with graceful degradation.

If Redis is unreachable, every method swallows the error, logs a warning and
behaves as a cache miss / no-op — the service must keep serving requests
straight from Postgres rather than fail.
"""

import json
import logging

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger("restaurant_service.cache")

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    return _redis_client


async def cache_get(key: str) -> dict | list | None:
    try:
        client = get_redis()
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - any Redis/network failure must not break the request
        logger.warning("Cache GET failed for key=%s: %s", key, exc)
        return None


async def cache_set(key: str, value: dict | list, ttl: int | None = None) -> None:
    try:
        client = get_redis()
        await client.set(key, json.dumps(value), ex=ttl or settings.CACHE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cache SET failed for key=%s: %s", key, exc)


async def cache_delete(*keys: str) -> None:
    if not keys:
        return
    try:
        client = get_redis()
        await client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cache DELETE failed for keys=%s: %s", keys, exc)


async def cache_delete_by_prefix(prefix: str) -> None:
    try:
        client = get_redis()
        keys = [key async for key in client.scan_iter(match=f"{prefix}*")]
        if keys:
            await client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cache prefix-delete failed for prefix=%s: %s", prefix, exc)


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
