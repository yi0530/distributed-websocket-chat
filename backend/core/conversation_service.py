import uuid

from backend.core.state import conversations


def create_group_conversation(name: str, owner_id: str) -> dict:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("会话名不能为空")

    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("创建者不能为空")

    conversation_id = str(uuid.uuid4())

    conversation = {
        "conversation_id": conversation_id,
        "type": "group",
        "name": name.strip(),
        "owner": owner_id,
        "participants": {owner_id},
    }

    conversations[conversation_id] = conversation
    return conversation


def get_conversation(conversation_id: str) -> dict:
    conversation = conversations.get(conversation_id)
    if conversation is None:
        raise ValueError("会话不存在")
    return conversation


def join_group_conversation(conversation_id: str, user_id: str) -> dict:
    conversation = get_conversation(conversation_id)

    if conversation["type"] != "group":
        raise ValueError("该会话不是群聊，不能执行加入操作")

    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户ID不合法")

    conversation["participants"].add(user_id)
    return conversation


def leave_group_conversation(conversation_id: str, user_id: str) -> dict:
    conversation = get_conversation(conversation_id)

    if conversation["type"] != "group":
        raise ValueError("该会话不是群聊，不能执行退出操作")

    if user_id not in conversation["participants"]:
        raise ValueError("用户不在该会话中")

    conversation["participants"].remove(user_id)

    # 如果群聊没人了，直接删除
    if not conversation["participants"]:
        deleted_conversation = conversations.pop(conversation_id)
        return deleted_conversation

    return conversation


def get_conversation_participants(conversation_id: str) -> list[str]:
    conversation = get_conversation(conversation_id)
    return sorted(conversation["participants"])

def find_private_conversation(user_a: str, user_b: str) -> dict | None:
    target_participants = {user_a, user_b}

    for conversation in conversations.values():
        if conversation["type"] != "private":
            continue

        if conversation["participants"] == target_participants:
            return conversation

    return None

def create_or_get_private_conversation(owner_id: str, target_user_id: str) -> dict:
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("当前用户ID不合法")

    if not isinstance(target_user_id, str) or not target_user_id.strip():
        raise ValueError("目标用户ID不合法")

    if owner_id == target_user_id:
        raise ValueError("不能和自己创建私聊会话")

    existing = find_private_conversation(owner_id, target_user_id)
    if existing is not None:
        return existing

    conversation_id = str(uuid.uuid4())

    conversation = {
        "conversation_id": conversation_id,
        "type": "private",
        "name": "",
        "owner": owner_id,
        "participants": {owner_id, target_user_id},
    }

    conversations[conversation_id] = conversation
    return conversation

def get_other_private_participant(conversation_id: str, current_user_id: str) -> str:
    conversation = get_conversation(conversation_id)

    if conversation["type"] != "private":
        raise ValueError("该会话不是私聊会话")

    participants = conversation["participants"]

    if current_user_id not in participants:
        raise ValueError("当前用户不属于该私聊会话")

    if len(participants) != 2:
        raise ValueError("私聊会话参与者数量异常")

    for user_id in participants:
        if user_id != current_user_id:
            return user_id

    raise ValueError("未找到私聊对方用户")