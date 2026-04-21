import uuid

from backend.core.state import rooms


def create_room(name: str, owner_id: str) -> dict:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("房间名不能为空")

    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("创建者不能为空")

    room_id = str(uuid.uuid4())

    room = {
        "room_id": room_id,
        "name": name.strip(),
        "owner": owner_id,
        "members": {owner_id},
    }

    rooms[room_id] = room
    return room


def join_room(room_id: str, user_id: str) -> dict:
    room = rooms.get(room_id)
    if room is None:
        raise ValueError("房间不存在")

    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("用户ID不合法")

    room["members"].add(user_id)
    return room


def leave_room(room_id: str, user_id: str) -> dict:
    room = rooms.get(room_id)
    if room is None:
        raise ValueError("房间不存在")

    if user_id not in room["members"]:
        raise ValueError("用户不在房间中")

    room["members"].remove(user_id)

    # 如果房间没人了，直接删除
    if not room["members"]:
        deleted_room = rooms.pop(room_id)
        return deleted_room

    return room


def get_room_members(room_id: str) -> list[str]:
    room = rooms.get(room_id)
    if room is None:
        raise ValueError("房间不存在")

    return sorted(room["members"])

def get_room(room_id: str) -> dict:
    room = rooms.get(room_id)
    if room is None:
        raise ValueError("房间不存在")
    return room