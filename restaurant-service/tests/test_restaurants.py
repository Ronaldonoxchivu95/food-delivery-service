import pytest

pytestmark = pytest.mark.asyncio


async def test_create_restaurant_requires_auth(client):
    response = await client.post("/api/restaurants", json={"name": "Pizza Place", "address": "1 Main St"})
    assert response.status_code == 401


async def test_create_restaurant_forbidden_for_regular_user(client, user_headers):
    response = await client.post(
        "/api/restaurants",
        json={"name": "Pizza Place", "address": "1 Main St"},
        headers=user_headers,
    )
    assert response.status_code == 403


async def test_admin_can_create_and_fetch_restaurant(client, admin_headers):
    create_resp = await client.post(
        "/api/restaurants",
        json={"name": "Pizza Place", "address": "1 Main St", "description": "Best pizza in town"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    restaurant = create_resp.json()
    assert restaurant["name"] == "Pizza Place"
    assert restaurant["is_active"] is True

    get_resp = await client.get(f"/api/restaurants/{restaurant['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["address"] == "1 Main St"


async def test_get_unknown_restaurant_returns_404(client):
    response = await client.get("/api/restaurants/9999")
    assert response.status_code == 404


async def test_list_restaurants_reflects_created_ones(client, admin_headers):
    for name in ["Sushi Bar", "Burger House"]:
        await client.post(
            "/api/restaurants", json={"name": name, "address": "Somewhere"}, headers=admin_headers
        )

    response = await client.get("/api/restaurants")
    assert response.status_code == 200
    names = {r["name"] for r in response.json()}
    assert {"Sushi Bar", "Burger House"}.issubset(names)


async def test_update_restaurant_invalidates_and_reflects_changes(client, admin_headers):
    create_resp = await client.post(
        "/api/restaurants", json={"name": "Old Name", "address": "Addr"}, headers=admin_headers
    )
    restaurant_id = create_resp.json()["id"]

    # Warm the cache
    await client.get(f"/api/restaurants/{restaurant_id}")

    update_resp = await client.patch(
        f"/api/restaurants/{restaurant_id}", json={"name": "New Name"}, headers=admin_headers
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "New Name"

    # Cache must have been invalidated, so this reflects the update, not the
    # stale cached copy.
    get_resp = await client.get(f"/api/restaurants/{restaurant_id}")
    assert get_resp.json()["name"] == "New Name"


async def test_menu_endpoint_returns_categories_with_items_eagerly_loaded(client, admin_headers):
    create_resp = await client.post(
        "/api/restaurants", json={"name": "Noodle Bar", "address": "Addr"}, headers=admin_headers
    )
    restaurant_id = create_resp.json()["id"]

    category_resp = await client.post(
        f"/api/restaurants/{restaurant_id}/categories", json={"name": "Soups"}, headers=admin_headers
    )
    assert category_resp.status_code == 201
    category_id = category_resp.json()["id"]

    await client.post(
        f"/api/restaurants/{restaurant_id}/menu-items",
        json={"name": "Ramen", "price": 9.5, "category_id": category_id},
        headers=admin_headers,
    )

    menu_resp = await client.get(f"/api/restaurants/{restaurant_id}/menu")
    assert menu_resp.status_code == 200
    menu = menu_resp.json()
    assert menu["categories"][0]["name"] == "Soups"
    assert menu["categories"][0]["items"][0]["name"] == "Ramen"


async def test_deactivate_restaurant_removes_it_from_public_listing(client, admin_headers):
    create_resp = await client.post(
        "/api/restaurants", json={"name": "Temporary Place", "address": "Addr"}, headers=admin_headers
    )
    restaurant_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/restaurants/{restaurant_id}", headers=admin_headers)
    assert delete_resp.status_code == 204

    list_resp = await client.get("/api/restaurants")
    names = {r["name"] for r in list_resp.json()}
    assert "Temporary Place" not in names
