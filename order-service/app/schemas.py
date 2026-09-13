from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import OrderStatus, UserRole

# ---------- Auth ----------

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    admin_secret: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Couriers ----------

class CourierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=30)


class CourierUpdate(BaseModel):
    is_available: bool | None = None
    name: str | None = None
    phone: str | None = None


class CourierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    is_available: bool


# ---------- Orders ----------

class OrderItemIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0, le=50)


class OrderCreate(BaseModel):
    restaurant_id: int
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int
    name_snapshot: str
    price_snapshot: float
    quantity: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    restaurant_id: int
    courier_id: int | None
    status: OrderStatus
    total_price: float
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut] = []


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    courier_id: int | None = None
