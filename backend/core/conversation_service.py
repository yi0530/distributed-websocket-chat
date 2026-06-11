import uuid

from backend.core.conversation_store import (
    delete_private_index,
    get_private_index,
    list_all_conversation_ids,
    load_conversation,
    save_conversation,
    set_private_index,
)


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

    save_conversation(conversation)
    return conversation


def get_conversation(conversation_id: str) -> dict:
    conversation = load_conversation(conversation_id)
    if conversation is None:
        raise ValueError("会话不存在")
    return conversation


def get_conversation_participants(conversation_id: str) -> list[str]:
    conversation = get_conversation(conversation_id)
    return sorted(conversation["participants"])


def join_group_conversation(conversation_id: str, user_id: str) -> dict:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户ID不能为空")

    conversation = get_conversation(conversation_id)

    if conversation["type"] != "group":
        raise ValueError("该会话不是群聊")

    conversation["participants"].add(user_id)
    save_conversation(conversation)
    return conversation


def leave_group_conversation(conversation_id: str, user_id: str) -> dict:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户ID不能为空")

    conversation = get_conversation(conversation_id)

    if conversation["type"] != "group":
        raise ValueError("该会话不是群聊")

    if user_id not in conversation["participants"]:
        raise ValueError("用户不在该会话中")

    conversation["participants"].remove(user_id)
    save_conversation(conversation)
    return conversation


def find_private_conversation(user_a: str, user_b: str) -> dict | None:
    if not all(isinstance(v, str) and v.strip() for v in [user_a, user_b]):
        raise ValueError("用户ID不合法")

    conversation_id = get_private_index(user_a, user_b)
    if not conversation_id:
        return None

    conversation = load_conversation(conversation_id)
    if conversation is None:
        delete_private_index(user_a, user_b)
        return None

    return conversation


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

    save_conversation(conversation)
    set_private_index(owner_id, target_user_id, conversation_id)
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


def list_group_conversations() -> list[dict]:
    """返回所有群聊会话摘要：conversation_id, name, participant_count, owner"""
    result = []
    for cid in list_all_conversation_ids():
        conv = load_conversation(cid)
        if conv is None or conv.get("type") != "group":
            continue
        result.append({
            "conversation_id": conv["conversation_id"],
            "name": conv.get("name", ""),
            "participant_count": len(conv.get("participants", set())),
            "owner": conv.get("owner", ""),
        })
    return result


def list_user_conversations(user_id: str) -> list[dict]:
    """返回用户参与的所有会话摘要"""
    result = []
    for cid in list_all_conversation_ids():
        conv = load_conversation(cid)
        if conv is None:
            continue
        participants = conv.get("participants", set())
        if user_id not in participants:
            continue
        item = {
            "conversation_id": conv["conversation_id"],
            "type": conv.get("type", ""),
            "name": conv.get("name", ""),
            "participant_count": len(participants),
        }
        if conv.get("type") == "private":
            peer = None
            for p in participants:
                if p != user_id:
                    peer = p
                    break
            item["peer"] = peer or ""
        result.append(item)
    return result


def seed_test_conversations_once() -> None:
    private_conv = load_conversation("conv_test_private")
    if private_conv is None:
        private_conv = {
            "conversation_id": "conv_test_private",
            "type": "private",
            "name": "",
            "owner": "user001",
            "participants": {"user001", "user002"},
        }
        save_conversation(private_conv)
        set_private_index("user001", "user002", "conv_test_private")

    group_conv = load_conversation("conv_test_group")
    if group_conv is None:
        group_conv = {
            "conversation_id": "conv_test_group",
            "type": "group",
            "name": "分布式测试群",
            "owner": "user001",
            "participants": {"user001", "user002", "admin"},
        }
        save_conversation(group_conv)