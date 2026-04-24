from backend.core.state import offline_messages


def store_offline_message(user_id: str, message: dict) -> None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("接收用户ID不合法")

    if not isinstance(message, dict):
        raise ValueError("离线消息必须是字典")

    offline_messages.setdefault(user_id, []).append(message)


def get_offline_messages(user_id: str) -> list[dict]:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("接收用户ID不合法")

    return list(offline_messages.get(user_id, []))


def remove_offline_message(user_id: str, msg_id: str) -> None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("接收用户ID不合法")

    if not isinstance(msg_id, str) or not msg_id.strip():
        raise ValueError("消息ID不合法")

    messages = offline_messages.get(user_id, [])
    offline_messages[user_id] = [
        msg for msg in messages
        if msg.get("msg_id") != msg_id
    ]

    if not offline_messages[user_id]:
        offline_messages.pop(user_id, None)


def clear_offline_messages(user_id: str) -> None:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("接收用户ID不合法")

    offline_messages.pop(user_id, None)