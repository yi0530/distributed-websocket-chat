import asyncio
from time import time

from websockets import State as WsState

from backend.config import NODE_ID
from backend.core.conversation_service import get_conversation
from backend.core.offline_message_service import store_offline_message
from backend.core.online_registry_service import get_user_online_node
from backend.core.protocol import build_message, send_json
from backend.core.state import connections
from backend.utils.logger import logger


def get_online_websockets_by_user_id(user_id: str) -> list:
    result = []
    for websocket, ctx in connections.items():
        if ctx.is_authenticated and ctx.user_id == user_id:
            if websocket.state != WsState.OPEN:
                continue
            if websocket.close_code is not None:
                continue
            result.append(websocket)
    return result


async def deliver_room_message_locally(
    *,
    msg_id: str,
    conversation_id: str,
    from_user_id: str,
    text: str,
) -> None:
    conversation = get_conversation(conversation_id)
    participants = conversation["participants"]

    response = build_message(
        "room_chat",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "from_user_id": from_user_id,
            "text": text,
        },
    )

    for user_id in participants:
        target_websockets = get_online_websockets_by_user_id(user_id)

        if target_websockets:
            for target_ws in target_websockets:
                await send_json(target_ws, response)
            continue

        if user_id == from_user_id:
            continue

        try:
            online_node = await asyncio.to_thread(get_user_online_node, user_id)
        except Exception:
            logger.exception("查询用户在线节点失败，按离线处理：user=%s", user_id)
            online_node = None
        if online_node and online_node != NODE_ID:
            continue

        try:
            await asyncio.to_thread(
                store_offline_message,
                user_id,
                {
                    "msg_id": msg_id,
                    "conversation_id": conversation_id,
                    "from_user_id": from_user_id,
                    "msg_type": "room_chat",
                    "payload": {
                        "text": text,
                    },
                    "timestamp": int(time()),
                },
            )
        except Exception:
            logger.exception("存储群聊离线消息失败：user=%s msg_id=%s", user_id, msg_id)


async def deliver_private_message_locally(
    *,
    msg_id: str,
    conversation_id: str,
    from_user_id: str,
    to_user_id: str,
    text: str,
) -> None:
    response = build_message(
        "private_chat",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "from_user_id": from_user_id,
            "to_user_id": to_user_id,
            "text": text,
        },
    )

    target_websockets = get_online_websockets_by_user_id(to_user_id)
    if target_websockets:
        for target_ws in target_websockets:
            await send_json(target_ws, response)
        return

    try:
        online_node = await asyncio.to_thread(get_user_online_node, to_user_id)
    except Exception:
        logger.exception("查询私聊目标在线节点失败，按离线处理：user=%s", to_user_id)
        online_node = None
    if online_node and online_node != NODE_ID:
        return

    try:
        await asyncio.to_thread(
            store_offline_message,
            to_user_id,
            {
                "msg_id": msg_id,
                "conversation_id": conversation_id,
                "from_user_id": from_user_id,
                "msg_type": "private_chat",
                "payload": {
                    "text": text,
                },
                "timestamp": int(time()),
            },
        )
    except Exception:
        logger.exception("存储私聊离线消息失败：user=%s msg_id=%s", to_user_id, msg_id)


async def deliver_room_message_online_only_locally(
    *,
    msg_id: str,
    conversation_id: str,
    from_user_id: str,
    text: str,
) -> None:
    conversation = get_conversation(conversation_id)
    participants = conversation["participants"]

    response = build_message(
        "room_chat",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "from_user_id": from_user_id,
            "text": text,
        },
    )

    for user_id in participants:
        target_websockets = get_online_websockets_by_user_id(user_id)
        for target_ws in target_websockets:
            await send_json(target_ws, response)


async def deliver_private_message_online_only_locally(
    *,
    msg_id: str,
    conversation_id: str,
    from_user_id: str,
    to_user_id: str,
    text: str,
) -> None:
    response = build_message(
        "private_chat",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "from_user_id": from_user_id,
            "to_user_id": to_user_id,
            "text": text,
        },
    )

    target_websockets = get_online_websockets_by_user_id(to_user_id)
    for target_ws in target_websockets:
        await send_json(target_ws, response)
