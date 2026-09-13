"""JWT verification for restaurant-service.

This service never issues tokens (that's order-service's job as the identity
owner). It only verifies tokens signed with the shared JWT_SECRET_KEY, which
is how two independent microservices can share stateless authentication
without calling each other on every request.
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload(dict):
    @property
    def user_id(self) -> int:
        return int(self["sub"])

    @property
    def role(self) -> str:
        return self["role"]


def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    return TokenPayload(payload)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> TokenPayload:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return decode_token(credentials.credentials)


def require_role(*allowed_roles: str):
    def _dependency(user: Annotated[TokenPayload, Depends(get_current_user)]) -> TokenPayload:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed_roles)}",
            )
        return user

    return _dependency


require_admin = require_role("admin")
