from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------- Menu items ----------

class MenuItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: float = Field(gt=0)
    category_id: int | None = None
    is_available: bool = True


class MenuItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: float | None = Field(default=None, gt=0)
    category_id: int | None = None
    is_available: bool | None = None


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    category_id: int | None
    name: str
    description: str | None
    price: float
    is_available: bool


# ---------- Menu categories ----------

class MenuCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MenuCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    name: str
    items: list[MenuItemOut] = []


# ---------- Restaurants ----------

class RestaurantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=300)
    description: str | None = None


class RestaurantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    is_active: bool | None = None


class RestaurantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    description: str | None
    is_active: bool
    created_at: datetime


class RestaurantMenuOut(BaseModel):
    """Restaurant with its full menu, eagerly loaded to avoid N+1 queries."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    categories: list[MenuCategoryOut] = []


# ---------- Internal (service-to-service) ----------

class MenuItemLookupRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)


class MenuItemLookupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    name: str
    price: float
    is_available: bool
