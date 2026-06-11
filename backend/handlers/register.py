"""
handle_register — 用户注册 handler。

msg_type: register
未认证连接可以调用。
"""

from backend.core.protocol import build_message, send_error, send_json
from backend.core.user_store import create_user, user_exists
from backend.utils.logger import logger


async def handle_register(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    username = proto.get("from")
    content = proto.get("content") or {}
    password = content.get("password") if isinstance(content, dict) else None

    # ── 字段校验 ──
    if not isinstance(msg_id, str) or not msg_id:
        await send_error(websocket, "register 报文缺少合法 msg_id")
        return

    if not isinstance(username, str) or not username:
        await send_error(websocket, "register 报文缺少合法用户名", msg_id=msg_id)
        return

    if not isinstance(password, str) or not password:
        await send_error(websocket, "register 报文缺少合法密码", msg_id=msg_id)
        return

    # ── 重复检查（明确 code=409） ──
    if user_exists(username):
        await send_error(websocket, "用户名已存在", msg_id=msg_id, code=409)
        return

    # ── 创建用户 ──
    try:
        create_user(username, password)
    except ValueError as e:
        await send_error(websocket, str(e), msg_id=msg_id, code=400)
        return
    except Exception:
        logger.exception("用户注册异常：%s", username)
        await send_error(websocket, "服务端内部错误，注册失败", msg_id=msg_id, code=500)
        return

    logger.info("用户注册成功：%s", username)

    await send_json(
        websocket,
        build_message(
            "register",
            msg_id=msg_id,
            code=200,
            content={"username": username},
        ),
    )
