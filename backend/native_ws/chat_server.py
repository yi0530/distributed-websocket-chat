"""
native_ws 聊天业务入口。

基于手写 RFC6455 WebSocket 协议层，复用现有聊天 handler（login / room / ACK 等），
完成最小业务闭环：login → create_room → join_room → room_chat → ACK。

与 echo server 的区别：
- echo server 只做文本往返验证协议层；
- chat_server 接入完整的 JSON 应用层协议，注册 ConnectionContext，
  复用 parse_protocol / validate_protocol / dispatch_message。

与主业务（端口 8000）的关系：
- 主业务仍使用 websockets 库，保持完整功能不变；
- chat_server 独立监听 8768 端口，互不干扰。
"""

import asyncio
import os
import traceback

from backend.native_ws.handshake import (
    build_handshake_response,
    parse_http_headers,
    validate_handshake_request,
)
from backend.native_ws.connection import NativeWebSocketConnection
from backend.core.state import ConnectionContext, connections
from backend.core.protocol import parse_protocol, send_error, validate_protocol
from backend.core.connection import dispatch_message
from backend.core.online_presence_service import stop_online_presence
from backend.utils.logger import logger

NATIVE_CHAT_HOST = os.getenv("NATIVE_CHAT_HOST", "127.0.0.1")
NATIVE_CHAT_PORT = int(os.getenv("NATIVE_CHAT_PORT", "8768"))

_MAX_HEADER_BYTES = 8192


async def read_http_request(reader: asyncio.StreamReader) -> bytes:
    """从 TCP 流读取 HTTP 请求头，直到 \\r\\n\\r\\n。"""
    data = b""
    while True:
        try:
            chunk = await reader.read(1024)
        except (ConnectionError, asyncio.IncompleteReadError):
            raise ValueError("连接在握手阶段断开")

        if not chunk:
            raise ValueError("连接在握手阶段关闭")

        data += chunk

        if len(data) > _MAX_HEADER_BYTES:
            raise ValueError(f"HTTP 请求头超过 {_MAX_HEADER_BYTES} 字节")

        if b"\r\n\r\n" in data:
            return data


async def handle_native_chat_client(reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
    """处理一个 TCP 连接：握手 → 注册 ctx → 消息循环 → 清理。"""
    conn = None
    try:
        # ── 阶段 1：WebSocket 握手 ──
        raw_request = await read_http_request(reader)
        request = parse_http_headers(raw_request)
        validate_handshake_request(request)

        key = request.headers["sec-websocket-key"]
        response = build_handshake_response(key)
        writer.write(response)
        await writer.drain()

        # ── 阶段 2：注册连接上下文 ──
        conn = NativeWebSocketConnection(reader, writer, path=request.path)
        ctx = ConnectionContext(websocket=conn)
        connections[conn] = ctx

        addr = writer.get_extra_info("peername")
        logger.info("native_ws 聊天连接: %s path=%s", addr, conn.path)

        # ── 阶段 3：消息循环 ──
        async for raw_message in conn:
            try:
                proto = parse_protocol(raw_message)
            except Exception:
                await send_error(conn, "协议解析失败")
                continue

            if proto is None:
                await send_error(conn, "协议解析失败")
                continue

            ok, err_msg = validate_protocol(proto)
            if not ok:
                await send_error(conn, err_msg, msg_id=proto.get("msg_id"))
                continue

            try:
                await dispatch_message(conn, proto)
            except Exception:
                logger.exception("native_ws 消息处理异常")
                try:
                    await send_error(conn, "服务端内部错误",
                                     msg_id=proto.get("msg_id"))
                except Exception:
                    pass

    except ValueError as e:
        logger.warning("native_ws 握手失败: %s", e)
        try:
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
        logger.info("native_ws 连接断开")

    except Exception:
        traceback.print_exc()

    finally:
        # 1. 先关闭 TCP writer，避免 CLOSE_WAIT 积累
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

        # 2. 在 TCP 已关闭后再清理应用层上下文
        if conn is not None:
            try:
                ctx = connections.get(conn)
                if ctx is not None and ctx.user_id:
                    await stop_online_presence(conn)
            except Exception:
                pass
            connections.pop(conn, None)
        logger.info("native_ws 连接清理完成")


async def main():
    server = await asyncio.start_server(handle_native_chat_client,
                                        NATIVE_CHAT_HOST, NATIVE_CHAT_PORT)
    logger.info("native_ws 聊天服务已启动: ws://%s:%s",
                NATIVE_CHAT_HOST, NATIVE_CHAT_PORT)
    logger.info("主业务不受影响 (ws://127.0.0.1:8000)")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
