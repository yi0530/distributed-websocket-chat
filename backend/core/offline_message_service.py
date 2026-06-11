# NOTE: Functions in this module use synchronous Redis calls.
# They MUST be called via asyncio.to_thread() from async code paths
# to avoid blocking the event loop.
import json

from backend.config import REDIS_KEY_PREFIX, REDIS_OFFLINE_TTL_SECONDS
from backend.core.redis_client import redis_client


def _offline_key(user_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:offline_messages:{user_id}"


def store_offline_message(user_id: str, message: dict) -> None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("接收用户ID不合法")

    if not isinstance(message, dict):
        raise ValueError("离线消息必须是字典")

    key = _offline_key(user_id)
    redis_client.rpush(key, json.dumps(message, ensure_ascii=False))
    redis_client.expire(key, REDIS_OFFLINE_TTL_SECONDS)


def get_offline_messages(user_id: str) -> list[dict]:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("接收用户ID不合法")

    key = _offline_key(user_id)
    raw_list = redis_client.lrange(key, 0, -1)

    result: list[dict] = []
    for item in raw_list:
        try:
            parsed = json.loads(item)
            if isinstance(parsed, dict):
                result.append(parsed)
        except json.JSONDecodeError:
            continue

    return result


def remove_offline_message(user_id: str, msg_id: str) -> None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("接收用户ID不合法")

    if not isinstance(msg_id, str) or not msg_id.strip():
        raise ValueError("消息ID不合法")

    key = _offline_key(user_id)
    messages = get_offline_messages(user_id)

    kept = [msg for msg in messages if msg.get("msg_id") != msg_id]

    redis_client.delete(key)

    if kept:
        for msg in kept:
            redis_client.rpush(key, json.dumps(msg, ensure_ascii=False))
        redis_client.expire(key, REDIS_OFFLINE_TTL_SECONDS)


def clear_offline_messages(user_id: str) -> None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("接收用户ID不合法")

    redis_client.delete(_offline_key(user_id))