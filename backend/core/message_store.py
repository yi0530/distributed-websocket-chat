"""永久消息存储 — 所有聊天消息写入 Redis List，不删除，不设 TTL。"""
import json
from time import time

from backend.config import REDIS_KEY_PREFIX
from backend.core.redis_client import redis_client


def _message_key(conversation_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:messages:{conversation_id}"


def save_message(conversation_id: str, msg: dict) -> None:
    """写入一条聊天消息到永久存储。"""
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id 不合法")
    if not isinstance(msg, dict):
        raise ValueError("消息必须是字典")

    record = {
        "msg_id": msg.get("msg_id", ""),
        "msg_type": msg.get("msg_type", ""),
        "conversation_id": conversation_id,
        "from_user_id": msg.get("from_user_id", ""),
        "text": msg.get("text", ""),
        "timestamp": msg.get("timestamp", int(time())),
    }
    redis_client.lpush(_message_key(conversation_id), json.dumps(record, ensure_ascii=False))


def get_recent_messages(conversation_id: str, count: int = 50) -> list[dict]:
    """获取最近 N 条消息（最新在前）。"""
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("conversation_id 不合法")

    raw_list = redis_client.lrange(_message_key(conversation_id), 0, count - 1)
    result = []
    for item in raw_list:
        try:
            parsed = json.loads(item)
            if isinstance(parsed, dict):
                result.append(parsed)
        except json.JSONDecodeError:
            continue
    return result
