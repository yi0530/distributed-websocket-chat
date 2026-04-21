import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from backend.config import JWT_ALGORITHM, JWT_EXP_HOURS, JWT_SECRET


def generate_jwt_token(user_id: str) -> str:
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": user_id,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            return None
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def verify_jwt_token(token: str) -> bool:
    return decode_jwt_token(token) is not None