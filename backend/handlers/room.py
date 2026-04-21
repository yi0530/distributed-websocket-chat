from backend.core.protocol import build_message, send_error, send_json
from backend.core.room_service import (
    create_room,
    get_room_members,
    join_room,
    leave_room,
)
from backend.core.state import connections
from backend.core.protocol import build_message, send_error, send_json
from backend.core.room_service import get_room
from backend.core.state import connections


async def handle_create_room(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    name = proto.get("name")
    ctx = connections[websocket]

    if not isinstance(name, str) or not name.strip():
        await send_error(websocket, "create_room 报文缺少合法 name", msg_id=msg_id)
        return

    try:
        room = create_room(name=name, owner_id=ctx.user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    await send_json(
        websocket,
        build_message(
            "room_created",
            msg_id=msg_id,
            code=200,
            content={
                "room_id": room["room_id"],
                "name": room["name"],
                "owner": room["owner"],
            },
        ),
    )


async def handle_join_room(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    room_id = proto.get("room_id")
    ctx = connections[websocket]

    if not isinstance(room_id, str) or not room_id.strip():
        await send_error(websocket, "join_room 报文缺少合法 room_id", msg_id=msg_id)
        return

    try:
        room = join_room(room_id=room_id, user_id=ctx.user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    await send_json(
        websocket,
        build_message(
            "room_joined",
            msg_id=msg_id,
            code=200,
            content={
                "room_id": room["room_id"],
                "name": room["name"],
                "user_id": ctx.user_id,
            },
        ),
    )


async def handle_leave_room(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    room_id = proto.get("room_id")
    ctx = connections[websocket]

    if not isinstance(room_id, str) or not room_id.strip():
        await send_error(websocket, "leave_room 报文缺少合法 room_id", msg_id=msg_id)
        return

    try:
        room = leave_room(room_id=room_id, user_id=ctx.user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    await send_json(
        websocket,
        build_message(
            "room_left",
            msg_id=msg_id,
            code=200,
            content={
                "room_id": room["room_id"],
                "name": room["name"],
                "user_id": ctx.user_id,
            },
        ),
    )


async def handle_get_room_members(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    room_id = proto.get("room_id")

    if not isinstance(room_id, str) or not room_id.strip():
        await send_error(websocket, "get_room_members 报文缺少合法 room_id", msg_id=msg_id)
        return

    try:
        members = get_room_members(room_id=room_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    await send_json(
        websocket,
        build_message(
            "room_members",
            msg_id=msg_id,
            code=200,
            content={
                "room_id": room_id,
                "members": members,
            },
        ),
    )

async def handle_room_chat(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    room_id = proto.get("room_id")
    payload = proto.get("payload")
    ctx = connections[websocket]

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        await send_error(websocket, "room_chat 报文缺少合法 text", msg_id=msg_id)
        return

    try:
        room = get_room(room_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    if ctx.user_id not in room["members"]:
        await send_error(websocket, "你不在该房间中，无法发送消息", msg_id=msg_id, code=403)
        return

    response = build_message(
        "room_chat",
        msg_id=msg_id,
        code=200,
        content={
            "room_id": room_id,
            "from_user_id": ctx.user_id,
            "text": text.strip(),
        },
    )

    # 广播给房间内所有在线成员
    room_members = room["members"]
    for target_ws, target_ctx in connections.items():
        if target_ctx.is_authenticated and target_ctx.user_id in room_members:
            await send_json(target_ws, response)