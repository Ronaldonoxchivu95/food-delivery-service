import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import messaging
from app.database import Base, get_db
from app.main import app


@pytest_asyncio.fixture
async def client(monkeypatch):
    # RabbitMQ is an external dependency: mock it out so tests are hermetic
    # and don't depend on a broker being reachable.
    async def _noop_connect(self):
        return None

    async def _noop_close(self):
        return None

    monkeypatch.setattr(messaging.OrderEventsPublisher, "connect", _noop_connect)
    monkeypatch.setattr(messaging.OrderEventsPublisher, "close", _noop_close)

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_db():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def published_events(monkeypatch):
    """Capture events that would have been published to RabbitMQ instead of
    requiring a real broker."""
    events = []

    async def fake_publish(self, routing_key, payload):
        events.append((routing_key, payload))

    monkeypatch.setattr(messaging.OrderEventsPublisher, "publish", fake_publish)
    return events


async def register_and_login(client, email: str, password: str = "password123", admin_secret: str | None = None) -> str:
    payload = {"email": email, "password": password, "full_name": "Test User"}
    if admin_secret:
        payload["admin_secret"] = admin_secret
    register_resp = await client.post("/api/auth/register", json=payload)
    assert register_resp.status_code == 201, register_resp.text

    login_resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    return login_resp.json()["access_token"]
