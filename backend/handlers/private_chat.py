import asyncio

from backend.config import NODE_ID
from backend.core.conversation_service import (
    create_or_get_private_conversation,
    get_conversation,
    get_other_private_participant,
    list_user_conversations,
)
from backend.core.dedupe_service import has_processed_message, mark_message_processed
from backend.core.local_delivery_service import deliver_private_message_locally
from backend.core.protocol import build_message, send_ack, send_error, send_json
from backend.core.pubsub_service import publish_distributed_message
from backend.core.state import connections
from backend.utils.logger import logger


async def handle_create_private_conversation(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    target_user_id = proto.get("target_user_id")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    if not isinstance(target_user_id, str) or not target_user_id.strip():
        await send_error(websocket, "目标用户ID不合法", msg_id=msg_id, code=400)
        return

    if target_user_id == ctx.user_id:
        await send_error(websocket, "不能和自己创建私聊会话", msg_id=msg_id, code=400)
        return

    try:
        conversation = await asyncio.to_thread(create_or_get_private_conversation, ctx.user_id, target_user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("创建私聊异常：from=%s target=%s", ctx.user_id, target_user_id)
        await send_error(websocket, "创建私聊失败，请重试", msg_id=msg_id, code=500)
        return

    await send_json(
        websocket,
        build_message(
            "private_conversation_created",
            msg_id=msg_id,
            code=200,
            content={
                "conversation_id": conversation["conversation_id"],
                "participants": sorted(conversation["participants"]),
            },
        ),
    )


async def handle_private_chat(websocket, proto: dict):
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
        await send_error(websocket, "private_chat 报文缺少合法 text", msg_id=msg_id)
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
        logger.exception("获取私聊会话异常：cid=%s", conversation_id)
        await send_error(websocket, "发送失败，请重试", msg_id=msg_id, code=500)
        return

    if conversation["type"] != "private":
        await send_error(websocket, "该会话不是私聊会话", msg_id=msg_id, code=400)
        return

    if ctx.user_id not in conversation["participants"]:
        await send_error(websocket, "你不在该私聊会话中，无法发送消息", msg_id=msg_id, code=403)
        return

    try:
        target_user_id = await asyncio.to_thread(get_other_private_participant, conversation_id, ctx.user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("获取私聊对方异常：cid=%s user=%s", conversation_id, ctx.user_id)
        await send_error(websocket, "发送失败，请重试", msg_id=msg_id, code=500)
        return

    await deliver_private_message_locally(
        msg_id=msg_id,
        conversation_id=conversation_id,
        from_user_id=ctx.user_id,
        to_user_id=target_user_id,
        text=text.strip(),
    )

    try:
        await asyncio.to_thread(
            publish_distributed_message,
            {
                "source_node_id": NODE_ID,
                "msg_id": msg_id,
                "msg_type": "private_chat",
                "conversation_id": conversation_id,
                "from_user_id": ctx.user_id,
                "to_user_id": target_user_id,
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


async def handle_list_my_conversations(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证", msg_id=msg_id, code=401)
        return

    try:
        convs = await asyncio.to_thread(list_user_conversations, ctx.user_id)
    except Exception:
        logger.exception("列出用户会话失败：user=%s", ctx.user_id)
        await send_error(websocket, "获取会话列表失败，请重试", msg_id=msg_id, code=500)
        return

    await send_json(
        websocket,
        build_message(
            "my_conversations",
            msg_id=msg_id,
            code=200,
            content={"conversations": convs},
        ),
    )