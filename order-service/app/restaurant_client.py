"""HTTP client for calling restaurant-service — the source of truth for
restaurants and menu items. order-service never touches restaurant-service's
database directly (each microservice owns its own data store).
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger("order_service.restaurant_client")


class RestaurantServiceError(Exception):
    """Raised when restaurant-service is unreachable or returns an unexpected error."""


async def get_restaurant(restaurant_id: int) -> dict | None:
    url = f"{settings.RESTAURANT_SERVICE_URL}/api/restaurants/{restaurant_id}"
    try:
        async with httpx.AsyncClient(timeout=settings.RESTAURANT_SERVICE_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.error("restaurant-service unreachable: %s", exc)
        raise RestaurantServiceError("restaurant-service is unavailable") from exc

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise RestaurantServiceError(f"restaurant-service returned {response.status_code}")
    return response.json()


async def lookup_menu_items(item_ids: list[int]) -> list[dict]:
    url = f"{settings.RESTAURANT_SERVICE_URL}/internal/menu-items/lookup"
    try:
        async with httpx.AsyncClient(timeout=settings.RESTAURANT_SERVICE_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json={"ids": item_ids})
    except httpx.HTTPError as exc:
        logger.error("restaurant-service unreachable: %s", exc)
        raise RestaurantServiceError("restaurant-service is unavailable") from exc

    if response.status_code >= 400:
        raise RestaurantServiceError(f"restaurant-service returned {response.status_code}")
    return response.json()
