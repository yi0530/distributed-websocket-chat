import json
import uuid
from time import time
from typing import Any

from websockets.exceptions import ConnectionClosed

from backend.utils.logger import logger


def build_message(
    msg_type: str,
    *,
    msg_id: str | None = None,
    code: int = 200,
    content: Any = None,
    err_msg: str = "",
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "msg_type": msg_type,
        "msg_id": msg_id or str(uuid.uuid4()),
        "code": code,
        "content": content,
        "err_msg": err_msg,
        "timestamp": int(time()),
    }


async def send_json(websocket, payload: dict[str, Any]) -> bool:
    try:
        await websocket.send(json.dumps(payload, ensure_ascii=False))
        return True
    except ConnectionClosed:
        logger.info("发送消息失败：连接已关闭")
        return False
    except Exception:
        logger.exception("发送消息失败")
        return False


async def send_error(websocket, err_msg: str, *, msg_id: str | None = None, code: int = 400):
    await send_json(
        websocket,
        build_message("error", msg_id=msg_id, code=code, err_msg=err_msg),
    )


async def send_ack(websocket, original_msg_id: str):
    await send_json(
        websocket,
        build_message("ack", msg_id=f"ack_{original_msg_id}"),
    )


def parse_protocol(raw_text: str) -> dict[str, Any] | None:
    try:
        proto = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(proto, dict):
        return None

    return proto


def validate_protocol(proto: dict[str, Any]) -> tuple[bool, str]:
    msg_type = proto.get("msg_type")
    msg_id = proto.get("msg_id")

    # ====================== 公共字段校验 ======================
    if not isinstance(msg_type, str) or not msg_type:
        return False, "缺少合法 msg_type"

    if not isinstance(msg_id, str) or not msg_id:
        return False, "缺少合法 msg_id"

    # ====================== 登录 ======================
    if msg_type == "login":
        username = proto.get("from")
        password = proto.get("content")

        if not isinstance(username, str) or not username.strip():
            return False, "login 报文缺少合法 from"

        if not isinstance(password, str) or not password.strip():
            return False, "login 报文缺少合法 content"

    # ====================== 心跳 ======================
    elif msg_type == "heartbeat":
        need_ack = proto.get("need_ack")
        if need_ack is not None and not isinstance(need_ack, bool):
            return False, "heartbeat 报文的 need_ack 必须为布尔值"

    # ====================== 在线用户列表 ======================
    elif msg_type == "get_online_users":
        pass

    # ====================== 创建群聊会话 ======================
    elif msg_type == "create_room":
        name = proto.get("name")
        if not isinstance(name, str) or not name.strip():
            return False, "create_room 报文缺少合法 name"

    # ====================== 会话相关（基于 conversation_id） ======================
    elif msg_type in {"join_room", "leave_room", "get_room_members"}:
        conversation_id = proto.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return False, f"{msg_type} 报文缺少合法 conversation_id"

    # ====================== 会话文本消息 ======================
    elif msg_type == "room_chat":
        conversation_id = proto.get("conversation_id")
        payload = proto.get("payload")

        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return False, "room_chat 报文缺少合法 conversation_id"

        if not isinstance(payload, dict):
            return False, "room_chat 报文缺少合法 payload"

        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return False, "room_chat 报文缺少合法 text"

    # ====================== 创建私聊房间 ======================
    elif msg_type == "create_private_conversation":
        target_user_id = proto.get("target_user_id")
        if not isinstance(target_user_id, str) or not target_user_id.strip():
            return False, "create_private_conversation 报文缺少合法 target_user_id"

    # ====================== 私聊消息 ======================
    elif msg_type == "private_chat":
        conversation_id = proto.get("conversation_id")
        payload = proto.get("payload")

        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return False, "private_chat 报文缺少合法 conversation_id"

        if not isinstance(payload, dict):
            return False, "private_chat 报文缺少合法 payload"

        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return False, "private_chat 报文缺少合法 text"

    else:
        return False, f"不支持的 msg_type: {msg_type}"



    return True, ""