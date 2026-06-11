from backend.config import ONLINE_STATUS_TTL_SECONDS, REDIS_KEY_PREFIX
from backend.core.redis_client import redis_client


def _online_user_key(user_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}:online:user:{user_id}"


def set_user_online(user_id: str, node_id: str) -> None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户ID不合法")
    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("节点ID不合法")

    redis_client.set(
        _online_user_key(user_id),
        node_id,
        ex=ONLINE_STATUS_TTL_SECONDS,
    )


def refresh_user_online(user_id: str, owner_node_id: str) -> bool:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户ID不合法")
    if not isinstance(owner_node_id, str) or not owner_node_id.strip():
        raise ValueError("节点ID不合法")

    key = _online_user_key(user_id)
    current = redis_client.get(key)

    if current != owner_node_id:
        return False

    redis_client.expire(key, ONLINE_STATUS_TTL_SECONDS)
    return True


def get_user_online_node(user_id: str) -> str | None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户ID不合法")

    value = redis_client.get(_online_user_key(user_id))
    if isinstance(value, str) and value.strip():
        return value
    return None


def list_all_online_users() -> list[str]:
    """扫描 Redis 中所有在线用户 key，返回 user_id 列表。"""
    pattern = f"{REDIS_KEY_PREFIX}:online:user:*"
    keys = redis_client.keys(pattern)
    prefix = f"{REDIS_KEY_PREFIX}:online:user:"
    return [k[len(prefix):] for k in keys if k.startswith(prefix)]


def clear_user_online(user_id: str, owner_node_id: str | None = None) -> None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户ID不合法")

    key = _online_user_key(user_id)

    if owner_node_id is None:
        redis_client.delete(key)
        return

    current = redis_client.get(key)
    if current == owner_node_id:
        redis_client.delete(key)