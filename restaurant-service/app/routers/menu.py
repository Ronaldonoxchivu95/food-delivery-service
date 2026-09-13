from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_delete
from app.database import get_db
from app.models import MenuCategory, MenuItem, Restaurant
from app.schemas import MenuCategoryCreate, MenuCategoryOut, MenuItemCreate, MenuItemOut, MenuItemUpdate
from app.security import require_admin

router = APIRouter(prefix="/api", tags=["menu"])


async def _get_restaurant_or_404(db: AsyncSession, restaurant_id: int) -> Restaurant:
    restaurant = await db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")
    return restaurant


@router.post(
    "/restaurants/{restaurant_id}/categories",
    response_model=MenuCategoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    restaurant_id: int,
    payload: MenuCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    await _get_restaurant_or_404(db, restaurant_id)
    category = MenuCategory(restaurant_id=restaurant_id, **payload.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    await cache_delete(f"restaurant:{restaurant_id}:menu")
    # Build the response directly instead of validating the ORM object: a
    # brand-new category has no items yet, and touching category.items here
    # would lazy-load an unloaded relationship outside of an awaited
    # context, which raises MissingGreenlet under the async driver.
    return MenuCategoryOut(id=category.id, restaurant_id=category.restaurant_id, name=category.name, items=[])


@router.post(
    "/restaurants/{restaurant_id}/menu-items",
    response_model=MenuItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_menu_item(
    restaurant_id: int,
    payload: MenuItemCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    await _get_restaurant_or_404(db, restaurant_id)
    item = MenuItem(restaurant_id=restaurant_id, **payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await cache_delete(f"restaurant:{restaurant_id}:menu")
    return item


@router.get("/menu-items/{item_id}", response_model=MenuItemOut)
async def get_menu_item(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")
    return item


@router.patch("/menu-items/{item_id}", response_model=MenuItemOut)
async def update_menu_item(
    item_id: int,
    payload: MenuItemUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    item = await db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)

    await cache_delete(f"restaurant:{item.restaurant_id}:menu")
    return item
