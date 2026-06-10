"""
最小 SSE（Server-Sent Events）服务。

用于 WebSocket vs HTTP 长连接的内存占用对比。
只使用 Python 标准库，不依赖第三方包。

用法:
  SSE_HOST=0.0.0.0 SSE_PORT=8770 python tools/load_test/sse_test_server.py

端点:
  GET /events → 返回 text/event-stream，每 5 秒发送 heartbeat

与 WebSocket 对比意义:
  SSE 和 WebSocket 都是基于 TCP 的长连接，但 SSE 是单向（服务器→客户端），
  WebSocket 是双向。两者在维持连接时的内核资源开销可比，
  区别主要体现在应用层协议处理开销。
"""

import asyncio
import os
import time

SSE_HOST = os.getenv("SSE_HOST", "127.0.0.1")
SSE_PORT = int(os.getenv("SSE_PORT", "8770"))

HEARTBEAT_INTERVAL = 5  # 秒


async def handle_sse(reader: asyncio.StreamReader,
                     writer: asyncio.StreamWriter) -> None:
    """处理一个 SSE 连接：200 响应 → 每 5s 发送 heartbeat → 保持连接。"""
    try:
        # 读取 HTTP 请求（只检查路径）
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = await asyncio.wait_for(reader.read(1024), timeout=10)
            if not chunk: break
            data += chunk

        # 发送 SSE 响应头
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: keep-alive\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "\r\n"
        )
        writer.write(response.encode())
        await writer.drain()

        # 持续发送 heartbeat
        seq = 0
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            seq += 1
            msg = f"id: {seq}\ndata: heartbeat {int(time.time())}\n\n"
            writer.write(msg.encode())
            await writer.drain()

    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle_sse, SSE_HOST, SSE_PORT)
    print(f"SSE 测试服务已启动: http://{SSE_HOST}:{SSE_PORT}/events")
    print(f"Heartbeat 间隔: {HEARTBEAT_INTERVAL}s")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
