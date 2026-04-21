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

    if not isinstance(msg_type, str) or not msg_type:
        return False, "缺少合法 msg_type"

    if not isinstance(msg_id, str) or not msg_id:
        return False, "缺少合法 msg_id"

    if msg_type == "login":
        username = proto.get("from")
        password = proto.get("content")

        if not isinstance(username, str) or not username:
            return False, "login 报文缺少合法 from"

        if not isinstance(password, str) or not password:
            return False, "login 报文缺少合法 content"

    elif msg_type == "heartbeat":
        need_ack = proto.get("need_ack")
        if need_ack is not None and not isinstance(need_ack, bool):
            return False, "heartbeat 报文的 need_ack 必须为布尔值"

    return True, ""