import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app import messaging


def make_token(sub: int = 1, role: str = "admin") -> str:
    return jwt.encode({"sub": str(sub), "role": role}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {make_token(role='admin')}"}


@pytest.fixture
def user_headers():
    return {"Authorization": f"Bearer {make_token(sub=2, role='user')}"}


@pytest_asyncio.fixture
async def client(monkeypatch):
    # The RabbitMQ consumer is an external dependency we don't want running
    # (or even attempted) during unit/integration tests.
    async def _noop_start(self):
        return None

    async def _noop_stop(self):
        return None

    monkeypatch.setattr(messaging.OrderEventsConsumer, "start", _noop_start)
    monkeypatch.setattr(messaging.OrderEventsConsumer, "stop", _noop_stop)

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
