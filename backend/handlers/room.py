from time import time

from backend.core.protocol import build_message, send_error, send_json, send_ack
from backend.core.conversation_service import (
    create_group_conversation,
    get_conversation,
    get_conversation_participants,
    join_group_conversation,
    leave_group_conversation,
)
from backend.core.state import connections,processed_message_keys
from backend.core.offline_message_service import store_offline_message
from backend.core.local_delivery_service import deliver_room_message_locally
from backend.config import NODE_ID
from backend.core.pubsub_service import publish_distributed_message


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

async def handle_get_participants(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")

    if not isinstance(conversation_id, str) or not conversation_id.strip():
        await send_error(websocket, "get_participants 报文缺少合法 conversation_id", msg_id=msg_id)
        return

    try:
        participants = get_conversation_participants(conversation_id=conversation_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    await send_json(
        websocket,
        build_message(
            "participants",
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

    dedupe_key = f"{ctx.user_id}:{msg_id}"
    need_ack = bool(proto.get("need_ack"))

    # 重复消息：不重复广播，但可再次回 ACK
    if dedupe_key in processed_message_keys:
        if need_ack:
            await send_ack(websocket, msg_id, status="duplicate")
        return

    try:
        conversation = get_conversation(conversation_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    if ctx.user_id not in conversation["participants"]:
        await send_error(websocket, "你不在该会话中，无法发送消息", msg_id=msg_id, code=403)
        return

    await deliver_room_message_locally(
        msg_id=msg_id,
        conversation_id=conversation_id,
        from_user_id=ctx.user_id,
        text=text.strip(),
    )
    publish_distributed_message(
    {
        "source_node_id": NODE_ID,
        "msg_id": msg_id,
        "msg_type": "room_chat",
        "conversation_id": conversation_id,
        "from_user_id": ctx.user_id,
        "payload": {
            "text": text.strip(),
        },
    }
)

    processed_message_keys[dedupe_key] = int(time())

    if need_ack:
        await send_ack(websocket, msg_id, status="processed")