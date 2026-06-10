"""
WebSocket 并发连接压力测试 — 支持三种模式。

用法:
  idle 模式（1000 并发内存测试）:
    python tools/load_test/ws_load_test.py --mode idle --connections 100 --duration 30

  ack_isolated 模式（ACK 功能验证，每批独立房间）:
    python tools/load_test/ws_load_test.py --mode ack_isolated --connections 100 --batch-size 5

  broadcast 模式（小型房间广播验证，仅 10/50）:
    python tools/load_test/ws_load_test.py --mode broadcast --connections 10

输出: results/ws_{mode}_{N}_result.json
"""

import argparse
import asyncio
import json
import os
import time
import base64
import hashlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.native_ws.frame import build_frame, parse_frame, OPCODE_TEXT, OPCODE_CLOSE


# ── 系统监控 ────────────────────────────────────────────────────────

def get_server_stats(pid: int) -> dict:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return {"rss_mb": round(int(line.split()[1]) / 1024, 2)}
    except Exception:
        pass
    return {"rss_mb": 0}


def count_established(port: int) -> int:
    import subprocess
    try:
        out = subprocess.check_output(
            ["ss", "-tan"], text=True, stderr=subprocess.DEVNULL
        )
        return sum(1 for line in out.split("\n") if f":{port}" in line and "ESTAB" in line)
    except Exception:
        return 0


def get_cpu_percent(pid: int) -> float:
    import subprocess
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "%cpu", "--no-headers"],
            text=True, stderr=subprocess.DEVNULL
        )
        return float(out.strip())
    except Exception:
        return 0


async def monitor_process(pid: int, port: int, interval: float = 0.5) -> dict:
    """后台采样任务：每 interval 秒采集 RSS/CPU/ESTAB，记录峰值。"""
    peak = {"rss_mb": 0.0, "cpu_pct": 0.0, "established": 0}
    if pid <= 0:
        print("  !! server-pid=0，无法采集资源数据")
        return peak
    try:
        while True:
            rss = get_server_stats(pid).get("rss_mb", 0)
            cpu = get_cpu_percent(pid)
            est = count_established(port)
            if rss > peak["rss_mb"]:
                peak["rss_mb"] = rss
            if cpu > peak["cpu_pct"]:
                peak["cpu_pct"] = cpu
            if est > peak["established"]:
                peak["established"] = est
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
    return peak


# ── 低层 WS 操作 ────────────────────────────────────────────────────

def _mk_msg(mt, mid, **kw):
    m = {"version":"1.0","msg_type":mt,"msg_id":mid,"code":200,
         "content":None,"err_msg":"","timestamp":int(time.time())}
    m.update(kw); return m


async def _ws_handshake(reader, writer, host, port, timeout=15):
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
        raise Exception("not 101")


async def _ws_login(reader, writer, timeout=15):
    t0 = time.time()
    mid = f"login-{os.urandom(3).hex()}"
    writer.write(build_frame(OPCODE_TEXT, json.dumps(
        _mk_msg("login", mid, **{"from":"user001","content":"123456"})
    ).encode(), mask=True)); await writer.drain()

    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        f, n = parse_frame(buf)
        if f:
            buf = buf[n:]
            resp = json.loads(f.payload)
            if resp.get("code") == 200:
                return True, round((time.time() - t0) * 1000, 1), resp
            raise Exception(f"login code={resp.get('code')}")
        chunk = await asyncio.wait_for(reader.read(4096), max(0.1, deadline - time.time()))
        if not chunk: break
        buf += chunk
    raise Exception("login timeout")


async def _ws_create_room(reader, writer, name="test", timeout=15):
    mid = f"cr-{os.urandom(3).hex()}"
    writer.write(build_frame(OPCODE_TEXT, json.dumps(
        _mk_msg("create_room", mid, name=name)
    ).encode(), mask=True)); await writer.drain()

    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        f, n = parse_frame(buf)
        if f:
            buf = buf[n:]
            resp = json.loads(f.payload)
            if resp.get("code") == 200:
                return resp["content"]["conversation_id"]
            raise Exception(f"create_room code={resp.get('code')}")
        chunk = await asyncio.wait_for(reader.read(4096), max(0.1, deadline - time.time()))
        if not chunk: break
        buf += chunk
    raise Exception("create_room timeout")


async def _ws_join_room(reader, writer, room_id, timeout=15):
    mid = f"join-{os.urandom(3).hex()}"
    writer.write(build_frame(OPCODE_TEXT, json.dumps(
        _mk_msg("join_room", mid, conversation_id=room_id)
    ).encode(), mask=True)); await writer.drain()

    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        f, n = parse_frame(buf)
        if f:
            buf = buf[n:]
            resp = json.loads(f.payload)
            if resp.get("code") in (200, 400):  # 400 = already joined
                return
            raise Exception(f"join_room code={resp.get('code')}")
        chunk = await asyncio.wait_for(reader.read(4096), max(0.1, deadline - time.time()))
        if not chunk: break
        buf += chunk
    raise Exception("join_room timeout")


async def _ws_close(writer):
    try:
        writer.write(build_frame(OPCODE_CLOSE, b"\x03\xe8", mask=True))
        writer.close(); await writer.wait_closed()
    except Exception:
        pass


# ── 模式 1：idle - 仅保持连接 ──────────────────────────────────────

async def idle_connect(host, port, idx, timeout=15):
    """仅连接+登录，返回 (result, reader, writer)。"""
    result = {"idx": idx, "connect_ok": False, "login_ok": False,
              "connect_ms": 0, "login_ms": 0, "error": None}
    try:
        t0 = time.time()
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        await _ws_handshake(r, w, host, port, timeout)
        result["connect_ok"] = True
        result["connect_ms"] = round((time.time() - t0) * 1000, 1)
        ok, ms, _ = await _ws_login(r, w, timeout)
        result["login_ok"] = ok
        result["login_ms"] = ms
        return result, r, w
    except asyncio.TimeoutError:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = str(e)[:100]
    return result, None, None


async def idle_hold_and_close(result, w, duration):
    """保持连接 duration 秒后关闭。"""
    if w is not None:
        try:
            await asyncio.sleep(duration)
        except Exception:
            pass
        await _ws_close(w)
    return result


# ── 模式 2：ack_isolated - 每批独立房间验证 ACK ────────────────────

async def ack_isolated_batch(host, port, batch_indices, batch_size, timeout=15):
    """一批客户端：创建独立房间 → 每个人加入 → 每个人发一条 chat → 等 ACK。"""
    clients = []
    # 1. 一个客户端创建房间
    first_r, first_w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    await _ws_handshake(first_r, first_w, host, port, timeout)
    await _ws_login(first_r, first_w, timeout)
    rid = await _ws_create_room(first_r, first_w, f"batch-{batch_indices[0]}", timeout)

    # 2. 其余客户端加入
    readers, writers = [first_r], [first_w]
    for idx in batch_indices[1:]:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        await _ws_handshake(r, w, host, port, timeout)
        await _ws_login(r, w, timeout)
        await _ws_join_room(r, w, rid, timeout)
        readers.append(r); writers.append(w)

    # 3. 每个人发一条 chat，带 need_ack
    msg_ids = {}
    for i, (r, w, idx) in enumerate(zip(readers, writers, batch_indices)):
        mid = f"ack-{idx}"
        msg_ids[idx] = mid
        w.write(build_frame(OPCODE_TEXT, json.dumps(
            _mk_msg("room_chat", mid, conversation_id=rid, payload={"text":f"hello-{idx}"}, need_ack=True)
        ).encode(), mask=True))
    for w in writers:
        await w.drain()

    # 4. 每个人等待自己的 ACK
    results = []
    for i, (r, w, idx) in enumerate(zip(readers, writers, batch_indices)):
        t0 = time.time()
        mid = msg_ids[idx]
        ack_ok = False
        ack_ms = 0
        last_msgs = []
        try:
            buf = b""
            deadline = time.time() + 10
            while time.time() < deadline:
                frame, n = parse_frame(buf)
                if frame is not None:
                    buf = buf[n:]
                    obj = json.loads(frame.payload)
                    last_msgs.append(obj.get("msg_type", "?"))
                    if obj.get("msg_type") == "ack":
                        if obj.get("content", {}).get("original_msg_id") == mid:
                            ack_ok = True; ack_ms = round((time.time() - t0) * 1000, 1)
                            break
                    # 忽略不匹配的 ACK 和 room_chat 广播
                    continue
                chunk = await asyncio.wait_for(r.read(4096), max(0.1, deadline - time.time()))
                if not chunk: break
                buf += chunk
        except Exception as e:
            last_msgs.append(str(e)[:40])

        results.append({
            "idx": idx, "connect_ok": True, "login_ok": True,
            "ack_ok": ack_ok, "ack_rtt_ms": ack_ms,
            "error": None if ack_ok else f"no matching ack, last: {last_msgs[-5:]}",
        })

    # 5. 关闭
    for w in writers:
        await _ws_close(w)

    return results


# ── 模式 3：broadcast - 同房间广播（仅小规模）───────────────────────

async def broadcast_client(host, port, idx, room_id, timeout=15):
    result = {"idx": idx, "connect_ok": False, "login_ok": False,
              "broadcast_received": False, "error": None}
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        await _ws_handshake(r, w, host, port, timeout)
        result["connect_ok"] = True
        await _ws_login(r, w, timeout)
        result["login_ok"] = True
        await _ws_join_room(r, w, room_id, timeout)

        if idx == 1:  # 第一个客户端发消息
            w.write(build_frame(OPCODE_TEXT, json.dumps(
                _mk_msg("room_chat", f"bc-{idx}", conversation_id=room_id,
                        payload={"text":"broadcast-test"}, need_ack=False)
            ).encode(), mask=True)); await w.drain()

        buf = b""
        deadline = time.time() + 10
        while time.time() < deadline:
            frame, n = parse_frame(buf)
            if frame is not None:
                buf = buf[n:]
                obj = json.loads(frame.payload)
                if obj.get("msg_type") == "room_chat" and obj.get("content", {}).get("text") == "broadcast-test":
                    result["broadcast_received"] = True
                    break
                continue
            chunk = await asyncio.wait_for(r.read(4096), max(0.1, deadline - time.time()))
            if not chunk: break
            buf += chunk

        await _ws_close(w)
    except Exception as e:
        result["error"] = str(e)[:100]
    return result


# ── 主函数 ──────────────────────────────────────────────────────────

async def run_idle(host, port, connections, batch_size, duration, server_pid):
    print(f"\n{'='*60}")
    print(f"WebSocket IDLE 模式: {host}:{port}  {connections} 连接  保持 {duration}s")
    print(f"{'='*60}\n")

    rss_before = get_server_stats(server_pid).get("rss_mb", 0)
    est_before = count_established(port)
    t_start = time.time()

    # 启动后台资源采样
    monitor_task = asyncio.create_task(monitor_process(server_pid, port))

    sem = asyncio.Semaphore(batch_size)

    async def _run_idle(idx):
        async with sem:
            res, r, w = await idle_connect(host, port, idx)
        # semaphore 释放后才进入 hold 阶段
        return await idle_hold_and_close(res, w, duration)

    tasks = [asyncio.create_task(_run_idle(i)) for i in range(connections)]

    results = []
    done = 0
    for coro in asyncio.as_completed(tasks):
        r = await coro; results.append(r); done += 1
        if done % 50 == 0 or done == connections:
            elapsed = time.time() - t_start
            ok = sum(1 for x in results if x["connect_ok"])
            print(f"  进度: {done}/{connections}  ({done/elapsed:.0f}/s)  成功: {ok}")

    # 停止采样
    monitor_task.cancel()
    try: await monitor_task
    except asyncio.CancelledError: pass
    peak = monitor_task.result()

    t_end = time.time()

    ok = [r for r in results if r["connect_ok"]]
    login_ok = [r for r in ok if r["login_ok"]]
    errors = [r for r in results if r["error"]]

    summary = {
        "mode": "idle", "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": host, "port": port, "total_connections": connections,
        "connect_success": len(ok), "connect_fail": connections - len(ok),
        "login_success": len(login_ok), "login_fail": len(ok) - len(login_ok),
        "avg_connect_ms": round(sum(r["connect_ms"] for r in ok) / max(len(ok), 1), 1),
        "max_connect_ms": round(max(r["connect_ms"] for r in ok) if ok else 0, 1),
        "errors": len(errors), "error_rate_pct": round(len(errors) / connections * 100, 1),
        "server_rss_mb_before": rss_before, "server_rss_mb_peak": peak["rss_mb"],
        "server_cpu_pct_peak": peak["cpu_pct"],
        "established_connections_peak": peak["established"],
        "established_connections_before": est_before,
        "duration_sec": round(t_end - t_start, 1), "idle_hold_sec": duration,
    }

    _save_and_print("ws_idle", connections, summary, peak["rss_mb"], peak["established"])
    return summary


async def run_ack_isolated(host, port, connections, batch_size, server_pid):
    print(f"\n{'='*60}")
    print(f"WebSocket ACK_ISOLATED 模式: {host}:{port}  {connections} 连接  batch={batch_size}")
    print(f"{'='*60}\n")

    t_start = time.time()
    all_results = []
    for batch_start in range(1, connections + 1, batch_size):
        batch_end = min(batch_start + batch_size, connections + 1)
        batch_indices = list(range(batch_start, batch_end))
        batch_results = await ack_isolated_batch(
            host, port, batch_indices, len(batch_indices))
        all_results.extend(batch_results)
        print(f"  batch {batch_start}-{batch_end-1}: "
              f"ack_ok={sum(1 for r in batch_results if r['ack_ok'])}/{len(batch_results)}")

    t_end = time.time()
    ack_ok = [r for r in all_results if r["ack_ok"]]
    errors = [r for r in all_results if r["error"]]

    summary = {
        "mode": "ack_isolated", "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": host, "port": port, "total_connections": connections,
        "connect_success": len(all_results), "connect_fail": connections - len(all_results),
        "login_success": sum(1 for r in all_results if r["login_ok"]),
        "ack_success": len(ack_ok), "ack_fail": connections - len(ack_ok),
        "avg_ack_rtt_ms": round(sum(r["ack_rtt_ms"] for r in ack_ok) / max(len(ack_ok), 1), 1),
        "max_ack_rtt_ms": round(max(r["ack_rtt_ms"] for r in ack_ok) if ack_ok else 0, 1),
        "errors": len(errors), "error_rate_pct": round(len(errors) / connections * 100, 1),
        "server_rss_mb_before": 0, "server_rss_mb_peak": get_server_stats(server_pid).get("rss_mb", 0),
        "duration_sec": round(t_end - t_start, 1), "batch_size": batch_size,
    }

    _save_and_print("ws_ack", connections, summary)
    return summary


async def run_broadcast(host, port, connections, server_pid):
    print(f"\n{'='*60}")
    print(f"WebSocket BROADCAST 模式: {host}:{port}  {connections} 连接（小规模）")
    print(f"{'='*60}\n")

    # 创建一间共享房间
    cr, cw = await asyncio.open_connection(host, port)
    await _ws_handshake(cr, cw, host, port)
    await _ws_login(cr, cw)
    room_id = await _ws_create_room(cr, cw, "broadcast-room")
    await _ws_close(cw)
    print(f"  房间: {room_id}\n")

    tasks = [asyncio.create_task(broadcast_client(host, port, i, room_id))
             for i in range(1, connections + 1)]
    results = await asyncio.gather(*tasks)

    ok = [r for r in results if r["connect_ok"]]
    bc = [r for r in results if r["broadcast_received"]]

    summary = {
        "mode": "broadcast", "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": host, "port": port, "total_connections": connections,
        "connect_success": len(ok), "broadcast_received": len(bc),
        "error_rate_pct": round((connections - len(bc)) / connections * 100, 1),
    }

    _save_and_print("ws_broadcast", connections, summary)
    return summary


def _save_and_print(prefix, connections, summary, rss_peak=0, est_peak=0):
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"{prefix}_{connections}_result.json")
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  结果: {out_file}")
    for k, v in summary.items():
        if k not in ("test_time", "host", "port", "mode"):
            print(f"  {k}: {v}")
    if summary.get("error_rate_pct", 0) > 10:
        print("  !! 错误率超过 10%")
    print()


def main():
    parser = argparse.ArgumentParser(description="WebSocket 并发压测")
    parser.add_argument("--mode", default="broadcast",
                        choices=["idle", "ack_isolated", "broadcast"],
                        help="idle=仅连接 | ack_isolated=独立房间ACK | broadcast=同房间广播")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--connections", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--server-pid", type=int, default=0)
    args = parser.parse_args()

    if args.mode == "idle":
        asyncio.run(run_idle(args.host, args.port, args.connections,
                             args.batch_size, args.duration, args.server_pid))
    elif args.mode == "ack_isolated":
        asyncio.run(run_ack_isolated(args.host, args.port, args.connections,
                                     args.batch_size, args.server_pid))
    else:
        asyncio.run(run_broadcast(args.host, args.port, args.connections,
                                  args.server_pid))


if __name__ == "__main__":
    main()
