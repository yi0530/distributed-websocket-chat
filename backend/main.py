import asyncio
import websockets
from websockets.exceptions import ConnectionClosed
import signal
import json
from time import time

# 全局配置
connected_clients = set()
HEARTBEAT_INTERVAL = 5
server = None

# ====================== 心跳模块（不变） ======================
async def heartbeat_task(websocket):
    while True:
        try:
            await websocket.ping()
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except Exception:
            break

# ====================== 协议解析（不变） ======================
async def parse_protocol(raw_text):
    try:
        data = json.loads(raw_text)
        return {
            "version": data.get("version", "1.0"),
            "msg_id": data.get("msg_id", ""),
            "msg_type": data.get("msg_type", ""),
            "target_type": data.get("target_type", ""),
            "from": data.get("from", ""),
            "to": data.get("to", ""),
            "content": data.get("content", ""),
            "status": data.get("status", 0),
            "timestamp": data.get("timestamp", 0),
            "need_ack": data.get("need_ack", 0),
            "code": data.get("code", 0),
            "err_msg": data.get("err_msg", ""),
            "expire": data.get("expire", 0),
            "node_id": data.get("node_id", "local"),
            "seq": data.get("seq", 0),
            "total": data.get("total", 1)
        }
    except json.JSONDecodeError:
        return None

# ====================== 发送错误包（不变） ======================
async def send_error(websocket, err_msg):
    error_pkg = {
        "version": "1.0", "msg_id": "error", "msg_type": "error",
        "target_type": "user", "from": "server", "to": "client",
        "content": "", "status": 0, "timestamp": int(time()),
        "need_ack": 0, "code": 400, "err_msg": err_msg,
        "expire": 0, "node_id": "local", "seq": 0, "total": 1
    }
    await websocket.send(json.dumps(error_pkg))

# ====================== 【新增】发送 ACK 回执 ======================
async def send_ack(websocket, original_msg_id):
    ack_pkg = {
        "version": "1.0",
        "msg_id": f"ack_{original_msg_id}",  # 回执ID绑定原消息
        "msg_type": "ack",  # 标记这是ACK回执
        "target_type": "user",
        "from": "server",
        "to": "client",
        "content": f"消息 {original_msg_id} 已成功接收",
        "status": 1,  # 1=已送达
        "timestamp": int(time()),
        "need_ack": 0,
        "code": 200,
        "err_msg": "",
        "expire": 0,
        "node_id": "local",
        "seq": 0,
        "total": 1
    }
    await websocket.send(json.dumps(ack_pkg))
    print(f"[✅ ACK 回执已发送] 对消息：{original_msg_id} 完成签收")

# ====================== 连接处理（新增ACK判断） ======================
async def handle_client(websocket):
    connected_clients.add(websocket)
    print(f"\n[连接成功] 客户端接入 | 当前在线：{len(connected_clients)}")
    asyncio.create_task(heartbeat_task(websocket))

    try:
        async for message in websocket:
            # 二进制帧
            if isinstance(message, bytes):
                print(f"[二进制帧] 长度：{len(message)} 字节")
                continue

            # 协议解析
            print("\n===== 收到文本帧，解析自定义协议 =====")
            proto = await parse_protocol(message)

            if not proto:
                print("[协议错误] 非法JSON格式")
                await send_error(websocket, "协议解析失败：非标准JSON")
                continue

            # 解析成功打印
            print("[✅ 协议解析成功]")
            print(f"消息ID：{proto['msg_id']}")
            print(f"类型：{proto['msg_type']}")
            print(f"内容：{proto['content']}")
            print(f"需要ACK：{proto['need_ack']}")

            # ======================
            # 核心：需要ACK则自动回复回执
            # ======================
            if proto["need_ack"] == 1 and proto["msg_id"]:
                await send_ack(websocket, proto["msg_id"])

    except ConnectionClosed:
        print("[状态] 客户端主动断开")
    except Exception as e:
        print(f"[连接异常] {e}")
    finally:
        connected_clients.remove(websocket)
        print(f"[连接清理] 客户端移除 | 当前在线：{len(connected_clients)}")

# ====================== 优雅关闭（不变） ======================
async def shutdown_server():
    global server
    print("\n[手动关闭] 安全关闭服务器...")
    for client in list(connected_clients):
        await client.close(code=1000, reason="服务器关闭")
    connected_clients.clear()
    if server:
        server.close()
        await server.wait_closed()
    print("[已关闭] 服务退出成功")

def handle_exit(sig, frame):
    asyncio.create_task(shutdown_server())

# ====================== 启动 ======================
async def main():
    global server
    server = await websockets.serve(handle_client, "127.0.0.1", 8765)
    print("="*70)
    print("✅ WebSocket + 最终协议 + ACK 回执服务 启动成功")
    print("📍 地址：ws://127.0.0.1 8765")
    print("📌 功能：消息解析 + 自动ACK回执 + 错误返回 + 不断连")
    print("⌨️  Ctrl+C 关闭服务")
    print("="*70)
    await server.wait_closed()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass