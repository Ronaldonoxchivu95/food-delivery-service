import jwt
import pytest

from app.config import settings
from app.security import create_access_token, decode_access_token, hash_password, verify_password

pytestmark = pytest.mark.asyncio


async def test_password_hash_roundtrip():
    hashed = hash_password("super-secret")
    assert hashed != "super-secret"
    assert verify_password("super-secret", hashed) is True


async def test_password_verify_rejects_wrong_password():
    hashed = hash_password("super-secret")
    assert verify_password("wrong-password", hashed) is False


async def test_access_token_roundtrip():
    token = create_access_token(subject=42, role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


async def test_access_token_rejects_tampering():
    token = create_access_token(subject=1, role="user")
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(token, "wrong-secret", algorithms=[settings.JWT_ALGORITHM])
