from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_admin
from app.models import Courier
from app.schemas import CourierCreate, CourierOut, CourierUpdate

router = APIRouter(prefix="/api/couriers", tags=["couriers"])


@router.post("", response_model=CourierOut, status_code=status.HTTP_201_CREATED)
async def create_courier(
    payload: CourierCreate, db: AsyncSession = Depends(get_db), _admin=Depends(require_admin)
):
    courier = Courier(**payload.model_dump())
    db.add(courier)
    await db.commit()
    await db.refresh(courier)
    return courier


@router.get("", response_model=list[CourierOut])
async def list_couriers(
    available_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    query = select(Courier)
    if available_only:
        query = query.where(Courier.is_available.is_(True))
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{courier_id}", response_model=CourierOut)
async def update_courier(
    courier_id: int,
    payload: CourierUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    courier = await db.get(Courier, courier_id)
    if courier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(courier, field, value)
    await db.commit()
    await db.refresh(courier)
    return courier
