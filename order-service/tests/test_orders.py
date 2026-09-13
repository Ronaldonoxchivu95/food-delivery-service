import pytest

from app import routers
from app.config import settings
from app.restaurant_client import RestaurantServiceError
from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio

FAKE_MENU_ITEMS = [
    {"id": 1, "restaurant_id": 10, "name": "Margherita Pizza", "price": 8.5, "is_available": True},
    {"id": 2, "restaurant_id": 10, "name": "Coke", "price": 1.5, "is_available": True},
    {"id": 3, "restaurant_id": 10, "name": "Sold Out Item", "price": 5.0, "is_available": False},
    {"id": 4, "restaurant_id": 99, "name": "Other Restaurant Item", "price": 5.0, "is_available": True},
]


def _mock_lookup(monkeypatch, items=FAKE_MENU_ITEMS, error: Exception | None = None):
    async def fake_lookup_menu_items(item_ids):
        if error:
            raise error
        return [item for item in items if item["id"] in item_ids]

    monkeypatch.setattr(routers.orders, "lookup_menu_items", fake_lookup_menu_items)


async def _user_headers(client, email="diner@example.com"):
    token = await register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}


async def _admin_headers(client):
    token = await register_and_login(client, "orders-admin@example.com", admin_secret=settings.ADMIN_REGISTRATION_SECRET)
    return {"Authorization": f"Bearer {token}"}


async def test_create_order_success_computes_total_and_publishes_event(client, monkeypatch, published_events):
    _mock_lookup(monkeypatch)
    headers = await _user_headers(client)

    resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 1, "quantity": 2}, {"menu_item_id": 2, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_price"] == pytest.approx(2 * 8.5 + 1.5)
    assert body["status"] == "created"
    assert len(body["items"]) == 2

    assert ("order.created", {"order_id": body["id"], "user_id": body["user_id"], "restaurant_id": 10, "total_price": body["total_price"]}) in published_events


async def test_create_order_unknown_menu_item_returns_400(client, monkeypatch):
    _mock_lookup(monkeypatch)
    headers = await _user_headers(client)

    resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 12345, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_create_order_item_from_different_restaurant_returns_400(client, monkeypatch):
    _mock_lookup(monkeypatch)
    headers = await _user_headers(client)

    resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 4, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_create_order_unavailable_item_returns_400(client, monkeypatch):
    _mock_lookup(monkeypatch)
    headers = await _user_headers(client)

    resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 3, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 400


async def test_create_order_when_restaurant_service_down_returns_503(client, monkeypatch):
    _mock_lookup(monkeypatch, error=RestaurantServiceError("boom"))
    headers = await _user_headers(client)

    resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 1, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 503


async def test_users_only_see_their_own_orders(client, monkeypatch):
    _mock_lookup(monkeypatch)
    alice_headers = await _user_headers(client, "alice-orders@example.com")
    bob_headers = await _user_headers(client, "bob-orders@example.com")

    await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 1, "quantity": 1}]},
        headers=alice_headers,
    )
    await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 2, "quantity": 1}]},
        headers=bob_headers,
    )

    alice_orders = await client.get("/api/orders", headers=alice_headers)
    assert alice_orders.status_code == 200
    assert len(alice_orders.json()) == 1

    admin_headers = await _admin_headers(client)
    all_orders = await client.get("/api/orders", headers=admin_headers)
    assert len(all_orders.json()) == 2


async def test_admin_can_assign_available_courier_and_change_status(client, monkeypatch, published_events):
    _mock_lookup(monkeypatch)
    user_headers = await _user_headers(client)
    admin_headers = await _admin_headers(client)

    order_resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 1, "quantity": 1}]},
        headers=user_headers,
    )
    order_id = order_resp.json()["id"]

    courier_resp = await client.post(
        "/api/couriers", json={"name": "Fast Freddy", "phone": "+123"}, headers=admin_headers
    )
    courier_id = courier_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "assigned", "courier_id": courier_id},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "assigned"
    assert update_resp.json()["courier_id"] == courier_id

    # The courier should now be marked unavailable.
    couriers_resp = await client.get("/api/couriers", headers=admin_headers)
    courier = next(c for c in couriers_resp.json() if c["id"] == courier_id)
    assert courier["is_available"] is False

    assert any(event[0] == "order.status_changed" for event in published_events)


async def test_assigning_unavailable_courier_returns_400(client, monkeypatch):
    _mock_lookup(monkeypatch)
    user_headers = await _user_headers(client)
    admin_headers = await _admin_headers(client)

    order_resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 1, "quantity": 1}]},
        headers=user_headers,
    )
    order_id = order_resp.json()["id"]

    courier_resp = await client.post(
        "/api/couriers", json={"name": "Busy Bob", "phone": "+321"}, headers=admin_headers
    )
    courier_id = courier_resp.json()["id"]
    await client.patch(f"/api/couriers/{courier_id}", json={"is_available": False}, headers=admin_headers)

    resp = await client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "assigned", "courier_id": courier_id},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_regular_user_cannot_update_order_status(client, monkeypatch):
    _mock_lookup(monkeypatch)
    user_headers = await _user_headers(client)

    order_resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 1, "quantity": 1}]},
        headers=user_headers,
    )
    order_id = order_resp.json()["id"]

    resp = await client.patch(
        f"/api/orders/{order_id}/status", json={"status": "confirmed"}, headers=user_headers
    )
    assert resp.status_code == 403


async def test_user_cannot_view_someone_elses_order(client, monkeypatch):
    _mock_lookup(monkeypatch)
    alice_headers = await _user_headers(client, "alice2@example.com")
    bob_headers = await _user_headers(client, "bob2@example.com")

    order_resp = await client.post(
        "/api/orders",
        json={"restaurant_id": 10, "items": [{"menu_item_id": 1, "quantity": 1}]},
        headers=alice_headers,
    )
    order_id = order_resp.json()["id"]

    resp = await client.get(f"/api/orders/{order_id}", headers=bob_headers)
    assert resp.status_code == 403
