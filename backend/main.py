import asyncio
import websockets
from websockets.exceptions import ConnectionClosed
import signal

# 全局配置
connected_clients = set()
HEARTBEAT_INTERVAL = 5
server = None


# --------------------------
# 心跳任务（独立异常，不影响主连接）
# --------------------------
async def heartbeat_task(websocket):
    while True:
        try:
            await websocket.ping()
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except Exception:
            break


# --------------------------
# 核心连接处理（异常完全隔离）
# --------------------------
async def handle_client(websocket):
    # 新增连接
    connected_clients.add(websocket)
    print(f"\n[连接成功] 客户端已接入 | 当前在线：{len(connected_clients)}")

    # 启动后台心跳
    asyncio.create_task(heartbeat_task(websocket))

    try:
        # 循环监听消息（长连接保持）
        async for message in websocket:
            # ====================
            # 所有解析错误 仅捕获，不断开连接！
            # ====================
            try:
                # 自动区分文本/二进制帧（新版库安全用法）
                if isinstance(message, str):
                    print(f"[文本帧] {message}")
                elif isinstance(message, bytes):
                    print(f"[二进制帧] 数据长度：{len(message)} 字节")

            # 单条消息解析错误 → 只打印，不中断连接
            except Exception as e:
                print(f"[消息解析失败] 错误：{str(e)}，连接保持不变")

    # ====================
    # 仅 连接真正断开 时执行
    # ====================
    except ConnectionClosed:
        print("[状态] 客户端主动断开连接")

    # 其他未知错误 → 打印日志，连接已由库自动处理
    except Exception as e:
        print(f"[连接异常] {str(e)}")

    # 最终清理（仅连接关闭后执行）
    finally:
        connected_clients.remove(websocket)
        print(f"[连接清理] 客户端已移除 | 当前在线：{len(connected_clients)}")


# --------------------------
# 优雅关闭服务器（Ctrl+C）
# --------------------------
async def shutdown_server():
    global server
    print("\n\n[手动关闭] 正在安全关闭服务器...")

    # 关闭所有客户端
    for client in list(connected_clients):
        await client.close(code=1000, reason="服务器手动关闭")
    connected_clients.clear()

    # 停止服务
    if server:
        server.close()
        await server.wait_closed()

    print("[已关闭] 服务器退出成功")
    asyncio.get_event_loop().stop()


# 信号处理
def handle_exit(sig, frame):
    asyncio.create_task(shutdown_server())


# --------------------------
# 启动服务
# --------------------------
async def main():
    global server
    server = await websockets.serve(
        handle_client,
        host="127.0.0.1",
        port=8765
    )
    print("=" * 65)
    print("✅ WebSocket 帧解析服务（稳定版）启动成功")
    print("📍 地址：ws://127.0.0.1:8765")
    print("🧩 支持：文本帧、二进制帧、心跳、优雅关闭")
    print("🛡️  异常隔离：解析错误不中断连接")
    print("⌨️  关闭方式：Ctrl + C")
    print("=" * 65)

    await server.wait_closed()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass