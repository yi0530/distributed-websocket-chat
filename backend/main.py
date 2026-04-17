import asyncio
import websockets
from websockets import frames
from websockets.exceptions import ConnectionClosed

# 仅用于帧解析测试，无业务逻辑
connected_clients = set()
# 心跳间隔5秒（作业要求，基于原生Ping帧实现）
HEARTBEAT_INTERVAL = 5

# 心跳任务：服务端主动发Ping帧，检测客户端存活
async def heartbeat_task(websocket):
    while True:
        try:
            # 发送原生Ping控制帧（非业务字符串，纯帧操作）
            await websocket.ping()
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except ConnectionClosed:
            break

# 核心：完整帧解析处理函数
async def handle_frame(websocket):
    # 新增客户端连接
    connected_clients.add(websocket)
    print(f"[连接] 新客户端接入，当前在线：{len(connected_clients)}")

    # 启动心跳检测任务
    asyncio.create_task(heartbeat_task(websocket))

    try:
        # 持续接收完整WebSocket帧
        while True:
            # 接收一整帧（TCP已拼包，无半包/粘包）
            frame = await websocket.recv_frame()

            # 提取帧核心字段（仅解析必要字段，符合作业要求）
            fin = frame.fin
            opcode = frame.opcode
            payload = frame.data

            # ==========================================
            # 完整帧类型解析（老师要求的全部帧类型）
            # ==========================================

            # 1. 文本帧解析
            if opcode == frames.OP_TEXT:
                print(f"[文本帧] FIN={fin} | 内容：{payload.decode('utf-8')}")

            # 2. 二进制帧解析
            elif opcode == frames.OP_BINARY:
                print(f"[二进制帧] FIN={fin} | 数据长度：{len(payload)} 字节")

            # 3. 关闭帧解析
            elif opcode == frames.OP_CLOSE:
                print("[关闭帧] 客户端发起断开请求")
                break

            # 4. Ping帧解析（原生心跳请求）
            elif opcode == frames.OP_PING:
                print("[Ping帧] 收到客户端心跳，自动回复Pong帧")
                await websocket.pong(payload)

            # 5. Pong帧解析（原生心跳响应）
            elif opcode == frames.OP_PONG:
                print("[Pong帧] 客户端心跳正常，连接存活")

            # 6. 分片帧（Opcode=0，仅打印日志，库已自动拼接）
            elif opcode == frames.OP_CONT:
                print(f"[分片帧] 收到续传分片，长度：{len(payload)} 字节")

    except ConnectionClosed:
        print("[异常] 客户端意外断开连接")
    finally:
        # 移除连接
        connected_clients.remove(websocket)
        print(f"[断开] 客户端退出，当前在线：{len(connected_clients)}")

# 启动纯帧解析服务器
async def start_frame_server():
    async with websockets.serve(handle_frame, "127.0.0.1", 8765):
        print("========================================")
        print("  WebSocket完整帧解析服务已启动")
        print("  地址：ws://127.0.0.1:8765")
        print("  仅处理：文本/二进制/关闭/Ping/Pong/分片帧")
        print("========================================")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(start_frame_server())