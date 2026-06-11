import asyncio

from backend.config import NODE_ID
from backend.core.conversation_service import (
    create_group_conversation,
    get_conversation,
    get_conversation_participants,
    join_group_conversation,
    leave_group_conversation,
    list_group_conversations,
)
from backend.core.message_store import get_recent_messages
from backend.core.dedupe_service import has_processed_message, mark_message_processed
from backend.core.local_delivery_service import deliver_room_message_locally, get_online_websockets_by_user_id
from backend.core.message_store import save_message
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
        conversation = await asyncio.to_thread(create_group_conversation, name, ctx.user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("创建群聊异常：name=%s user=%s", name, ctx.user_id)
        await send_error(websocket, "创建群聊失败，请重试", msg_id=msg_id, code=500)
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
        conversation = await asyncio.to_thread(join_group_conversation, conversation_id, ctx.user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("加入群聊异常：cid=%s user=%s", conversation_id, ctx.user_id)
        await send_error(websocket, "加入群聊失败，请重试", msg_id=msg_id, code=500)
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
        conversation = await asyncio.to_thread(leave_group_conversation, conversation_id, ctx.user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("离开群聊异常：cid=%s user=%s", conversation_id, ctx.user_id)
        await send_error(websocket, "操作失败，请重试", msg_id=msg_id, code=500)
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
        members = await asyncio.to_thread(get_conversation_participants, conversation_id)
        conversation = await asyncio.to_thread(get_conversation, conversation_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("获取群成员异常：cid=%s", conversation_id)
        await send_error(websocket, "获取群成员失败，请重试", msg_id=msg_id, code=500)
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
        conversation = await asyncio.to_thread(get_conversation, conversation_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("获取会话异常：cid=%s", conversation_id)
        await send_error(websocket, "发送失败，请重试", msg_id=msg_id, code=500)
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
            save_message,
            conversation_id,
            {
                "msg_id": msg_id,
                "msg_type": "room_chat",
                "from_user_id": ctx.user_id,
                "text": text.strip(),
                "timestamp": proto.get("timestamp", 0),
            },
        )
    except Exception:
        logger.exception("保存群聊消息失败：msg_id=%s", msg_id)

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


async def handle_list_rooms(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    try:
        rooms = await asyncio.to_thread(list_group_conversations)
    except Exception:
        logger.exception("列出群聊失败")
        await send_error(websocket, "获取群聊列表失败，请重试", msg_id=msg_id, code=500)
        return

    await send_json(
        websocket,
        build_message(
            "room_list",
            msg_id=msg_id,
            code=200,
            content={"rooms": rooms},
        ),
    )


async def handle_get_chat_history(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    try:
        conversation = await asyncio.to_thread(get_conversation, conversation_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("获取会话异常：cid=%s", conversation_id)
        await send_error(websocket, "获取历史失败，请重试", msg_id=msg_id, code=500)
        return

    if ctx.user_id not in conversation.get("participants", set()):
        await send_error(websocket, "你不在该会话中", msg_id=msg_id, code=403)
        return

    try:
        messages = await asyncio.to_thread(get_recent_messages, conversation_id, 50)
    except Exception:
        logger.exception("获取历史消息失败：cid=%s", conversation_id)
        await send_error(websocket, "获取历史失败，请重试", msg_id=msg_id, code=500)
        return

    await send_json(
        websocket,
        build_message(
            "chat_history",
            msg_id=msg_id,
            code=200,
            content={
                "conversation_id": conversation_id,
                "messages": list(reversed(messages)),
            },
        ),
    )


async def _broadcast_to_conversation(conversation_id: str, msg: dict, skip_user_id: str = ""):
    """广播消息给会话中所有在线参与者，跳过指定用户。"""
    try:
        conversation = await asyncio.to_thread(get_conversation, conversation_id)
    except ValueError:
        return
    for user_id in conversation.get("participants", set()):
        if user_id == skip_user_id:
            continue
        for ws in get_online_websockets_by_user_id(user_id):
            await send_json(ws, msg)


async def handle_read_receipt(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    last_read_msg_id = proto.get("last_read_msg_id", "")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    receipt = build_message(
        "read_receipt",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "user_id": ctx.user_id,
            "last_read_msg_id": last_read_msg_id,
        },
    )
    await _broadcast_to_conversation(conversation_id, receipt, skip_user_id=ctx.user_id)


async def handle_typing_start(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    notify = build_message(
        "user_typing",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "user_id": ctx.user_id,
            "typing": True,
        },
    )
    await _broadcast_to_conversation(conversation_id, notify, skip_user_id=ctx.user_id)


async def handle_typing_stop(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    notify = build_message(
        "user_typing",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "user_id": ctx.user_id,
            "typing": False,
        },
    )
    await _broadcast_to_conversation(conversation_id, notify, skip_user_id=ctx.user_id)