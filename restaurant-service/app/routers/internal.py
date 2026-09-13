"""Internal, service-to-service endpoints.

order-service calls this to validate menu items and fetch authoritative
prices when placing an order — a single batched call instead of N HTTP
round-trips (which would just move the N+1 problem to the network layer).
In production this would additionally be restricted to the internal
network / a service-mesh mTLS boundary; here that boundary is docker-compose's
private network.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MenuItem
from app.schemas import MenuItemLookupOut, MenuItemLookupRequest

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/menu-items/lookup", response_model=list[MenuItemLookupOut])
async def lookup_menu_items(payload: MenuItemLookupRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MenuItem).where(MenuItem.id.in_(payload.ids)))
    return result.scalars().all()
