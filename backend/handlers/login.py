from backend.config import TEST_ACCOUNTS
from backend.core.auth import decode_jwt_token, generate_jwt_token, get_token_exp_ts
from backend.core.protocol import build_message, send_error, send_json
from backend.utils.logger import logger
from backend.core.offline_delivery_service import deliver_offline_messages
from backend.core.online_presence_service import start_online_presence
from backend.core.state import connections


async def handle_login(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    username = proto.get("from")
    password = proto.get("content")

    if not isinstance(msg_id, str) or not msg_id:
        await send_error(websocket, "login 报文缺少合法 msg_id")
        return

    if not isinstance(username, str) or not username:
        await send_error(websocket, "login 报文缺少合法用户名", msg_id=msg_id)
        return

    if not isinstance(password, str) or not password:
        await send_error(websocket, "login 报文缺少合法密码", msg_id=msg_id)
        return

    ctx = connections[websocket]
    if ctx.is_authenticated and ctx.user_id:
        await send_error(
            websocket,
            "当前连接已登录，请先断开连接后再切换账号",
            msg_id=msg_id,
            code=409,
        )
        return

    if TEST_ACCOUNTS.get(username) != password:
        await send_error(websocket, "账号或密码错误", msg_id=msg_id, code=401)
        return

    token = generate_jwt_token(username)
    payload = decode_jwt_token(token) or {}
    expires_at = get_token_exp_ts(payload)

    ctx.user_id = username
    ctx.is_authenticated = True
    ctx.token_exp = expires_at

    start_online_presence(websocket)

    logger.info("登录成功：user=%s", username)

    await send_json(
        websocket,
        build_message(
            "login",
            msg_id=msg_id,
            code=200,
            content={
                "token": token,
                "expires_at": expires_at,
            },
        ),
    )

    await deliver_offline_messages(websocket)