from backend.core.protocol import build_message, send_error, send_json
from backend.core.conversation_service import (
    create_group_conversation,
    get_conversation,
    get_conversation_participants,
    join_group_conversation,
    leave_group_conversation,
)
from backend.core.state import connections


async def handle_create_room(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    name = proto.get("name")
    ctx = connections[websocket]

    if not isinstance(name, str) or not name.strip():
        await send_error(websocket, "create_room 报文缺少合法 name", msg_id=msg_id)
        return

    try:
        conversation = create_group_conversation(name=name, owner_id=ctx.user_id)
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
                "conversation_id": conversation["conversation_id"],
                "name": conversation["name"],
                "owner": conversation["owner"],
                "type": conversation["type"],
            },
        ),
    )


async def handle_join_room(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    ctx = connections[websocket]

    if not isinstance(conversation_id, str) or not conversation_id.strip():
        await send_error(websocket, "join_room 报文缺少合法 conversation_id", msg_id=msg_id)
        return

    try:
        conversation = join_group_conversation(conversation_id=conversation_id, user_id=ctx.user_id)
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
                "conversation_id": conversation["conversation_id"],
                "name": conversation["name"],
                "user_id": ctx.user_id,
            },
        ),
    )


async def handle_leave_room(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    ctx = connections[websocket]

    if not isinstance(conversation_id, str) or not conversation_id.strip():
        await send_error(websocket, "leave_room 报文缺少合法 conversation_id", msg_id=msg_id)
        return

    try:
        conversation = leave_group_conversation(conversation_id=conversation_id, user_id=ctx.user_id)
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
                "conversation_id": conversation["conversation_id"],
                "name": conversation["name"],
                "user_id": ctx.user_id,
            },
        ),
    )

async def handle_get_room_members(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")

    if not isinstance(conversation_id, str) or not conversation_id.strip():
        await send_error(websocket, "get_room_members 报文缺少合法 conversation_id", msg_id=msg_id)
        return

    try:
        participants = get_conversation_participants(conversation_id=conversation_id)
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
                "conversation_id": conversation_id,
                "participants": participants,
            },
        ),
    )


async def handle_room_chat(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    payload = proto.get("payload")
    ctx = connections[websocket]

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        await send_error(websocket, "room_chat 报文缺少合法 text", msg_id=msg_id)
        return

    try:
        conversation = get_conversation(conversation_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    if ctx.user_id not in conversation["participants"]:
        await send_error(websocket, "你不在该会话中，无法发送消息", msg_id=msg_id, code=403)
        return

    response = build_message(
        "room_chat",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "from_user_id": ctx.user_id,
            "text": text.strip(),
        },
    )

    participants = conversation["participants"]

    for target_ws, target_ctx in connections.items():
        if target_ctx.is_authenticated and target_ctx.user_id in participants:
            await send_json(target_ws, response)