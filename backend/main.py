import asyncio
import websockets
from websockets.exceptions import ConnectionClosed
import signal
import json
from time import time

# 全局配置（全部不变）
connected_clients = set()
HEARTBEAT_TRANS_INTERVAL = 5   # 底层传输层Ping心跳间隔（原有）
HEARTBEAT_APP_TIMEOUT = 30     # 应用层心跳超时阈值（新增：30s不上报视为业务离线）
server = None

# ====================== 原有【传输层Ping/Pong心跳】完全不动 ======================
async def heartbeat_transport_task(websocket):
    while True:
        try:
            await websocket.ping()
            await asyncio.sleep(HEARTBEAT_TRANS_INTERVAL)
        except Exception:
            break

# ====================== 协议解析（原有完整版，不动） ======================
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

# ====================== 原有错误包、ACK回执 全部不动 ======================
async def send_error(websocket, err_msg):
    error_pkg = {
        "version": "1.0", "msg_id": "error", "msg_type": "error",
        "target_type": "user", "from": "server", "to": "client",
        "content": "", "status": 0, "timestamp": int(time()),
        "need_ack": 0, "code": 400, "err_msg": err_msg,
        "expire": 0, "node_id": "local", "seq": 0, "total": 1
    }
    await websocket.send(json.dumps(error_pkg))

async def send_ack(websocket, original_msg_id):
    ack_pkg = {
        "version": "1.0",
        "msg_id": f"ack_{original_msg_id}",
        "msg_type": "ack",
        "target_type": "user",
        "from": "server",
        "to": "client",
        "content": f"消息 {original_msg_id} 已成功接收",
        "status": 1,
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
    print(f"[✅ ACK回执已发送] msg_id：{original_msg_id}")

# ====================== 【新增】应用层业务心跳接收处理 ======================
async def handle_app_heartbeat(proto):
    """处理客户端发来的业务心跳包"""
    print(f"[✅ 收到应用层业务心跳] 用户：{proto['from']} | 时间戳：{proto['timestamp']}")

# ====================== 主连接逻辑（仅新增心跳判断分支） ======================
async def handle_client(websocket):
    connected_clients.add(websocket)
    print(f"\n[连接成功] 客户端接入 | 当前在线：{len(connected_clients)}")
    asyncio.create_task(heartbeat_transport_task(websocket))

    try:
        async for message in websocket:
            # 二进制帧不变
            if isinstance(message, bytes):
                print(f"[二进制帧] 长度：{len(message)} 字节")
                continue

            print("\n===== 收到文本帧，解析自定义协议 =====")
            proto = await parse_protocol(message)

            if not proto:
                print("[协议错误] 非法JSON格式")
                await send_error(websocket, "协议解析失败：非标准JSON")
                continue

            print("[✅ 协议解析成功]")
            print(f"消息ID：{proto['msg_id']}")
            print(f"类型：{proto['msg_type']}")
            print(f"发送者：{proto['from']}")

            # 原有ACK逻辑不变
            if proto["need_ack"] == 1 and proto["msg_id"]:
                await send_ack(websocket, proto["msg_id"])

            # ====================== 新增：业务心跳分支 ======================
            if proto["msg_type"] == "heartbeat":
                await handle_app_heartbeat(proto)

    except ConnectionClosed:
        print("[状态] 客户端主动断开")
    except Exception as e:
        print(f"[连接异常] {e}")
    finally:
        connected_clients.remove(websocket)
        print(f"[连接清理] 客户端移除 | 当前在线：{len(connected_clients)}")

# ====================== 原有优雅关闭全程不动 ======================
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

# ====================== 服务启动 ======================
async def main():
    global server
    server = await websockets.serve(handle_client, "127.0.0.1", 8765)
    print("="*75)
    print("✅ 底层帧 + 完整协议 + ACK回执 + 应用层业务心跳 服务启动")
    print("📍 地址：ws://127.0.0.1:8765")
    print("🔹 传输层Ping心跳（已有） | 🔹 应用层业务心跳（本次新增）")
    print("🛡️  异常不断连 | ⌨️ Ctrl+C 关闭服务")
    print("="*75)
    await server.wait_closed()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass