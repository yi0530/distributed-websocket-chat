import json

from backend.config import REDIS_KEY_PREFIX
from backend.core.redis_client import redis_client


def _conversation_key(conversation_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:conversation:{conversation_id}"


def _private_index_key(user_a: str, user_b: str) -> str:
    a, b = sorted([user_a, user_b])
    return f"{REDIS_KEY_PREFIX}:private_index:{a}:{b}"


def _serialize_conversation(conversation: dict) -> str:
    data = dict(conversation)
    participants = data.get("participants", set())
    if isinstance(participants, set):
        data["participants"] = sorted(participants)
    return json.dumps(data, ensure_ascii=False)


def _deserialize_conversation(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    participants = data.get("participants", [])
    if isinstance(participants, list):
        data["participants"] = set(participants)

    return data


def save_conversation(conversation: dict) -> None:
    conversation_id = conversation.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id 不合法")

    redis_client.set(_conversation_key(conversation_id), _serialize_conversation(conversation))


def load_conversation(conversation_id: str) -> dict | None:
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id 不合法")

    raw = redis_client.get(_conversation_key(conversation_id))
    if not raw:
        return None

    return _deserialize_conversation(raw)


def delete_conversation(conversation_id: str) -> None:
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id 不合法")

    redis_client.delete(_conversation_key(conversation_id))


def set_private_index(user_a: str, user_b: str, conversation_id: str) -> None:
    if not all(isinstance(v, str) and v.strip() for v in [user_a, user_b, conversation_id]):
        raise ValueError("私聊索引参数不合法")

    redis_client.set(_private_index_key(user_a, user_b), conversation_id)


def get_private_index(user_a: str, user_b: str) -> str | None:
    if not all(isinstance(v, str) and v.strip() for v in [user_a, user_b]):
        raise ValueError("私聊索引参数不合法")

    value = redis_client.get(_private_index_key(user_a, user_b))
    if isinstance(value, str) and value.strip():
        return value
    return None


def delete_private_index(user_a: str, user_b: str) -> None:
    if not all(isinstance(v, str) and v.strip() for v in [user_a, user_b]):
        raise ValueError("私聊索引参数不合法")

    redis_client.delete(_private_index_key(user_a, user_b))