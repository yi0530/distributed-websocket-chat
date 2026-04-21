from backend.core.protocol import build_message, send_error, send_json
from backend.core.conversation_service import (
    create_or_get_private_conversation,
    get_conversation,
    get_other_private_participant,
)
from backend.core.state import connections


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

    if not is_user_online(target_user_id):
        await send_error(websocket, "对方当前不在线，暂不支持离线私聊消息", msg_id=msg_id, code=404)
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

    # 先发给发送者自己
    await send_json(websocket, response)

    # 再发给对方在线连接
    target_websockets = get_online_websockets_by_user_id(target_user_id)
    for target_ws in target_websockets:
        await send_json(target_ws, response)


