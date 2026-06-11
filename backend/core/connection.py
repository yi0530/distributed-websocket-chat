import asyncio
import signal
from time import time
from urllib.parse import parse_qs, urlparse

from websockets.exceptions import ConnectionClosed, InvalidHandshake

from backend.core.auth import decode_jwt_token, get_token_exp_ts, verify_jwt_token
from backend.core.state import ConnectionContext, connections
import backend.core.state as state_module
from backend.handlers.heartbeat import handle_heartbeat
from backend.handlers.login import handle_login
from backend.handlers.register import handle_register
from backend.utils.logger import logger
from backend.config import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT
from backend.handlers.user_list import handle_get_online_users
from backend.handlers.room import (
    handle_create_room,
    handle_get_chat_history,
    handle_get_room_members,
    handle_join_room,
    handle_leave_room,
    handle_list_rooms,
    handle_read_receipt,
    handle_room_chat,
    handle_typing_start,
    handle_typing_stop,
)
from backend.handlers.private_chat import (
    handle_create_private_conversation,
    handle_list_my_conversations,
    handle_private_chat,
)
from backend.core.offline_delivery_service import deliver_offline_messages
from backend.core.protocol import parse_protocol, send_error, send_json, validate_protocol
from backend.handlers.token import handle_refresh_token
from backend.config import NODE_ID
from backend.core.online_presence_service import start_online_presence, stop_online_presence


def extract_token_from_path(path: str) -> str | None:
    parsed = urlparse(path)
    query_params = parse_qs(parsed.query)
    return query_params.get("token", [None])[0]


async def bind_context_from_token(websocket, token: str | None):
    ctx = connections[websocket]
    if not token:
        return

    payload = decode_jwt_token(token)
    if not payload:
        return

    ctx.user_id = payload["sub"]
    ctx.is_authenticated = True
    ctx.token_exp = get_token_exp_ts(payload)

    asyncio.create_task(start_online_presence(websocket))

async def check_connection_auth(server_obj, request):
    token = extract_token_from_path(request.path)

    # 匿名连接放行：仅用于 login
    if not token:
        return None

    # 携带 token 但无效：握手阶段拒绝
    if not verify_jwt_token(token):
        raise InvalidHandshake("Token 鉴权失败")

    return None


async def heartbeat_transport_task(websocket):
    ctx = connections[websocket]

    while True:
        try:
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=HEARTBEAT_TIMEOUT)
            ctx.last_pong = int(time())
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except asyncio.TimeoutError:
            logger.warning("传输层心跳超时，主动关闭连接：user=%s", ctx.user_id or "anonymous")
            await websocket.close(code=1001, reason="heartbeat timeout")
            break
        except ConnectionClosed:
            break
        except Exception:
            logger.exception("传输层心跳任务异常")
            break


async def dispatch_message(websocket, proto: dict):
    msg_type = proto.get("msg_type")
    msg_id = proto.get("msg_id")
    ctx = connections[websocket]

    if not isinstance(msg_type, str) or not msg_type:
        await send_error(websocket, "缺少合法 msg_type", msg_id=msg_id)
        return

    # 未认证连接：仅允许 login / register
    if not ctx.is_authenticated and msg_type not in ("login", "register"):
        await send_error(websocket, "请先登录获取 Token", msg_id=msg_id, code=401)
        return

    if msg_type == "login":
        await handle_login(websocket, proto)
    elif msg_type == "register":
        await handle_register(websocket, proto)
    elif msg_type == "heartbeat":
        await handle_heartbeat(websocket, proto)
    elif msg_type == "get_online_users":
        await handle_get_online_users(websocket, proto)
    elif msg_type == "create_room":
        await handle_create_room(websocket, proto)
    elif msg_type == "join_room":
        await handle_join_room(websocket, proto)
    elif msg_type == "leave_room":
        await handle_leave_room(websocket, proto)
    elif msg_type == "get_room_members":
        await handle_get_room_members(websocket, proto)
    elif msg_type == "list_rooms":
        await handle_list_rooms(websocket, proto)
    elif msg_type == "get_chat_history":
        await handle_get_chat_history(websocket, proto)
    elif msg_type == "read_receipt":
        await handle_read_receipt(websocket, proto)
    elif msg_type == "typing_start":
        await handle_typing_start(websocket, proto)
    elif msg_type == "typing_stop":
        await handle_typing_stop(websocket, proto)
    elif msg_type == "room_chat":
        await handle_room_chat(websocket, proto)
    elif msg_type == "create_private_conversation":
        await handle_create_private_conversation(websocket, proto)
    elif msg_type == "list_my_conversations":
        await handle_list_my_conversations(websocket, proto)
    elif msg_type == "private_chat":
        await handle_private_chat(websocket, proto)
    elif msg_type == "refresh_token":
        await handle_refresh_token(websocket, proto)
    else:
        await send_error(websocket, f"暂不支持的 msg_type: {msg_type}", msg_id=msg_id, code=405)


async def handle_client(websocket):
    ctx = ConnectionContext(websocket=websocket)
    connections[websocket] = ctx

    request_path = getattr(getattr(websocket, "request", None), "path", "") or ""
    token = extract_token_from_path(request_path)
    await bind_context_from_token(websocket, token)

    ctx.heartbeat_task = asyncio.create_task(heartbeat_transport_task(websocket))

    await deliver_offline_messages(websocket)

    logger.info(
        "新连接：online=%s auth=%s user=%s",
        len(connections),
        ctx.is_authenticated,
        ctx.user_id or "anonymous",
    )

    try:
        async for raw_message in websocket:
            proto = parse_protocol(raw_message)
            if proto is None:
                await send_error(websocket, "协议解析失败")
                continue

            ok, err_msg = validate_protocol(proto)
            if not ok:
                await send_error(websocket, err_msg, msg_id=proto.get("msg_id"))
                continue

            try:
                await dispatch_message(websocket, proto)
            except Exception:
                logger.exception(
                    "业务消息处理异常：msg_type=%s msg_id=%s",
                    proto.get("msg_type"), proto.get("msg_id"),
                )
                try:
                    await send_error(
                        websocket,
                        "服务端内部错误，请查看后端日志",
                        msg_id=proto.get("msg_id"),
                        code=500,
                    )
                except Exception:
                    pass
    except ConnectionClosed:
        logger.info("连接断开：user=%s", ctx.user_id or "anonymous")
    except Exception:
        logger.exception("连接处理出现未预期异常")
    finally:
        ctx = connections.get(websocket)

        if ctx and ctx.heartbeat_task is not None:
            ctx.heartbeat_task.cancel()
            try:
                await ctx.heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("清理心跳任务失败")

        await stop_online_presence(websocket)

        connections.pop(websocket, None)

        logger.info("连接清理完成：online=%s", len(connections))


async def shutdown_server():
    logger.info("服务关闭中：准备断开所有连接")

    for websocket, ctx in list(connections.items()):
        try:
            await websocket.close(code=1000, reason="服务关闭")
        except Exception:
            logger.exception("关闭连接失败：user=%s", ctx.user_id or "anonymous")

    connections.clear()

    if state_module.server is not None:
        state_module.server.close()
        await state_module.server.wait_closed()

    logger.info("服务关闭完成")


def handle_exit(sig, frame):
    logger.info("收到退出信号：%s", sig)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(shutdown_server())
    except RuntimeError:
        logger.warning("事件循环未运行，无法异步关闭服务")
