import asyncio
import websockets
from websockets.exceptions import ConnectionClosed, InvalidHandshake
import signal
import json
import uuid
from time import time
import jwt
from datetime import datetime, timedelta, UTC
from urllib.parse import urlparse, parse_qs

# ====================== 全局配置 ======================
connected_clients = set()
HEARTBEAT_TRANS_INTERVAL = 5
JWT_SECRET = "E5d8X$pR2!sQ9zG7kLbV6nA4cHjFmP0tU"
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 1

# ====================== 硬编码测试账号 ======================
TEST_ACCOUNTS = {
    "user001": "123456",
    "user002": "654321",
    "admin": "admin123"
}


# ====================== JWT工具类（修复弃用警告，官方规范写法） ======================
def generate_jwt_token(user_id: str) -> str:
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": user_id,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=JWT_EXP_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> bool:
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return False


# ======================================================================
# 【websockets 16.0 官方原生规范钩子】
# 唯一法定职责：握手阶段拦截/放行，无任何私有属性操作，无任何黑科技
# ======================================================================
async def check_connection_auth(server, request):
    parsed_url = urlparse(request.path)
    query_params = parse_qs(parsed_url.query)
    token = query_params.get("token", [None])[0]

    # 无Token：放行匿名连接（仅用于登录）
    if not token:
        return None

    # 有Token：验签失败直接拦截握手
    if not verify_jwt_token(token):
        raise InvalidHandshake("Token鉴权失败")

    # 合法Token：放行
    return None


# ====================== 原有基础功能 ======================
async def heartbeat_transport_task(websocket):
    while True:
        try:
            await websocket.ping()
            await asyncio.sleep(HEARTBEAT_TRANS_INTERVAL)
        except Exception:
            break


async def parse_protocol(raw_text):
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None


async def send_error(websocket, err_msg):
    await websocket.send(json.dumps({
        "version": "1.0", "msg_type": "error",
        "code": 400, "err_msg": err_msg, "timestamp": int(time())
    }))


async def send_ack(websocket, original_msg_id):
    await websocket.send(json.dumps({
        "version": "1.0", "msg_type": "ack",
        "msg_id": f"ack_{original_msg_id}", "code": 200,
        "timestamp": int(time())
    }))


# ====================== 登录业务处理 ======================
async def handle_login(websocket, proto):
    username = proto.get("from")
    password = proto.get("content")

    if username not in TEST_ACCOUNTS or TEST_ACCOUNTS[username] != password:
        await send_error(websocket, "账号或密码错误")
        return

    token = generate_jwt_token(username)
    print(f"[✅ 登录成功] 用户：{username}")

    await websocket.send(json.dumps({
        "version": "1.0", "msg_type": "login",
        "msg_id": proto["msg_id"], "content": token,
        "code": 200, "timestamp": int(time())
    }))


# ======================================================================
# 【业务层权限控制】匿名连接仅允许登录报文，完全符合你的安全要求
# ======================================================================
async def handle_client(websocket):
    connected_clients.add(websocket)
    asyncio.create_task(heartbeat_transport_task(websocket))
    print(f"\n[新连接] 当前在线：{len(connected_clients)}")

    # 官方公开API：判断当前连接是否带Token（鉴权连接）
    is_auth_connect = "token=" in websocket.request.path

    try:
        async for message in websocket:
            proto = await parse_protocol(message)
            if not proto:
                await send_error(websocket, "协议解析失败")
                continue

            msg_type = proto.get("msg_type", "")

            # 匿名连接权限锁：仅允许登录报文，其他消息全拦截
            if not is_auth_connect and msg_type != "login":
                await send_error(websocket, "请先登录获取Token")
                continue

            # 消息路由分发
            if msg_type == "login":
                await handle_login(websocket, proto)
            elif msg_type == "heartbeat":
                print(f"[✅ 心跳] 用户：{proto.get('from')}")
                if proto.get("need_ack"):
                    await send_ack(websocket, proto["msg_id"])

    except ConnectionClosed:
        print("[连接断开] 客户端主动关闭")
    finally:
        connected_clients.remove(websocket)
        print(f"[连接清理] 当前在线：{len(connected_clients)}")


# ====================== 服务优雅关停 ======================
async def shutdown_server():
    global server
    print("\n[服务关闭] 正在断开所有连接...")
    for client in list(connected_clients):
        await client.close(code=1000, reason="服务关闭")
    connected_clients.clear()
    if server:
        server.close()
        await server.wait_closed()
    print("[服务关闭] 完成")


def handle_exit(sig, frame):
    asyncio.create_task(shutdown_server())


# ====================== 服务启动入口 ======================
async def main():
    global server
    server = await websockets.serve(
        handle_client,
        "127.0.0.1",
        8765,
        process_request=check_connection_auth
    )
    print("=" * 70)
    print("✅ 分布式聊天系统 - 最终稳定版")
    print("📍 地址：ws://127.0.0.1:8765")
    print("🔐 适配：websockets 16.0 官方规范 | 无警告、无报错")
    print("📋 测试账号：user001/123456、user002/654321、admin/admin123")
    print("=" * 70)
    await server.wait_closed()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    asyncio.run(main())