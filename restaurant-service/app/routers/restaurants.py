from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cache import cache_delete, cache_delete_by_prefix, cache_get, cache_set
from app.database import get_db
from app.metrics import RESTAURANTS_CREATED_TOTAL
from app.models import MenuCategory, Restaurant
from app.schemas import RestaurantCreate, RestaurantMenuOut, RestaurantOut, RestaurantUpdate
from app.security import require_admin

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])


@router.post("", response_model=RestaurantOut, status_code=status.HTTP_201_CREATED)
async def create_restaurant(
    payload: RestaurantCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    restaurant = Restaurant(**payload.model_dump())
    db.add(restaurant)
    await db.commit()
    await db.refresh(restaurant)
    RESTAURANTS_CREATED_TOTAL.inc()
    await cache_delete_by_prefix("restaurants:list")
    return restaurant


@router.get("", response_model=list[RestaurantOut])
async def list_restaurants(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"restaurants:list:{skip}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(Restaurant).where(Restaurant.is_active.is_(True)).offset(skip).limit(limit)
    )
    restaurants = result.scalars().all()
    data = [RestaurantOut.model_validate(r).model_dump(mode="json") for r in restaurants]
    await cache_set(cache_key, data)
    return data


@router.get("/{restaurant_id}", response_model=RestaurantOut)
async def get_restaurant(restaurant_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"restaurant:{restaurant_id}:detail"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    restaurant = await db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    data = RestaurantOut.model_validate(restaurant).model_dump(mode="json")
    await cache_set(cache_key, data)
    return data


@router.get("/{restaurant_id}/menu", response_model=RestaurantMenuOut)
async def get_restaurant_menu(restaurant_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"restaurant:{restaurant_id}:menu"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # A single query with selectinload for categories + items avoids the
    # classic N+1 problem of fetching items per category in a loop.
    result = await db.execute(
        select(Restaurant)
        .where(Restaurant.id == restaurant_id)
        .options(selectinload(Restaurant.categories).selectinload(MenuCategory.items))
    )
    restaurant = result.unique().scalar_one_or_none()
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    data = RestaurantMenuOut.model_validate(restaurant).model_dump(mode="json")
    await cache_set(cache_key, data)
    return data


@router.patch("/{restaurant_id}", response_model=RestaurantOut)
async def update_restaurant(
    restaurant_id: int,
    payload: RestaurantUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    restaurant = await db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(restaurant, field, value)
    await db.commit()
    await db.refresh(restaurant)

    await cache_delete(f"restaurant:{restaurant_id}:detail", f"restaurant:{restaurant_id}:menu")
    await cache_delete_by_prefix("restaurants:list")
    return restaurant


@router.delete("/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_restaurant(
    restaurant_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    restaurant = await db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    restaurant.is_active = False
    await db.commit()

    await cache_delete(f"restaurant:{restaurant_id}:detail", f"restaurant:{restaurant_id}:menu")
    await cache_delete_by_prefix("restaurants:list")
