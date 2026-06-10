"""
SSE 长连接压力测试。

建立 N 个 HTTP SSE 长连接，保持 30 秒，记录服务器内存占用变化。
用于与 WebSocket 对比：在相同连接数下的 RSS 内存对比。

用法:
  python tools/load_test/sse_load_test.py --host 127.0.0.1 --port 8770 --connections 100

输出:
  控制台实时进度 + results/sse_{N}_result.json
"""

import argparse
import asyncio
import json
import os
import time
import sys
import subprocess

# ── 工具函数 ──────────────────────────────────────────────────────


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
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "%cpu", "--no-headers"],
            text=True, stderr=subprocess.DEVNULL
        )
        return float(out.strip())
    except Exception:
        return 0


# ── SSE 客户端 ────────────────────────────────────────────────────


async def sse_client(host: str, port: int, idx: int, hold_sec: float = 30.0) -> dict:
    """建立一个 SSE 长连接，保持 hold_sec 秒。"""
    result = {"idx": idx, "connect_ok": False, "connect_ms": 0, "error": None}
    try:
        t0 = time.time()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=10
        )
        req = f"GET /events HTTP/1.1\r\nHost: {host}:{port}\r\nAccept: text/event-stream\r\nConnection: keep-alive\r\n\r\n"
        writer.write(req.encode()); await writer.drain()

        # 等待 200 响应
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=10)
            if not chunk: raise Exception("no response")
            data += chunk
        if b"200" not in data:
            raise Exception(f"not 200: {data.split(b'\\r\\n')[0]!r}")

        result["connect_ok"] = True
        result["connect_ms"] = round((time.time() - t0) * 1000, 1)

        # 保持连接 hold_sec 秒
        await asyncio.sleep(hold_sec)

        writer.close()
        await writer.wait_closed()

    except asyncio.TimeoutError:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = str(e)[:100]

    return result


# ── 主函数 ────────────────────────────────────────────────────────


async def run_sse_test(host: str, port: int, connections: int,
                       batch_size: int = 50, hold_sec: float = 30.0,
                       server_pid: int = 0):
    print(f"\n{'='*60}")
    print(f"SSE 长连接压测: {host}:{port}  {connections} 连接  保持 {hold_sec}s")
    print(f"{'='*60}\n")

    rss_before = get_server_stats(server_pid).get("rss_mb", 0)
    est_before = count_established(port)
    t_start = time.time()

    sem = asyncio.Semaphore(batch_size)
    tasks = []

    async def one_client(idx: int):
        async with sem:
            return await sse_client(host, port, idx, hold_sec)

    for i in range(connections):
        tasks.append(asyncio.create_task(one_client(i)))

    results = []
    done_count = 0
    for coro in asyncio.as_completed(tasks):
        r = await coro
        results.append(r)
        done_count += 1
        if done_count % 50 == 0 or done_count == connections:
            elapsed = time.time() - t_start
            ok = sum(1 for x in results if x["connect_ok"])
            print(f"  进度: {done_count}/{connections}  "
                  f"({done_count/elapsed:.0f} 连接/秒)  成功: {ok}")

    # 等完所有连接后再等 hold_sec
    await asyncio.sleep(hold_sec)

    t_end = time.time()
    rss_peak = get_server_stats(server_pid).get("rss_mb", 0)
    est_peak = count_established(port)
    cpu_peak = get_cpu_percent(server_pid)

    ok = [r for r in results if r["connect_ok"]]
    errors = [r for r in results if r["error"]]

    summary = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": host, "port": port,
        "total_connections": connections,
        "connect_success": len(ok),
        "connect_fail": connections - len(ok),
        "avg_connect_ms": round(sum(r["connect_ms"] for r in ok) / max(len(ok), 1), 1),
        "max_connect_ms": round(max(r["connect_ms"] for r in ok) if ok else 0, 1),
        "errors": len(errors),
        "error_rate_pct": round(len(errors) / connections * 100, 1),
        "server_rss_mb_before": rss_before,
        "server_rss_mb_peak": rss_peak,
        "server_cpu_pct_peak": cpu_peak,
        "established_connections_peak": est_peak,
        "established_connections_before": est_before,
        "hold_sec": hold_sec,
        "duration_sec": round(t_end - t_start, 1),
    }

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"sse_{connections}_result.json")
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  结果已保存: {out_file}")
    print(f"  连接成功: {summary['connect_success']}/{connections}")
    print(f"  平均连接耗时: {summary['avg_connect_ms']}ms  最大: {summary['max_connect_ms']}ms")
    print(f"  服务器内存: {rss_before}MB → 峰值 {rss_peak}MB")
    print(f"  ESTAB 连接: {est_before} → 峰值 {est_peak}\n")

    if summary["error_rate_pct"] > 10:
        print("  ⚠ 错误率超过 10%，建议停止更高规模测试")

    return summary


def main():
    parser = argparse.ArgumentParser(description="SSE 长连接压测")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--connections", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--hold-sec", type=float, default=30.0)
    parser.add_argument("--server-pid", type=int, default=0)
    args = parser.parse_args()

    asyncio.run(run_sse_test(
        args.host, args.port, args.connections,
        batch_size=args.batch_size, hold_sec=args.hold_sec,
        server_pid=args.server_pid
    ))


if __name__ == "__main__":
    main()
