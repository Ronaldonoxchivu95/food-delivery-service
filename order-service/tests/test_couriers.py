import pytest

from app.config import settings
from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def _admin_headers(client):
    token = await register_and_login(
        client, "courier-admin@example.com", admin_secret=settings.ADMIN_REGISTRATION_SECRET
    )
    return {"Authorization": f"Bearer {token}"}


async def test_create_courier_requires_admin(client):
    token = await register_and_login(client, "regular@example.com")
    resp = await client.post(
        "/api/couriers",
        json={"name": "Dan the Courier", "phone": "+1000000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_admin_can_create_and_list_couriers(client):
    headers = await _admin_headers(client)
    create_resp = await client.post(
        "/api/couriers", json={"name": "Dan the Courier", "phone": "+1000000"}, headers=headers
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["is_available"] is True

    list_resp = await client.get("/api/couriers", headers=headers)
    assert list_resp.status_code == 200
    names = {c["name"] for c in list_resp.json()}
    assert "Dan the Courier" in names


async def test_update_courier_availability(client):
    headers = await _admin_headers(client)
    create_resp = await client.post(
        "/api/couriers", json={"name": "Eve", "phone": "+2000000"}, headers=headers
    )
    courier_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/couriers/{courier_id}", json={"is_available": False}, headers=headers
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_available"] is False


async def test_update_unknown_courier_returns_404(client):
    headers = await _admin_headers(client)
    resp = await client.patch("/api/couriers/9999", json={"is_available": False}, headers=headers)
    assert resp.status_code == 404
