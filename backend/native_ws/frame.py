"""
RFC6455 Section 5 — Data Framing.

WebSocket 帧格式（RFC6455 Section 5.2）：

    字节 0: [FIN 1bit] [RSV 3bit] [OPCODE 4bit]
    字节 1: [MASK 1bit] [PAYLOAD_LEN 7bit]
    字节 2+: 扩展载荷长度 (0/2/8 字节) + 掩码密钥 (0/4 字节) + 载荷数据

- FIN=1 表示最后一帧，控制帧 FIN 必须为 1
- OPCODE: 0x1=text, 0x2=binary, 0x8=close, 0x9=ping, 0xA=pong
- MASK=1 表示载荷被掩码（客户端→服务端必须 mask）
- PAYLOAD_LEN:
    0-125  → 直接表示长度
    126    → 后续 2 字节无符号大端整数
    127    → 后续 8 字节无符号大端整数
"""

import os
import struct
from dataclasses import dataclass

# ── Opcode 常量 ───────────────────────────────────────────────────

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA

# 控制帧（opcode >= 0x8）payload 不得超过 125 字节（RFC6455 Section 5.5）
_MAX_CONTROL_PAYLOAD = 125


# ── Frame 数据结构 ────────────────────────────────────────────────

@dataclass
class Frame:
    fin: bool
    opcode: int
    mask: bool
    payload_length: int
    mask_key: bytes | None
    payload: bytes


# ── Mask / unmask ─────────────────────────────────────────────────

def mask_payload(data: bytes, mask_key: bytes) -> bytes:
    """对 data 逐字节做 XOR mask（RFC6455 Section 5.3）。

    mask 和 unmask 是同一操作：XOR 两次还原原文。
    """
    if len(mask_key) != 4:
        raise ValueError("mask_key 必须是 4 字节")
    return bytes(data[i] ^ mask_key[i % 4] for i in range(len(data)))


# ── 帧类型判断 ────────────────────────────────────────────────────

def is_control_frame(opcode: int) -> bool:
    """opcode >= 0x8 即为控制帧（close / ping / pong）。"""
    return opcode >= 0x8


def is_close_frame(opcode: int) -> bool:
    return opcode == OPCODE_CLOSE


def is_ping_frame(opcode: int) -> bool:
    return opcode == OPCODE_PING


def is_pong_frame(opcode: int) -> bool:
    return opcode == OPCODE_PONG


# ── 帧解析 ────────────────────────────────────────────────────────

def parse_frame(data: bytes) -> tuple[Frame | None, int]:
    """从字节流头部解析一帧。

    返回 (Frame, 消耗字节数)。数据不完整时返回 (None, 0)，不抛异常。
    """
    if len(data) < 2:
        return None, 0

    # ── 字节 0：FIN (bit 7) + RSV (bit 6-4) + OPCODE (bit 3-0) ──
    byte0 = data[0]
    fin = bool(byte0 & 0x80)          # bit 7
    opcode = byte0 & 0x0F             # bit 3-0

    # ── 字节 1：MASK (bit 7) + PAYLOAD LEN (bit 6-0) ──
    byte1 = data[1]
    masked = bool(byte1 & 0x80)       # bit 7
    payload_len = byte1 & 0x7F        # bit 6-0

    pos = 2

    # ── 扩展载荷长度 ──
    if payload_len == 126:
        # 后续 2 字节无符号大端表示实际长度 (max 65535)
        if len(data) < pos + 2:
            return None, 0
        payload_len = struct.unpack("!H", data[pos:pos + 2])[0]
        pos += 2
    elif payload_len == 127:
        # 后续 8 字节无符号大端表示实际长度
        if len(data) < pos + 8:
            return None, 0
        payload_len = struct.unpack("!Q", data[pos:pos + 8])[0]
        pos += 8

    # ── 掩码密钥（客户端→服务端） ──
    mask_key = None
    if masked:
        if len(data) < pos + 4:
            return None, 0
        mask_key = data[pos:pos + 4]
        pos += 4

    # ── 载荷 ──
    if len(data) < pos + payload_len:
        return None, 0

    payload = data[pos:pos + payload_len]
    pos += payload_len

    # 解码掩码
    if mask_key:
        payload = mask_payload(payload, mask_key)

    return Frame(
        fin=fin,
        opcode=opcode,
        mask=masked,
        payload_length=payload_len,
        mask_key=mask_key,
        payload=payload,
    ), pos


# ── 帧构造 ────────────────────────────────────────────────────────

def build_frame(
    opcode: int,
    payload: bytes = b"",
    *,
    fin: bool = True,
    mask: bool = False,
    mask_key: bytes | None = None,
) -> bytes:
    """构造一帧，返回完整字节序列。

    服务端发往客户端默认 mask=False（不掩码）。
    客户端→服务端须 mask=True，不传 mask_key 则自动生成随机密钥。
    """
    # ── 校验 ──
    if opcode not in (OPCODE_CONTINUATION, OPCODE_TEXT, OPCODE_BINARY,
                       OPCODE_CLOSE, OPCODE_PING, OPCODE_PONG):
        raise ValueError(f"非法 opcode: {opcode:#04x}")

    if is_control_frame(opcode):
        if not fin:
            raise ValueError("控制帧 FIN 必须为 True")
        if len(payload) > _MAX_CONTROL_PAYLOAD:
            raise ValueError(f"控制帧载荷不得超过 {_MAX_CONTROL_PAYLOAD} 字节")

    if mask:
        if mask_key is None:
            mask_key = os.urandom(4)       # 随机生成 4 字节掩码密钥
        elif len(mask_key) != 4:
            raise ValueError("mask_key 必须是 4 字节")

    payload_length = len(payload)

    # 如果需要掩码，先对载荷做 XOR
    wire_payload = mask_payload(payload, mask_key) if mask else payload

    buf = bytearray()

    # ── 字节 0：FIN (1bit) + RSV 全 0 (3bit) + OPCODE (4bit) ──
    buf.append((0x80 if fin else 0x00) | (opcode & 0x0F))

    # ── 字节 1：MASK (1bit) + PAYLOAD LEN (7bit) ──
    mask_bit = 0x80 if mask else 0x00

    if payload_length <= 125:
        # 7-bit 直接表示长度
        buf.append(mask_bit | payload_length)
    elif payload_length <= 65535:
        # 126 标记 + 2 字节扩展长度（大端无符号）
        buf.append(mask_bit | 126)
        buf.extend(struct.pack("!H", payload_length))
    else:
        # 127 标记 + 8 字节扩展长度（大端无符号）
        buf.append(mask_bit | 127)
        buf.extend(struct.pack("!Q", payload_length))

    # ── 掩码密钥（4 字节，仅当 mask=True） ──
    if mask:
        buf.extend(mask_key)

    # ── 载荷 ──
    buf.extend(wire_payload)

    return bytes(buf)


# ── 自检 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    passed = 0
    failed = 0

    def check(name: str, condition: bool):
        global passed, failed
        if condition:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")

    print("=== frame.py 自检 ===\n")

    # 1. 文本帧往返（不掩码）
    print("[1] 文本帧 roundtrip（不掩码）")
    built = build_frame(OPCODE_TEXT, b"Hello, WebSocket!")
    f, n = parse_frame(built)
    assert f is not None
    check("FIN=True", f.fin is True)
    check("opcode=TEXT", f.opcode == OPCODE_TEXT)
    check("mask=False", f.mask is False)
    check("载荷一致", f.payload == b"Hello, WebSocket!")
    check("消耗全部字节", n == len(built))

    # 2. 掩码帧解析
    print("\n[2] 掩码帧解析")
    mk = b"\x01\x02\x03\x04"
    built2 = build_frame(OPCODE_TEXT, b"masked-data", mask=True, mask_key=mk)
    f2, _ = parse_frame(built2)
    assert f2 is not None
    check("mask=True", f2.mask is True)
    check("掩码密钥一致", f2.mask_key == mk)
    check("解码后载荷一致", f2.payload == b"masked-data")

    # 3. 载荷长度 126（2 字节扩展）
    print("\n[3] 载荷长度=126（256 字节）")
    p3 = b"X" * 256
    built3 = build_frame(OPCODE_BINARY, p3)
    f3, _ = parse_frame(built3)
    assert f3 is not None
    check("长度=256", f3.payload_length == 256)
    check("载荷一致", f3.payload == p3)
    check("帧头标记 126", built3[1] & 0x7F == 126)

    # 4. ping 帧
    print("\n[4] ping 帧")
    built4 = build_frame(OPCODE_PING, b"ping-data")
    f4, _ = parse_frame(built4)
    assert f4 is not None
    check("opcode=PING", f4.opcode == OPCODE_PING)
    check("FIN=True", f4.fin is True)
    check("载荷一致", f4.payload == b"ping-data")

    # 5. close 帧（带状态码 1000）
    print("\n[5] close 帧（状态码 1000）")
    built5 = build_frame(OPCODE_CLOSE, b"\x03\xe8")   # 1000 = 0x03E8
    f5, _ = parse_frame(built5)
    assert f5 is not None
    check("opcode=CLOSE", f5.opcode == OPCODE_CLOSE)
    check("载荷=状态码", f5.payload == b"\x03\xe8")

    # 6. 控制帧载荷 >125 → ValueError
    print("\n[6] 控制帧载荷 >125 → ValueError")
    try:
        build_frame(OPCODE_PING, b"X" * 126)
        check("抛出 ValueError", False)
    except ValueError:
        check("抛出 ValueError", True)

    # 7. 控制帧 FIN=False → ValueError
    print("\n[7] 控制帧 FIN=False → ValueError")
    try:
        build_frame(OPCODE_CLOSE, b"", fin=False)
        check("抛出 ValueError", False)
    except ValueError:
        check("抛出 ValueError", True)

    # 8. 非法 opcode → ValueError
    print("\n[8] 非法 opcode(0x3) → ValueError")
    try:
        build_frame(0x3)
        check("抛出 ValueError", False)
    except ValueError:
        check("抛出 ValueError", True)

    # 9. 数据不完整 → (None, 0)
    print("\n[9] 不完整数据 → (None, 0)")
    full = build_frame(OPCODE_TEXT, b"complete")
    half = full[:3]
    f9, n9 = parse_frame(half)
    check("返回 None", f9 is None)
    check("消耗 0", n9 == 0)

    # 10. 辅助函数
    print("\n[10] 分类辅助函数")
    check("is_control_frame(PING)=True", is_control_frame(OPCODE_PING) is True)
    check("is_control_frame(TEXT)=False", is_control_frame(OPCODE_TEXT) is False)
    check("is_close_frame(CLOSE)=True", is_close_frame(OPCODE_CLOSE) is True)
    check("is_close_frame(PING)=False", is_close_frame(OPCODE_PING) is False)
    check("is_ping_frame(PING)=True", is_ping_frame(OPCODE_PING) is True)
    check("is_pong_frame(PONG)=True", is_pong_frame(OPCODE_PONG) is True)

    # 11. 空载荷帧
    print("\n[11] 空载荷帧")
    built11 = build_frame(OPCODE_TEXT, b"")
    f11, _ = parse_frame(built11)
    assert f11 is not None
    check("空载荷 roundtrip", f11.payload == b"" and f11.payload_length == 0)

    print(f"\n{'='*40}")
    print(f"结果: {passed} 通过, {failed} 失败")
    if failed:
        raise SystemExit(1)
