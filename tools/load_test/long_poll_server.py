"""
HTTP 长轮询（Long Polling）测试服务。

用于 WebSocket vs HTTP Long Polling 1000 并发内存占用对比。
只使用 Python 标准库。

与 SSE 的区别：
- SSE：服务端推送流 (text/event-stream)，连接持续不关闭
- Long Polling：每次 /poll 挂起 → 超时返回 JSON → 连接关闭 → 客户端重新发起
- Long Polling 更接近传统 HTTP 长轮询业务模型

用法:
  LONG_POLL_HOST=0.0.0.0 LONG_POLL_PORT=8771 python tools/load_test/long_poll_server.py
"""

import asyncio
import json
import os
import time
import sys

LONG_POLL_HOST = os.getenv("LONG_POLL_HOST", "127.0.0.1")
LONG_POLL_PORT = int(os.getenv("LONG_POLL_PORT", "8771"))
POLL_TIMEOUT = float(os.getenv("LONG_POLL_TIMEOUT", "25"))

# 统计
active_polls = 0
total_requests = 0
completed_requests = 0
start_time = time.time()


async def handle_poll(reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter) -> None:
    global active_polls, total_requests, completed_requests

    try:
        # 读取 HTTP 请求
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
            if not chunk: break
            data += chunk

        # 解析路径
        first_line = data.split(b"\r\n")[0].decode()
        parts = first_line.split()
        path = parts[1] if len(parts) > 1 else "/"

        if not path.startswith("/poll"):
            body = b"Not Found"
            header = (
                "HTTP/1.1 404 Not Found\r\n"
                "Content-Type: text/plain\r\n"
                f"Content-Length: {len(body)}\r\n"
                "\r\n"
            ).encode()
            writer.write(header + body)
            await writer.drain()
            return

        # 解析 client_id
        client_id = "unknown"
        if "client_id=" in path:
            try:
                client_id = path.split("client_id=")[1].split("&")[0]
            except Exception:
                pass

        total_requests += 1
        active_polls += 1

        # 模拟服务端挂起
        await asyncio.sleep(POLL_TIMEOUT)

        # 返回 JSON
        resp_body = json.dumps({
            "type": "timeout",
            "client_id": client_id,
            "timestamp": int(time.time()),
        })
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(resp_body)}\r\n"
            "\r\n"
        )
        writer.write(header.encode() + resp_body.encode())
        await writer.drain()

        completed_requests += 1

    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    except Exception:
        pass
    finally:
        active_polls = max(0, active_polls - 1)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def stats_reporter():
    """每 5 秒打印统计信息。"""
    while True:
        await asyncio.sleep(5)
        elapsed = int(time.time() - start_time)
        print(f"[stats] active={active_polls}  "
              f"total={total_requests}  completed={completed_requests}  "
              f"uptime={elapsed}s")


async def main():
    server = await asyncio.start_server(handle_poll, LONG_POLL_HOST, LONG_POLL_PORT)
    print(f"HTTP Long Polling 测试服务已启动: http://{LONG_POLL_HOST}:{LONG_POLL_PORT}/poll")
    print(f"Poll timeout: {POLL_TIMEOUT}s")
    asyncio.create_task(stats_reporter())
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
