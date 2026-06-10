"""
手写 RFC6455 WebSocket 独立 echo 服务。

本文件是 native_ws 模块的入口，用于验证：
- HTTP Upgrade 握手（handshake.py）
- WebSocket frame 收发（frame.py）
- 连接抽象（connection.py）

工作流程：

1. 浏览器发起 TCP 连接
   → 读取 HTTP Upgrade 请求头（直到 \r\n\r\n）
   → 解析请求行 + 头部
   → 校验 WebSocket 握手条件
   → 计算 Sec-WebSocket-Accept
   → 返回 HTTP 101 Switching Protocols

2. 握手完成后，同一 TCP 连接进入 WebSocket 帧模式
   → 创建 NativeWebSocketConnection 接管 reader/writer
   → 进入 echo 循环：收到文本 → 回复 "echo: <原文>"
   → ping 自动 pong（由 connection.py 处理）
   → close 帧优雅关闭

3. 为什么端口和主业务分开？
   主业务（ws://localhost:8000）仍使用外部 WebSocket 库，保留完整的
   JWT/Redis/房间/私聊功能。native_ws echo server 在独立端口 8766
   运行，互不干扰，用于抓包验证和课程展示。
"""

import asyncio
import traceback

from backend.native_ws.handshake import (
    build_handshake_response,
    parse_http_headers,
    validate_handshake_request,
)
from backend.native_ws.connection import NativeWebSocketConnection

# 独立端口，不占用主业务 8000
HOST = "127.0.0.1"
PORT = 8766

# HTTP 头部最大 8KB（足够容纳标准 WebSocket 握手请求）
_MAX_HEADER_BYTES = 8192


# ── 读取 HTTP Upgrade 请求 ──────────────────────────────────────

async def read_http_request(reader: asyncio.StreamReader) -> bytes:
    """从 TCP 流读取 HTTP 请求，直到 \\r\\n\\r\\n（头部结束标记）。

    为什么先读 HTTP 头再进入帧模式？
    WebSocket 连接建立分两个阶段：
    - 阶段 1（HTTP）：客户端发送 Upgrade 请求，服务端返回 101
    - 阶段 2（WebSocket 帧）：同一 TCP 连接切换到二进制帧协议
    只有完成握手后，后续字节才是 WebSocket frame。
    """
    data = b""
    while True:
        # 读取一块数据
        try:
            chunk = await reader.read(1024)
        except (ConnectionError, asyncio.IncompleteReadError):
            raise ValueError("连接在握手阶段断开")

        if not chunk:
            raise ValueError("连接在握手阶段关闭")

        data += chunk

        # 超出最大头部大小
        if len(data) > _MAX_HEADER_BYTES:
            raise ValueError(f"HTTP 请求头超过 {_MAX_HEADER_BYTES} 字节")

        # 找到头部结束标记
        if b"\r\n\r\n" in data:
            return data


# ── 客户端处理器 ─────────────────────────────────────────────────

async def handle_client(reader: asyncio.StreamReader,
                        writer: asyncio.StreamWriter) -> None:
    """处理一个 TCP 连接：握手 → echo 循环 → 关闭。"""
    conn = None
    try:
        # ── 阶段 1：读取并完成 WebSocket 握手 ──
        raw_request = await read_http_request(reader)
        request = parse_http_headers(raw_request)
        validate_handshake_request(request)

        key = request.headers["sec-websocket-key"]
        response = build_handshake_response(key)
        writer.write(response)
        await writer.drain()

        # 握手完成，创建 WebSocket 连接对象
        # 此后 reader/writer 的数据是 WebSocket frame，不再是 HTTP
        conn = NativeWebSocketConnection(reader, writer, path=request.path)
        addr = writer.get_extra_info("peername")
        print(f"[native_ws] 连接: {addr} path={conn.path}")

        # ── 阶段 2：WebSocket echo 循环 ──
        async for message in conn:
            print(f"[native_ws] 收到: {message!r}")
            await conn.send_text(f"echo: {message}")

    except ValueError as e:
        # 握手阶段校验失败（缺少 Upgrade 头、非 GET 等）
        print(f"[native_ws] 握手失败: {e}")
        try:
            # 尝试返回 HTTP 400 错误（如果连接仍在）
            body = f"握手失败: {e}\r\n".encode("utf-8")
            header = (
                f"HTTP/1.1 400 Bad Request\r\n"
                f"Content-Type: text/plain\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n"
            ).encode("utf-8")
            writer.write(header + body)
            await writer.drain()
        except Exception:
            pass

    except (ConnectionError, asyncio.IncompleteReadError):
        print(f"[native_ws] 连接异常断开")

    except Exception:
        traceback.print_exc()

    finally:
        print(f"[native_ws] 连接关闭: path={conn.path if conn else '?'}")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── 服务入口 ─────────────────────────────────────────────────────

async def main():
    """启动手写 WebSocket echo server。"""
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"[native_ws] 手写 RFC6455 WebSocket echo server 已启动")
    print(f"[native_ws] 地址: ws://{HOST}:{PORT}")
    print(f"[native_ws] 主业务不受影响 (ws://{HOST}:8000)")
    print()

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
