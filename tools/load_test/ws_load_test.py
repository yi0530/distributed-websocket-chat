"""
WebSocket 并发连接压力测试。

测试 native_ws chat_server 在高并发下的表现。
每个客户端执行最小业务链路：connect → login → join room → chat → ACK → close。

用法:
  python tools/load_test/ws_load_test.py --host 127.0.0.1 --port 8768 --connections 100

输出:
  控制台实时进度 + results/ws_{N}_result.json
"""

import argparse
import asyncio
import json
import os
import time
import struct
import base64
import hashlib
import sys

# 允许从项目根目录导入 native_ws frame
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.native_ws.frame import build_frame, parse_frame, OPCODE_TEXT, OPCODE_CLOSE

# ── 工具函数 ──────────────────────────────────────────────────────

def get_server_stats(pid: int) -> dict:
    """读取 /proc/{pid}/status 获取 RSS 内存和 CPU 信息。"""
    try:
        with open(f"/proc/{pid}/status") as f:
            lines = f.readlines()
        rss_kb = 0
        for line in lines:
            if line.startswith("VmRSS:"):
                rss_kb = int(line.split()[1])
                break
        return {"rss_mb": round(rss_kb / 1024, 2)}
    except Exception:
        return {"rss_mb": 0}


def count_established(port: int) -> int:
    """统计 ss -tan 中 ESTAB 状态的连接数"""
    import subprocess
    try:
        out = subprocess.check_output(
            ["ss", "-tan", f"state established", f"sport = :{port}"],
            text=True, stderr=subprocess.DEVNULL
        )
        return out.count("\n") - 1 if out else 0
    except Exception:
        try:
            out = subprocess.check_output(
                ["ss", "-tan"], text=True, stderr=subprocess.DEVNULL
            )
            count = 0
            for line in out.split("\n"):
                if f":{port}" in line and "ESTAB" in line:
                    count += 1
            return count
        except Exception:
            return 0


def get_cpu_percent(pid: int) -> float:
    """通过 ps 获取 CPU 使用率。"""
    import subprocess
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "%cpu", "--no-headers"],
            text=True, stderr=subprocess.DEVNULL
        )
        return float(out.strip())
    except Exception:
        return 0


# ── WebSocket 客户端 ──────────────────────────────────────────────

async def ws_client(host: str, port: int, user_id: str, room_id: str, timeout: float = 15.0) -> dict:
    """单个 WebSocket 客户端：完成完整业务链路，返回耗时和数据。"""
    result = {
        "user_id": user_id,
        "connect_ok": False, "connect_ms": 0,
        "login_ok": False, "login_ms": 0,
        "chat_ok": False, "chat_ms": 0,
        "ack_ok": False, "ack_rtt_ms": 0,
        "error": None,
    }
    reader = writer = None
    try:
        # ── Connect ──
        t0 = time.time()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout
        )
        key = base64.b64encode(os.urandom(16)).decode()
        guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        req = f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        writer.write(req.encode()); await writer.drain()

        data = b""
        while b"\r\n\r\n" not in data:
            chunk = await asyncio.wait_for(reader.read(4096), timeout)
            if not chunk: raise Exception("no handshake")
            data += chunk
        if b"101" not in data:
            raise Exception("handshake not 101")
        result["connect_ok"] = True
        result["connect_ms"] = round((time.time() - t0) * 1000, 1)

        # ── Helpers ──
        def _mk_msg(mt, mid, **kw):
            m = {"version":"1.0","msg_type":mt,"msg_id":mid,"code":200,"content":None,"err_msg":"","timestamp":int(time.time())}
            m.update(kw); return m

        def _send(msg):
            frame = build_frame(OPCODE_TEXT, json.dumps(msg, ensure_ascii=False).encode(), mask=True)
            writer.write(frame)

        async def _recv(timeout_sec=10):
            buf = b""
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                frame, n = parse_frame(buf)
                if frame is not None:
                    return json.loads(frame.payload)
                chunk = await asyncio.wait_for(reader.read(4096), max(0.1, deadline - time.time()))
                if not chunk: break
                buf += chunk
            raise Exception("recv timeout")

        # ── Login ──（所有连接共用 user001，每个连接有独立 ConnectionContext）
        t0 = time.time()
        _send(_mk_msg("login", f"{user_id}-login", **{"from": "user001", "content": "123456"}))
        resp = await _recv(timeout)
        if resp.get("code") != 200:
            raise Exception(f"login failed: {resp.get('code')}")
        result["login_ok"] = True
        result["login_ms"] = round((time.time() - t0) * 1000, 1)

        # ── Join room ──
        _send(_mk_msg("join_room", f"{user_id}-join", conversation_id=room_id))
        await _recv(timeout)

        # ── Chat + wait ACK ──
        t0 = time.time()
        _send(_mk_msg("room_chat", f"{user_id}-chat", conversation_id=room_id,
                        payload={"text": f"hello from {user_id}"}, need_ack=True))

        # 读到 ack 为止（忽略可能的 room_chat 广播）
        while True:
            resp = await _recv(timeout)
            if resp.get("msg_type") == "ack":
                result["ack_ok"] = True
                result["ack_rtt_ms"] = round((time.time() - t0) * 1000, 1)
                break
        result["chat_ok"] = True
        result["chat_ms"] = round((time.time() - t0) * 1000, 1)

    except asyncio.TimeoutError:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = str(e)[:100]

    finally:
        try:
            if writer:
                cf = build_frame(OPCODE_CLOSE, b"\x03\xe8", mask=True)
                writer.write(cf); writer.close(); await writer.wait_closed()
        except Exception:
            pass

    return result


# ── 主函数 ────────────────────────────────────────────────────────

async def run_load_test(host: str, port: int, connections: int,
                        batch_size: int = 50, server_pid: int = 0):
    print(f"\n{'='*60}")
    print(f"WebSocket 压测: {host}:{port}  {connections} 连接")
    print(f"{'='*60}\n")

    # 创建固定房间供所有客户端加入
    print("准备: 创建测试房间...")
    cr, cw = await asyncio.open_connection(host, port)
    key = base64.b64encode(os.urandom(16)).decode()
    req = f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    cw.write(req.encode()); await cw.drain()
    buf = b""
    while b"\r\n\r\n" not in buf: buf += await cr.read(4096)
    assert b"101" in buf

    def _send(msg):
        cw.write(build_frame(OPCODE_TEXT, json.dumps(msg, ensure_ascii=False).encode(), mask=True))
    async def _recv():
        buf2 = b""
        while True:
            f, _ = parse_frame(buf2)
            if f: return json.loads(f.payload)
            buf2 += await asyncio.wait_for(cr.read(4096), 10)

    _send({"version":"1.0","msg_type":"login","msg_id":"root-login","code":200,"content":"123456","err_msg":"","timestamp":int(time.time()),"from":"user001"})
    await _recv()
    _send({"version":"1.0","msg_type":"create_room","msg_id":"root-room","code":200,"content":None,"err_msg":"","timestamp":int(time.time()),"name":"stress-test-room"})
    resp = await _recv()
    room_id = resp["content"]["conversation_id"]
    cw.close(); await cw.wait_closed()
    print(f"   房间创建完成: {room_id}\n")

    # 测试前资源
    rss_before = get_server_stats(server_pid).get("rss_mb", 0)
    est_before = count_established(port)
    t_start = time.time()

    # 分批并发
    sem = asyncio.Semaphore(batch_size)
    tasks = []
    idx = 0

    async def one_client(user_idx: int):
        nonlocal idx
        async with sem:
            uid = f"u{user_idx:04d}"
            return await ws_client(host, port, uid, room_id)

    for user_idx in range(1, connections + 1):
        tasks.append(asyncio.create_task(one_client(user_idx)))

    # 等待完成，显示进度
    results = []
    done_count = 0
    for coro in asyncio.as_completed(tasks):
        r = await coro
        results.append(r)
        done_count += 1
        if done_count % 50 == 0 or done_count == connections:
            elapsed = time.time() - t_start
            print(f"  进度: {done_count}/{connections}  "
                  f"({done_count/elapsed:.0f} 连接/秒)  "
                  f"成功: {sum(1 for x in results if x['connect_ok'])}")

    t_end = time.time()
    rss_peak = get_server_stats(server_pid).get("rss_mb", 0)
    est_peak = count_established(port)
    cpu_peak = get_cpu_percent(server_pid)

    # 统计
    ok = [r for r in results if r["connect_ok"]]
    login_ok = [r for r in ok if r["login_ok"]]
    ack_ok = [r for r in ok if r["ack_ok"]]
    errors = [r for r in results if r["error"]]

    summary = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": host, "port": port,
        "total_connections": connections,
        "connect_success": len(ok),
        "connect_fail": connections - len(ok),
        "login_success": len(login_ok),
        "login_fail": len(ok) - len(login_ok),
        "ack_success": len(ack_ok),
        "ack_fail": len(ok) - len(ack_ok),
        "avg_connect_ms": round(sum(r["connect_ms"] for r in ok) / max(len(ok), 1), 1),
        "max_connect_ms": round(max(r["connect_ms"] for r in ok) if ok else 0, 1),
        "avg_ack_rtt_ms": round(sum(r["ack_rtt_ms"] for r in ack_ok) / max(len(ack_ok), 1), 1),
        "max_ack_rtt_ms": round(max(r["ack_rtt_ms"] for r in ack_ok) if ack_ok else 0, 1),
        "errors": len(errors),
        "error_rate_pct": round(len(errors) / connections * 100, 1),
        "server_rss_mb_before": rss_before,
        "server_rss_mb_peak": rss_peak,
        "server_cpu_pct_peak": cpu_peak,
        "established_connections_peak": est_peak,
        "established_connections_before": est_before,
        "duration_sec": round(t_end - t_start, 1),
    }

    # 保存
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"ws_{connections}_result.json")
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  结果已保存: {out_file}")
    print(f"  连接成功: {summary['connect_success']}/{connections}  "
          f"ACK 成功率: {summary['ack_success']}/{summary['connect_success']}  "
          f"错误率: {summary['error_rate_pct']}%")
    print(f"  平均连接耗时: {summary['avg_connect_ms']}ms  最大: {summary['max_connect_ms']}ms")
    print(f"  平均 ACK RTT: {summary['avg_ack_rtt_ms']}ms  最大: {summary['max_ack_rtt_ms']}ms")
    print(f"  服务器内存: {rss_before}MB → 峰值 {rss_peak}MB")
    print(f"  ESTAB 连接: {est_before} → 峰值 {est_peak}\n")

    if summary["error_rate_pct"] > 10:
        print("  !! 错误率超过 10%，建议停止更高规模测试")

    return summary


def main():
    parser = argparse.ArgumentParser(description="WebSocket 并发压测")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--connections", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=50,
                        help="每批并发连接数")
    parser.add_argument("--output", default="",
                        help="输出目录（默认 results/）")
    parser.add_argument("--server-pid", type=int, default=0,
                        help="被测试服务进程 PID（用于资源监控）")
    args = parser.parse_args()

    asyncio.run(run_load_test(
        args.host, args.port, args.connections,
        batch_size=args.batch_size, server_pid=args.server_pid
    ))


if __name__ == "__main__":
    main()
