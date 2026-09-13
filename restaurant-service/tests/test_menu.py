import pytest

pytestmark = pytest.mark.asyncio


async def _create_restaurant(client, admin_headers, name="Test Restaurant"):
    resp = await client.post("/api/restaurants", json={"name": name, "address": "Addr"}, headers=admin_headers)
    return resp.json()["id"]


async def test_create_menu_item_requires_admin(client, user_headers):
    response = await client.post(
        "/api/restaurants/1/menu-items",
        json={"name": "Burger", "price": 5.0},
        headers=user_headers,
    )
    assert response.status_code == 403


async def test_create_menu_item_for_unknown_restaurant_returns_404(client, admin_headers):
    response = await client.post(
        "/api/restaurants/9999/menu-items", json={"name": "Burger", "price": 5.0}, headers=admin_headers
    )
    assert response.status_code == 404


async def test_create_and_get_menu_item(client, admin_headers):
    restaurant_id = await _create_restaurant(client, admin_headers)
    create_resp = await client.post(
        f"/api/restaurants/{restaurant_id}/menu-items",
        json={"name": "Cheeseburger", "price": 6.5},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    item_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/menu-items/{item_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["price"] == 6.5


async def test_update_menu_item_price_and_availability(client, admin_headers):
    restaurant_id = await _create_restaurant(client, admin_headers)
    create_resp = await client.post(
        f"/api/restaurants/{restaurant_id}/menu-items",
        json={"name": "Fries", "price": 3.0},
        headers=admin_headers,
    )
    item_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/menu-items/{item_id}",
        json={"price": 3.5, "is_available": False},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["price"] == 3.5
    assert body["is_available"] is False


async def test_get_unknown_menu_item_returns_404(client):
    response = await client.get("/api/menu-items/9999")
    assert response.status_code == 404


async def test_internal_lookup_returns_only_matching_ids(client, admin_headers):
    restaurant_id = await _create_restaurant(client, admin_headers)
    ids = []
    for name, price in [("A", 1.0), ("B", 2.0)]:
        resp = await client.post(
            f"/api/restaurants/{restaurant_id}/menu-items",
            json={"name": name, "price": price},
            headers=admin_headers,
        )
        ids.append(resp.json()["id"])

    lookup_resp = await client.post("/internal/menu-items/lookup", json={"ids": ids + [999999]})
    assert lookup_resp.status_code == 200
    found_ids = {item["id"] for item in lookup_resp.json()}
    assert found_ids == set(ids)
