import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user, require_admin
from app.messaging import publisher
from app.metrics import ORDER_EVENTS_PUBLISHED_TOTAL, ORDERS_CREATED_TOTAL
from app.models import Courier, Order, OrderItem, OrderStatus, User
from app.restaurant_client import RestaurantServiceError, lookup_menu_items
from app.schemas import OrderCreate, OrderOut, OrderStatusUpdate

router = APIRouter(prefix="/api/orders", tags=["orders"])
logger = logging.getLogger("order_service.orders")


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    requested_ids = [item.menu_item_id for item in payload.items]

    try:
        menu_items = await lookup_menu_items(requested_ids)
    except RestaurantServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Restaurant service is currently unavailable, please try again later",
        ) from exc

    menu_items_by_id = {item["id"]: item for item in menu_items}
    missing = [mid for mid in requested_ids if mid not in menu_items_by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown menu item ids: {missing}"
        )

    order_items: list[OrderItem] = []
    total_price = 0.0
    for requested in payload.items:
        menu_item = menu_items_by_id[requested.menu_item_id]
        if menu_item["restaurant_id"] != payload.restaurant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Menu item {requested.menu_item_id} does not belong to restaurant {payload.restaurant_id}",
            )
        if not menu_item["is_available"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Menu item {requested.menu_item_id} is not available",
            )
        line_total = float(menu_item["price"]) * requested.quantity
        total_price += line_total
        order_items.append(
            OrderItem(
                menu_item_id=menu_item["id"],
                name_snapshot=menu_item["name"],
                price_snapshot=menu_item["price"],
                quantity=requested.quantity,
            )
        )

    order = Order(
        user_id=user.id,
        restaurant_id=payload.restaurant_id,
        status=OrderStatus.CREATED,
        total_price=round(total_price, 2),
        items=order_items,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order, attribute_names=["items"])

    ORDERS_CREATED_TOTAL.labels(restaurant_id=str(payload.restaurant_id)).inc()

    await publisher.publish(
        "order.created",
        {
            "order_id": order.id,
            "user_id": order.user_id,
            "restaurant_id": order.restaurant_id,
            "total_price": float(order.total_price),
        },
    )
    ORDER_EVENTS_PUBLISHED_TOTAL.labels(event_type="order.created").inc()

    return order


@router.get("", response_model=list[OrderOut])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # selectinload avoids issuing one extra query per order for its items.
    query = select(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc())
    if user.role.value != "admin":
        query = query.where(Order.user_id == user.id)
    result = await db.execute(query)
    return result.scalars().all()


async def _get_order_or_404(db: AsyncSession, order_id: int) -> Order:
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = await _get_order_or_404(db, order_id)
    if user.role.value != "admin" and order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    order = await _get_order_or_404(db, order_id)

    if payload.courier_id is not None:
        courier = await db.get(Courier, payload.courier_id)
        if courier is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found")
        if not courier.is_available and order.courier_id != courier.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Courier is not available")
        courier.is_available = False
        order.courier_id = courier.id

    order.status = payload.status
    if payload.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED) and order.courier_id:
        freed_courier = await db.get(Courier, order.courier_id)
        if freed_courier is not None:
            freed_courier.is_available = True

    await db.commit()
    await db.refresh(order, attribute_names=["items"])

    await publisher.publish(
        "order.status_changed",
        {"order_id": order.id, "status": order.status.value, "courier_id": order.courier_id},
    )
    ORDER_EVENTS_PUBLISHED_TOTAL.labels(event_type="order.status_changed").inc()

    return order
