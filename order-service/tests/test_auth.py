import pytest

from app.config import settings
from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def test_register_and_login_returns_working_token(client):
    token = await register_and_login(client, "alice@example.com")

    me_resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "user"


async def test_register_duplicate_email_returns_409(client):
    await register_and_login(client, "bob@example.com")
    resp = await client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "password": "password123", "full_name": "Bob Again"},
    )
    assert resp.status_code == 409


async def test_login_with_wrong_password_returns_401(client):
    await register_and_login(client, "carol@example.com")
    resp = await client.post(
        "/api/auth/login", json={"email": "carol@example.com", "password": "not-the-password"}
    )
    assert resp.status_code == 401


async def test_register_with_correct_admin_secret_grants_admin_role(client):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "admin@example.com",
            "password": "password123",
            "full_name": "Admin",
            "admin_secret": settings.ADMIN_REGISTRATION_SECRET,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "admin"


async def test_register_with_wrong_admin_secret_returns_400(client):
    # A wrong admin secret must fail loudly (400) rather than silently
    # falling back to a regular user account — see app/routers/auth.py.
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "notadmin@example.com",
            "password": "password123",
            "full_name": "Not Admin",
            "admin_secret": "totally-wrong",
        },
    )
    assert resp.status_code == 400


async def test_me_requires_authentication(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
