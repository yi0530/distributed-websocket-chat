import asyncio

from backend.core.state import connections
from backend.core.offline_message_service import get_offline_messages, clear_offline_messages
from backend.core.protocol import build_message, send_json
from backend.utils.logger import logger


async def deliver_offline_messages(websocket):
    ctx = connections[websocket]
    if not ctx.is_authenticated or not ctx.user_id:
        return

    try:
        messages = await asyncio.to_thread(get_offline_messages, ctx.user_id)
    except Exception:
        logger.exception("获取离线消息失败，跳过离线补发：user=%s", ctx.user_id)
        return

    if not messages:
        return

    for msg in messages:
        msg_type = msg.get("msg_type")
        conversation_id = msg.get("conversation_id")
        from_user_id = msg.get("from_user_id")
        payload = msg.get("payload", {})
        text = payload.get("text", "")

        if msg_type == "room_chat":
            response = build_message(
                "room_chat",
                msg_id=msg.get("msg_id"),
                code=200,
                content={
                    "conversation_id": conversation_id,
                    "from_user_id": from_user_id,
                    "text": text,
                },
            )
            await send_json(websocket, response)

        elif msg_type == "private_chat":
            response = build_message(
                "private_chat",
                msg_id=msg.get("msg_id"),
                code=200,
                content={
                    "conversation_id": conversation_id,
                    "from_user_id": from_user_id,
                    "to_user_id": ctx.user_id,
                    "text": text,
                },
            )
            await send_json(websocket, response)

    try:
        await asyncio.to_thread(clear_offline_messages, ctx.user_id)
    except Exception:
        logger.exception("清理离线消息失败：user=%s", ctx.user_id)
