from time import time

from backend.config import TOKEN_REFRESH_WINDOW_SECONDS
from backend.core.auth import decode_jwt_token, generate_jwt_token, get_token_exp_ts
from backend.core.protocol import build_message, send_error, send_json
from backend.core.state import connections


async def handle_refresh_token(websocket, proto: dict):
    msg_id = proto.get("msg_id")
    ctx = connections[websocket]

    if not ctx.is_authenticated or not ctx.user_id:
        await send_error(websocket, "当前连接未认证，无法续约 token", msg_id=msg_id, code=401)
        return

    if ctx.token_exp is None:
        await send_error(websocket, "当前连接缺少 token 过期时间信息", msg_id=msg_id, code=400)
        return

    now_ts = int(time())
    remaining = ctx.token_exp - now_ts

    if remaining <= 0:
        await send_error(websocket, "当前 token 已过期，请重新登录", msg_id=msg_id, code=401)
        return

    if remaining > TOKEN_REFRESH_WINDOW_SECONDS:
        await send_error(
            websocket,
            f"当前 token 距离过期还有 {remaining} 秒，暂不允许续约",
            msg_id=msg_id,
            code=400,
        )
        return

    new_token = generate_jwt_token(ctx.user_id)
    payload = decode_jwt_token(new_token) or {}
    new_exp = get_token_exp_ts(payload)

    ctx.token_exp = new_exp

    await send_json(
        websocket,
        build_message(
            "token_refreshed",
            msg_id=msg_id,
            code=200,
            content={
                "token": new_token,
                "expires_at": new_exp,
            },
        ),
    )