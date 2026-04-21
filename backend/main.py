import asyncio
import json
import logging
import os
import signal
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import websockets
from websockets.exceptions import ConnectionClosed, InvalidHandshake

# ====================== 日志配置 ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ====================== 配置区 ======================
HOST = "127.0.0.1"
PORT = 8765
HEARTBEAT_INTERVAL = 5
HEARTBEAT_TIMEOUT = 5
JWT_SECRET = os.getenv("JWT_SECRET", "dev_only_change_me")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 1

# 学习阶段先保留硬编码账号；后续再替换为数据库
TEST_ACCOUNTS = {
    "user001": "123456",
    "user002": "654321",
    "admin": "admin123",
}

server = None


# ====================== 运行时状态 ======================
@dataclass
class ConnectionContext:
    websocket: Any
    user_id: str | None = None
    is_authenticated: bool = False
    connected_at: int = field(default_factory=lambda: int(time()))
    last_pong: int = field(default_factory=lambda: int(time()))
    heartbeat_task: asyncio.Task | None = None


connections: dict[Any, ConnectionContext] = {}


# ====================== JWT 工具 ======================
def generate_jwt_token(user_id: str) -> str:
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": user_id,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            return None
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def verify_jwt_token(token: str) -> bool:
    return decode_jwt_token(token) is not None


# ====================== 协议工具 ======================
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


# ====================== 连接辅助 ======================
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


# ====================== 握手鉴权 ======================
async def check_connection_auth(server_obj, request):
    token = extract_token_from_path(request.path)

    # 匿名连接放行：仅用于 login
    if not token:
        return None

    # 携带 token 但无效：握手阶段拒绝
    if not verify_jwt_token(token):
        raise InvalidHandshake("Token 鉴权失败")

    return None


# ====================== 核心业务 ======================
async def handle_login(websocket, proto: dict[str, Any]):
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

    if TEST_ACCOUNTS.get(username) != password:
        await send_error(websocket, "账号或密码错误", msg_id=msg_id, code=401)
        return

    token = generate_jwt_token(username)
    logger.info("登录成功：user=%s", username)

    await send_json(
        websocket,
        build_message("login", msg_id=msg_id, code=200, content=token),
    )


async def handle_heartbeat(websocket, proto: dict[str, Any]):
    msg_id = proto.get("msg_id")
    ctx = connections[websocket]

    logger.info("收到业务心跳：user=%s", ctx.user_id or proto.get("from") or "unknown")

    if proto.get("need_ack"):
        if not isinstance(msg_id, str) or not msg_id:
            await send_error(websocket, "heartbeat 报文缺少合法 msg_id")
            return
        await send_ack(websocket, msg_id)


# ====================== 心跳任务 ======================
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


# ====================== 消息分发 ======================
async def dispatch_message(websocket, proto: dict[str, Any]):
    msg_type = proto.get("msg_type")
    msg_id = proto.get("msg_id")
    ctx = connections[websocket]

    if not isinstance(msg_type, str) or not msg_type:
        await send_error(websocket, "缺少合法 msg_type", msg_id=msg_id)
        return

    # 未认证连接：仅允许 login
    if not ctx.is_authenticated and msg_type != "login":
        await send_error(websocket, "请先登录获取 Token", msg_id=msg_id, code=401)
        return

    if msg_type == "login":
        await handle_login(websocket, proto)
    elif msg_type == "heartbeat":
        await handle_heartbeat(websocket, proto)
    else:
        await send_error(websocket, f"暂不支持的 msg_type: {msg_type}", msg_id=msg_id, code=405)


# ====================== 主连接处理器 ======================
async def handle_client(websocket):
    ctx = ConnectionContext(websocket=websocket)
    connections[websocket] = ctx

    request_path = getattr(getattr(websocket, "request", None), "path", "") or ""
    token = extract_token_from_path(request_path)
    await bind_context_from_token(websocket, token)

    ctx.heartbeat_task = asyncio.create_task(heartbeat_transport_task(websocket))

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

            await dispatch_message(websocket, proto)
    except ConnectionClosed:
        logger.info("连接断开：user=%s", ctx.user_id or "anonymous")
    except Exception:
        logger.exception("连接处理出现未预期异常")
    finally:
        if ctx.heartbeat_task is not None:
            ctx.heartbeat_task.cancel()
            try:
                await ctx.heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("清理心跳任务失败")

        connections.pop(websocket, None)
        logger.info("连接清理完成：online=%s", len(connections))


# ====================== 服务关停 ======================
async def shutdown_server():
    global server

    logger.info("服务关闭中：准备断开所有连接")

    for websocket, ctx in list(connections.items()):
        try:
            await websocket.close(code=1000, reason="服务关闭")
        except Exception:
            logger.exception("关闭连接失败：user=%s", ctx.user_id or "anonymous")

    connections.clear()

    if server is not None:
        server.close()
        await server.wait_closed()

    logger.info("服务关闭完成")


def handle_exit(sig, frame):
    logger.info("收到退出信号：%s", sig)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(shutdown_server())
    except RuntimeError:
        logger.warning("事件循环未运行，无法异步关闭服务")


# ====================== 启动入口 ======================
async def main():
    global server

    if JWT_SECRET == "dev_only_change_me":
        logger.warning("当前 JWT_SECRET 使用开发默认值，部署前请改为环境变量")

    server = await websockets.serve(
        handle_client,
        HOST,
        PORT,
        process_request=check_connection_auth,
    )

    logger.info("=" * 60)
    logger.info("WebSocket 聊天服务基线版已启动")
    logger.info("地址：ws://%s:%s", HOST, PORT)
    logger.info("测试账号：user001/123456、user002/654321、admin/admin123")
    logger.info("=" * 60)

    await server.wait_closed()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    asyncio.run(main())
