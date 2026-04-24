from time import time

from backend.core.protocol import build_message, send_error, send_json, send_ack
from backend.core.conversation_service import (
    create_or_get_private_conversation,
    get_conversation,
    get_other_private_participant,
)
from backend.core.state import connections,processed_message_keys
from backend.core.offline_message_service import store_offline_message


def is_user_online(user_id: str) -> bool:
    for ctx in connections.values():
        if ctx.is_authenticated and ctx.user_id == user_id:
            return True
    return False


async def handle_create_private_conversation(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    target_user_id = proto.get("target_user_id")
    ctx = connections[websocket]

    if not isinstance(target_user_id, str) or not target_user_id.strip():
        await send_error(websocket, "create_private_conversation 报文缺少合法 target_user_id", msg_id=msg_id)
        return

    if not is_user_online(target_user_id):
        await send_error(websocket, "目标用户当前不在线，暂时无法创建私聊会话", msg_id=msg_id, code=404)
        return

    try:
        conversation = create_or_get_private_conversation(
            owner_id=ctx.user_id,
            target_user_id=target_user_id,
        )
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    await send_json(
        websocket,
        build_message(
            "private_conversation_created",
            msg_id=msg_id,
            code=200,
            content={
                "conversation_id": conversation["conversation_id"],
                "type": conversation["type"],
                "participants": sorted(conversation["participants"]),
                "owner": conversation["owner"],
            },
        ),
    )


def get_online_websockets_by_user_id(user_id: str) -> list:
    result = []
    for websocket, ctx in connections.items():
        if ctx.is_authenticated and ctx.user_id == user_id:
            result.append(websocket)
    return result


async def handle_private_chat(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    conversation_id = proto.get("conversation_id")
    payload = proto.get("payload")
    ctx = connections[websocket]

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        await send_error(websocket, "private_chat 报文缺少合法 text", msg_id=msg_id)
        return

    dedupe_key = f"{ctx.user_id}:{msg_id}"
    need_ack = bool(proto.get("need_ack"))

    # 重复消息：不重复转发，但可再次回 ACK
    if dedupe_key in processed_message_keys:
        if need_ack:
            await send_ack(websocket, msg_id, status="duplicate")
        return

    try:
        conversation = get_conversation(conversation_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    if conversation["type"] != "private":
        await send_error(websocket, "该会话不是私聊会话", msg_id=msg_id, code=400)
        return

    if ctx.user_id not in conversation["participants"]:
        await send_error(websocket, "你不在该私聊会话中，无法发送消息", msg_id=msg_id, code=403)
        return

    try:
        target_user_id = get_other_private_participant(conversation_id, ctx.user_id)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return

    response = build_message(
        "private_chat",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "from_user_id": ctx.user_id,
            "to_user_id": target_user_id,
            "text": text.strip(),
        },
    )

    # 发给发送者自己
    await send_json(websocket, response)

    # 发给对方：在线就发，不在线就存离线
    target_websockets = get_online_websockets_by_user_id(target_user_id)
    if target_websockets:
        for target_ws in target_websockets:
            await send_json(target_ws, response)
    else:
        store_offline_message(
            target_user_id,
            {
                "msg_id": msg_id,
                "conversation_id": conversation_id,
                "from_user_id": ctx.user_id,
                "msg_type": "private_chat",
                "payload": {
                    "text": text.strip(),
                },
                "timestamp": int(time()),
            },
        )

    response = build_message(
        "private_chat",
        msg_id=msg_id,
        code=200,
        content={
            "conversation_id": conversation_id,
            "from_user_id": ctx.user_id,
            "to_user_id": target_user_id,
            "text": text.strip(),
        },
    )

    await send_json(websocket, response)

    target_websockets = get_online_websockets_by_user_id(target_user_id)
    for target_ws in target_websockets:
        await send_json(target_ws, response)

    processed_message_keys[dedupe_key] = int(time())

    if need_ack:
        await send_ack(websocket, msg_id, status="processed")

