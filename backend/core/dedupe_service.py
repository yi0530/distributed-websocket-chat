from backend.config import DEDUPE_TTL_SECONDS, REDIS_KEY_PREFIX
from backend.core.redis_client import redis_client


def _message_dedupe_key(sender_id: str, msg_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:dedupe:message:{sender_id}:{msg_id}"


def _node_delivery_dedupe_key(node_id: str, sender_id: str, msg_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:dedupe:node_delivery:{node_id}:{sender_id}:{msg_id}"


def has_processed_message(sender_id: str, msg_id: str) -> bool:
    if not isinstance(sender_id, str) or not sender_id.strip():
        raise ValueError("sender_id 不合法")
    if not isinstance(msg_id, str) or not msg_id.strip():
        raise ValueError("msg_id 不合法")

    return redis_client.exists(_message_dedupe_key(sender_id, msg_id)) == 1


def mark_message_processed(sender_id: str, msg_id: str) -> None:
    if not isinstance(sender_id, str) or not sender_id.strip():
        raise ValueError("sender_id 不合法")
    if not isinstance(msg_id, str) or not msg_id.strip():
        raise ValueError("msg_id 不合法")

    redis_client.set(
        _message_dedupe_key(sender_id, msg_id),
        "1",
        ex=DEDUPE_TTL_SECONDS,
    )


def has_node_delivery_processed(node_id: str, sender_id: str, msg_id: str) -> bool:
    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("node_id 不合法")
    if not isinstance(sender_id, str) or not sender_id.strip():
        raise ValueError("sender_id 不合法")
    if not isinstance(msg_id, str) or not msg_id.strip():
        raise ValueError("msg_id 不合法")

    return redis_client.exists(_node_delivery_dedupe_key(node_id, sender_id, msg_id)) == 1


def mark_node_delivery_processed(node_id: str, sender_id: str, msg_id: str) -> None:
    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("node_id 不合法")
    if not isinstance(sender_id, str) or not sender_id.strip():
        raise ValueError("sender_id 不合法")
    if not isinstance(msg_id, str) or not msg_id.strip():
        raise ValueError("msg_id 不合法")

    redis_client.set(
        _node_delivery_dedupe_key(node_id, sender_id, msg_id),
        "1",
        ex=DEDUPE_TTL_SECONDS,
    )