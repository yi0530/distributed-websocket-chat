import asyncio

from backend.config import NODE_ID
from backend.core.conversation_service import (
    create_group_conversation,
    get_conversation,
    get_conversation_participants,
    join_group_conversation,
    leave_group_conversation,
)
from backend.core.dedupe_service import has_processed_message, mark_message_processed
from backend.core.local_delivery_service import deliver_room_message_locally
from backend.core.protocol import build_message, send_ack, send_error, send_json
from backend.core.pubsub_service import publish_distributed_message
from backend.core.state import connections
from backend.utils.logger import logger


async def handle_create_room(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    name = proto.get("name")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    try:
        conversation = create_group_conversation(name, ctx.user_id)
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
                "participants": sorted(conversation["participants"]),
            },
        ),
    )


async def handle_join_room(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    try:
        conversation = join_group_conversation(conversation_id, ctx.user_id)
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

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    try:
        conversation = leave_group_conversation(conversation_id, ctx.user_id)
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

    try:
        members = get_conversation_participants(conversation_id)
        conversation = get_conversation(conversation_id)
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
                "conversation_id": conversation["conversation_id"],
                "name": conversation["name"],
                "participants": members,
            },
        ),
    )


async def handle_room_chat(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    payload = proto.get("payload")
    need_ack = bool(proto.get("need_ack"))
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        await send_error(websocket, "room_chat 报文缺少合法 text", msg_id=msg_id)
        return

    try:
        already = await asyncio.to_thread(has_processed_message, ctx.user_id, msg_id)
    except Exception:
        logger.exception("消息去重检查失败：user=%s msg_id=%s", ctx.user_id, msg_id)
        already = False
    if already:
        if need_ack:
            await send_ack(websocket, msg_id, status="duplicate")
        return

    try:
        conversation = get_conversation(conversation_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    if conversation["type"] != "group":
        await send_error(websocket, "该会话不是群聊会话", msg_id=msg_id, code=400)
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

    try:
        await asyncio.to_thread(
            publish_distributed_message,
            {
                "source_node_id": NODE_ID,
                "msg_id": msg_id,
                "msg_type": "room_chat",
                "conversation_id": conversation_id,
                "from_user_id": ctx.user_id,
                "payload": {
                    "text": text.strip(),
                },
            },
        )
    except Exception:
        logger.exception("发布分布式消息失败：user=%s msg_id=%s", ctx.user_id, msg_id)

    try:
        await asyncio.to_thread(mark_message_processed, ctx.user_id, msg_id)
    except Exception:
        logger.exception("标记消息已处理失败：user=%s msg_id=%s", ctx.user_id, msg_id)

    if need_ack:
        await send_ack(websocket, msg_id, status="processed")