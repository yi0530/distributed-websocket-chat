"""
RFC6455 Section 5-7 — 基于手写帧的 WebSocket 连接。

在 asyncio TCP stream 之上提供 WebSocket 语义的 send/recv/close。

设计要点：

1. 接收缓冲区
   TCP 是字节流，一次 read 可能只收到半帧。recv_frame 内部维护一个
   字节缓冲区，每次读取后尝试 parse_frame，不完整则继续读。

2. ping/pong 自动回复
   RFC6455 Section 5.5.3：收到 ping 后必须尽快回复 pong。
   recv_text 在收到 ping 帧时自动回复 pong，然后继续等待下一帧，
   对上层调用者透明。

3. close 帧回应
   RFC6455 Section 5.5.1：收到 close 帧后应回复 close 帧，然后关闭
   TCP 连接。这是 WebSocket 的"礼貌关闭"握手。

4. 服务端不 mask
   RFC6455 Section 5.3：客户端→服务端帧必须 mask，服务端→客户端帧
   绝对不能 mask。send_* 系列方法默认 mask=False。

5. 不分片重组
   第一版假定每个应用消息只占一帧（FIN=1）。课程作业主要用于展示
   协议握手和基础帧收发，分片消息重组属于后续改进。
"""

import asyncio
import struct

from backend.native_ws.frame import (
    OPCODE_TEXT,
    OPCODE_BINARY,
    OPCODE_CLOSE,
    OPCODE_PING,
    OPCODE_PONG,
    Frame,
    build_frame,
    parse_frame,
    is_control_frame,
    is_close_frame,
    is_ping_frame,
    is_pong_frame,
)


class NativeWebSocketConnection:
    """基于手写帧解析的 WebSocket 连接。"""

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter, path: str = "/"):
        self._reader = reader
        self._writer = writer
        self.path = path
        self.closed = False
        self._recv_buf = b""               # 接收缓冲区：累积 TCP 字节流

    # ── 帧级接收 ──────────────────────────────────────────────

    async def recv_frame(self) -> Frame | None:
        """从 TCP 流中读取一个完整 WebSocket 帧。

        如果连接已关闭或对方发送了 close 帧之后连接断开，返回 None。
        """
        if self.closed:
            return None

        while True:
            # 先尝试从已有缓冲区解析
            frame, consumed = parse_frame(self._recv_buf)
            if frame is not None:
                self._recv_buf = self._recv_buf[consumed:]
                return frame

            # 数据不完整，继续读取
            try:
                chunk = await self._reader.read(4096)
            except (ConnectionError, asyncio.IncompleteReadError):
                self.closed = True
                return None

            if not chunk:
                # TCP 连接已关闭（EOF）
                self.closed = True
                return None

            self._recv_buf += chunk

    # ── 消息级接收（处理控制帧） ──────────────────────────────

    async def recv_text(self) -> str | None:
        """读取下一帧文本消息。

        自动处理控制帧：
        - ping → 回复 pong，继续等待
        - pong → 忽略，继续等待
        - close → 回复 close，返回 None
        - binary → 返回提示字符串（第一版不做二进制业务处理）
        - text → 解码并返回字符串
        """
        while True:
            frame = await self.recv_frame()
            if frame is None:
                return None

            # ── RFC6455 Section 5.5.3：收到 ping 必须回复 pong ──
            if is_ping_frame(frame.opcode):
                await self.send_pong(frame.payload)
                continue

            # ── pong 可以忽略（主动 ping 的响应由调用方自行处理） ──
            if is_pong_frame(frame.opcode):
                continue

            # ── RFC6455 Section 5.5.1：收到 close 应回复 close ──
            if is_close_frame(frame.opcode):
                # 回显对方发来的 close payload
                await self._send_close_frame(frame.payload)
                await self._close_writer()
                return None

            # ── text 帧 ──
            if frame.opcode == OPCODE_TEXT:
                return frame.payload.decode("utf-8", errors="replace")

            # ── binary 帧：第一版不处理二进制业务 ──
            if frame.opcode == OPCODE_BINARY:
                return f"[binary frame, {frame.payload_length} bytes]"

            # 其余帧类型（continuation 等）忽略
            continue

    # ── 发送方法（服务端不 mask） ──────────────────────────────

    async def send_text(self, text: str) -> None:
        """发送文本帧（不 mask，符合服务端规则）。"""
        payload = text.encode("utf-8")
        await self._send_bytes(build_frame(OPCODE_TEXT, payload))

    async def send_binary(self, data: bytes) -> None:
        """发送二进制帧（不 mask）。"""
        await self._send_bytes(build_frame(OPCODE_BINARY, data))

    async def send_ping(self, payload: bytes = b"") -> None:
        """发送 ping 帧。"""
        await self._send_bytes(build_frame(OPCODE_PING, payload))

    async def send_pong(self, payload: bytes = b"") -> None:
        """发送 pong 帧。"""
        await self._send_bytes(build_frame(OPCODE_PONG, payload))

    # ── 关闭连接 ──────────────────────────────────────────────

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """发送 close 帧并关闭 TCP 连接。

        RFC6455 Section 5.5.1：close 帧载荷格式为
        2 字节状态码（大端无符号）+ 可选原因字符串（UTF-8）。
        """
        if self.closed:
            return

        # 构造 close payload：2 字节状态码 + reason
        reason_bytes = reason.encode("utf-8")
        close_payload = struct.pack("!H", code) + reason_bytes

        await self._send_close_frame(close_payload)
        await self._close_writer()

    # ── 异步迭代器（用于 server.py echo 循环） ────────────────

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        message = await self.recv_text()
        if message is None:
            raise StopAsyncIteration
        return message

    # ── 内部方法 ──────────────────────────────────────────────

    async def _send_bytes(self, data: bytes) -> None:
        """底层写入。"""
        if self.closed:
            return
        try:
            self._writer.write(data)
            await self._writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            self.closed = True

    async def _send_close_frame(self, payload: bytes) -> None:
        """发送 close 帧（不检查 closed，因为回应 close 也是合法的）。"""
        try:
            self._writer.write(build_frame(OPCODE_CLOSE, payload))
            await self._writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            self.closed = True

    async def _close_writer(self) -> None:
        """关闭底层 TCP 连接。"""
        self.closed = True
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass


# ── 自检说明 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("connection.py 自检：")
    print("  本模块依赖 asyncio TCP stream，无独立自检。")
    print("  端到端验证请等待 server.py 完成后执行：")
    print("    python -m backend.native_ws.server")
    print("  然后用浏览器 WebSocket 连接 ws://localhost:9001")
    print("  发送消息后应收到 echo 回复。")
    print()
    print("  当前可做语法检查：python -m py_compile backend/native_ws/connection.py")
