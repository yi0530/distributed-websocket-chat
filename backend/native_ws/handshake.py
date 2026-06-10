"""
RFC6455 Section 4 — Opening Handshake.

WebSocket 连接建立流程：

1. 浏览器发起 HTTP GET，带上 Upgrade 头：
       GET /chat HTTP/1.1
       Upgrade: websocket
       Connection: Upgrade
       Sec-WebSocket-Key: <base64 随机 16 字节>
       Sec-WebSocket-Version: 13

2. 服务端验证请求头，拼接 GUID 计算 Accept：
       accept = base64(sha1(Key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))

   为什么拼接 GUID（Magic String）？
   - GUID 是 RFC6455 规定的固定魔术字符串
   - 确保服务端"理解 WebSocket 协议"而非意外响应
   - 因为普通 HTTP 服务不会知道这个 GUID 拼接规则
   - sha1 + base64 将客户端随机 Key 转换为固定格式的 Accept 值

3. 服务端返回 101 Switching Protocols：
       HTTP/1.1 101 Switching Protocols
       Upgrade: websocket
       Connection: Upgrade
       Sec-WebSocket-Accept: <base64>

   101 状态码代表"协议升级成功"，此后 TCP 连接进入 WebSocket 帧模式。
"""

import base64
import hashlib
from dataclasses import dataclass

# RFC6455 Section 4.2.2 — 固定魔术字符串
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


@dataclass
class HandshakeRequest:
    """解析后的 HTTP Upgrade 请求。"""
    method: str
    path: str
    version: str
    headers: dict[str, str]       # 键统一小写


# ── HTTP 请求头解析 ──────────────────────────────────────────────

def parse_http_headers(raw_request: bytes) -> HandshakeRequest:
    """从原始 HTTP 请求字节流解析请求行和头部。

    不处理请求体（WebSocket 握手不含 body）。
    """
    text = raw_request.decode("utf-8", errors="replace")
    lines = text.split("\r\n")

    if not lines:
        raise ValueError("空请求")

    # ── 请求行：METHOD PATH HTTP/VERSION ──
    parts = lines[0].split(" ", 2)
    if len(parts) < 3:
        raise ValueError(f"请求行格式错误: {lines[0]!r}")
    method, path, version = parts[0], parts[1], parts[2]

    # ── 头部行：Key: Value ──
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            break                       # 空行 = 头部结束
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()

    return HandshakeRequest(method=method, path=path, version=version, headers=headers)


# ── 握手请求校验 ──────────────────────────────────────────────────

def validate_handshake_request(request: HandshakeRequest) -> None:
    """校验 HTTP Upgrade 请求是否满足 RFC6455 要求。

    不满足则抛出 ValueError，包含具体原因。
    """
    # 必须是 GET（RFC6455 Section 4.2.1）
    if request.method.upper() != "GET":
        raise ValueError(f"WebSocket 握手必须使用 GET，实际: {request.method}")

    # HTTP 版本必须是 HTTP/1.1
    if request.version.upper() != "HTTP/1.1":
        raise ValueError(f"WebSocket 握手要求 HTTP/1.1，实际: {request.version}")

    # Upgrade 头必须包含 "websocket"（大小写不敏感）
    upgrade = request.headers.get("upgrade", "")
    if "websocket" not in upgrade.lower():
        raise ValueError(f"缺少 Upgrade: websocket，实际: {upgrade!r}")

    # Connection 头必须包含 "Upgrade"（大小写不敏感）
    connection = request.headers.get("connection", "")
    if "upgrade" not in connection.lower():
        raise ValueError(f"缺少 Connection: Upgrade，实际: {connection!r}")

    # Sec-WebSocket-Key 必须存在（RFC6455 Section 4.2.1 第 7 步）
    key = request.headers.get("sec-websocket-key", "")
    if not key:
        raise ValueError("缺少 Sec-WebSocket-Key 头")

    # Sec-WebSocket-Version 必须是 13（RFC6455 Section 4.2.1 第 9 步）
    version = request.headers.get("sec-websocket-version", "")
    if version != "13":
        raise ValueError(f"Sec-WebSocket-Version 必须是 13，实际: {version!r}")


# ── Accept 密钥计算 ───────────────────────────────────────────────

def compute_accept_key(sec_websocket_key: str) -> str:
    """计算 Sec-WebSocket-Accept（RFC6455 Section 4.2.2 第 5 步）。

    步骤：
    1. 拼接客户端 Key + GUID
    2. SHA-1 哈希
    3. Base64 编码
    """
    combined = sec_websocket_key + WEBSOCKET_GUID
    sha1_bytes = hashlib.sha1(combined.encode("utf-8")).digest()
    return base64.b64encode(sha1_bytes).decode("ascii")


# ── 握手响应构造 ──────────────────────────────────────────────────

def build_handshake_response(sec_websocket_key: str) -> bytes:
    """构造 HTTP 101 Switching Protocols 响应。

    返回完整的 HTTP 响应字节流（包含 \r\n\r\n 结尾）。
    浏览器收到此响应后，同一 TCP 连接即切换为 WebSocket 帧模式。
    """
    accept = compute_accept_key(sec_websocket_key)

    # RFC6455 Section 4.2.2 — 服务端握手响应格式
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )
    return response.encode("utf-8")


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

    print("=== handshake.py 自检 ===\n")

    # 1. RFC6455 官方示例（Section 4.2.2 第 5 步示例值）
    print("[1] 官方 Accept 密钥示例")
    official_key = "dGhlIHNhbXBsZSBub25jZQ=="
    expected_accept = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    actual = compute_accept_key(official_key)
    check("Accept 密钥匹配", actual == expected_accept)
    print(f"      key={official_key}")
    print(f"   accept={actual}")

    # 2. 解析标准 WebSocket Upgrade 请求
    print("\n[2] 解析标准 Upgrade 请求")
    raw = (
        b"GET /chat HTTP/1.1\r\n"
        b"Host: localhost:9001\r\n"
        b"Upgrade: websocket\r\n"
        b"Connection: Upgrade\r\n"
        b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        b"Sec-WebSocket-Version: 13\r\n"
        b"\r\n"
    )
    req = parse_http_headers(raw)
    check("method=GET", req.method == "GET")
    check("path=/chat", req.path == "/chat")
    check("version=HTTP/1.1", req.version == "HTTP/1.1")
    check("Upgrade 头", req.headers.get("upgrade") == "websocket")
    check("Connection 头", req.headers.get("connection") == "Upgrade")
    check("Sec-WebSocket-Key 存在", req.headers.get("sec-websocket-key") == official_key)
    check("Sec-WebSocket-Version=13", req.headers.get("sec-websocket-version") == "13")

    # 3. 校验通过不会抛异常
    print("\n[3] 校验合法请求（不应抛异常）")
    try:
        validate_handshake_request(req)
        check("校验通过", True)
    except ValueError as e:
        check(f"校验通过（不应抛异常: {e}）", False)

    # 4. 构造 101 响应
    print("\n[4] 构造 101 响应")
    resp = build_handshake_response(official_key)
    resp_text = resp.decode("utf-8")
    check("包含 101", "101 Switching Protocols" in resp_text)
    check("包含 Upgrade: websocket", "Upgrade: websocket" in resp_text)
    check("包含 Connection: Upgrade", "Connection: Upgrade" in resp_text)
    check("包含 Sec-WebSocket-Accept", f"Sec-WebSocket-Accept: {expected_accept}" in resp_text)
    check("以 \\r\\n\\r\\n 结尾", resp.endswith(b"\r\n\r\n"))

    # 5. 缺少 Sec-WebSocket-Key → ValueError
    print("\n[5] 缺少 Sec-WebSocket-Key → ValueError")
    bad_req = HandshakeRequest(
        method="GET", path="/", version="HTTP/1.1",
        headers={"upgrade": "websocket", "connection": "upgrade",
                 "sec-websocket-version": "13"}
    )
    try:
        validate_handshake_request(bad_req)
        check("抛出 ValueError", False)
    except ValueError as e:
        check(f"抛出 ValueError: {e}", "Sec-WebSocket-Key" in str(e))

    # 6. version 不是 13 → ValueError
    print("\n[6] 版本不是 13 → ValueError")
    bad_ver = HandshakeRequest(
        method="GET", path="/", version="HTTP/1.1",
        headers={"upgrade": "websocket", "connection": "upgrade",
                 "sec-websocket-key": official_key,
                 "sec-websocket-version": "8"}
    )
    try:
        validate_handshake_request(bad_ver)
        check("抛出 ValueError", False)
    except ValueError as e:
        check(f"抛出 ValueError: {e}", "Sec-WebSocket-Version" in str(e))

    # 7. method 不是 GET → ValueError
    print("\n[7] method 不是 GET → ValueError")
    bad_method = HandshakeRequest(
        method="POST", path="/", version="HTTP/1.1",
        headers={"upgrade": "websocket", "connection": "upgrade",
                 "sec-websocket-key": official_key,
                 "sec-websocket-version": "13"}
    )
    try:
        validate_handshake_request(bad_method)
        check("抛出 ValueError", False)
    except ValueError as e:
        check(f"抛出 ValueError: {e}", "GET" in str(e))

    # 8. 缺少 Upgrade 头 → ValueError
    print("\n[8] 缺少 Upgrade 头 → ValueError")
    bad_upgrade = HandshakeRequest(
        method="GET", path="/", version="HTTP/1.1",
        headers={"connection": "upgrade",
                 "sec-websocket-key": official_key,
                 "sec-websocket-version": "13"}
    )
    try:
        validate_handshake_request(bad_upgrade)
        check("抛出 ValueError", False)
    except ValueError as e:
        check(f"抛出 ValueError: {e}", "Upgrade" in str(e))

    print(f"\n{'='*40}")
    print(f"结果: {passed} 通过, {failed} 失败")
    if failed:
        raise SystemExit(1)
