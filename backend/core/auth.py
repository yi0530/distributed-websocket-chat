import uuid
from datetime import timezone, datetime, timedelta
from typing import Any

import jwt

from backend.config import JWT_ALGORITHM, JWT_EXP_HOURS, JWT_SECRET


def generate_jwt_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXP_HOURS),
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


def get_token_exp_ts(payload: dict[str, Any]) -> int | None:
    exp = payload.get("exp")
    if isinstance(exp, int):
        return exp
    if isinstance(exp, float):
        return int(exp)
    if isinstance(exp, datetime):
        return int(exp.timestamp())
    return None