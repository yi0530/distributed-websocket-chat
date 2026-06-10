"""
HTTP 长轮询（Long Polling）压力测试。

启动 N 个虚拟客户端，每个客户端循环执行：
  建立 TCP → GET /poll?client_id=i → 等待响应 → 收到后立即下一轮
在 duration 秒内持续维持 N 个"正在等待响应的长轮询客户端"。

用法:
  python tools/load_test/long_poll_load_test.py --host 127.0.0.1 --port 8771 --connections 100 --duration 30

输出:
  results/long_poll_{N}_result.json
"""

import argparse
import asyncio
import json
import os
import time
import subprocess
import sys


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


async def monitor_process(pid: int, port: int, interval: float = 0.5) -> dict:
    """后台采样：每 interval 秒采集 RSS/CPU/ESTAB，记录峰值。"""
    peak = {"rss_mb": 0.0, "cpu_pct": 0.0, "established": 0}
    if pid <= 0:
        print("  !! server-pid=0，无法采集资源数据")
        return peak
    try:
        while True:
            rss = get_server_stats(pid).get("rss_mb", 0)
            cpu = get_cpu_percent(pid)
            est = count_established(port)
            if rss > peak["rss_mb"]: peak["rss_mb"] = rss
            if cpu > peak["cpu_pct"]: peak["cpu_pct"] = cpu
            if est > peak["established"]: peak["established"] = est
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
    return peak


async def poll_client(host: str, port: int, idx: int, duration: float) -> dict:
    """一个长轮询客户端：持续发送 /poll 请求直到 duration 结束。"""
    result = {
        "idx": idx,
        "polls": 0, "poll_success": 0, "poll_fail": 0,
        "latencies": [], "errors": [],
    }
    deadline = time.time() + duration

    while time.time() < deadline:
        try:
            t0 = time.time()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10
            )

            req = f"GET /poll?client_id={idx} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n"
            writer.write(req.encode()); await writer.drain()

            data = b""
            while b"\r\n\r\n" not in data:
                chunk = await asyncio.wait_for(
                    reader.read(4096), timeout=30
                )
                if not chunk: break
                data += chunk

            # 读取 body
            if b"Content-Length:" in data:
                cl_start = data.index(b"Content-Length:") + 15
                cl_end = data.index(b"\r\n", cl_start)
                content_length = int(data[cl_start:cl_end])
                body = data[data.index(b"\r\n\r\n") + 4:]
                while len(body) < content_length:
                    chunk = await asyncio.wait_for(reader.read(content_length - len(body)), timeout=5)
                    if not chunk: break
                    body += chunk

            writer.close()
            await writer.wait_closed()

            result["polls"] += 1
            result["poll_success"] += 1
            result["latencies"].append(round((time.time() - t0) * 1000, 1))

        except asyncio.TimeoutError:
            result["poll_fail"] += 1
            result["errors"].append("timeout")
        except Exception as e:
            result["poll_fail"] += 1
            result["errors"].append(str(e)[:80])

    return result


async def run_long_poll_test(host: str, port: int, connections: int,
                             duration: float = 30.0, server_pid: int = 0):
    print(f"\n{'='*60}")
    print(f"HTTP Long Polling 压测: {host}:{port}  {connections} 连接  持续 {duration}s")
    print(f"{'='*60}\n")

    rss_before = get_server_stats(server_pid).get("rss_mb", 0)
    est_before = count_established(port)
    t_start = time.time()

    # 启动后台资源采样
    monitor_task = asyncio.create_task(monitor_process(server_pid, port))

    tasks = [asyncio.create_task(poll_client(host, port, i, duration))
             for i in range(connections)]

    results = await asyncio.gather(*tasks)

    # 停止采样
    monitor_task.cancel()
    try: await monitor_task
    except asyncio.CancelledError: pass
    peak = monitor_task.result()

    t_end = time.time()

    total_polls = sum(r["polls"] for r in results)
    success = sum(r["poll_success"] for r in results)
    fail = sum(r["poll_fail"] for r in results)
    all_latencies = [l for r in results for l in r["latencies"]]
    all_errors = [e for r in results for e in r["errors"]]

    summary = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": host, "port": port,
        "total_clients": connections,
        "total_poll_requests": total_polls,
        "poll_success": success,
        "poll_fail": fail,
        "avg_poll_latency_ms": round(sum(all_latencies) / max(len(all_latencies), 1), 1),
        "max_poll_latency_ms": round(max(all_latencies) if all_latencies else 0, 1),
        "errors": len(all_errors),
        "error_rate_pct": round(fail / max(total_polls, 1) * 100, 1),
        "server_rss_mb_before": rss_before,
        "server_rss_mb_peak": peak["rss_mb"],
        "server_cpu_pct_peak": peak["cpu_pct"],
        "established_connections_peak": peak["established"],
        "established_connections_before": est_before,
        "duration_sec": round(t_end - t_start, 1),
    }

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"long_poll_{connections}_result.json")
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  结果已保存: {out_file}")
    print(f"  客户端数: {connections}")
    print(f"  总轮询次数: {total_polls}  成功: {success}  失败: {fail}")
    print(f"  平均轮询延迟: {summary['avg_poll_latency_ms']}ms  最大: {summary['max_poll_latency_ms']}ms")
    print(f"  服务器内存: {rss_before}MB → 峰值 {peak['rss_mb']}MB")
    print(f"  ESTAB 连接: {est_before} → 峰值 {peak['established']}")
    if summary["error_rate_pct"] > 10:
        print("  !! 错误率超过 10%，建议停止更高规模测试\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description="HTTP Long Polling 压测")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8771)
    parser.add_argument("--connections", type=int, default=100)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--server-pid", type=int, default=0)
    args = parser.parse_args()

    asyncio.run(run_long_poll_test(
        args.host, args.port, args.connections,
        duration=args.duration, server_pid=args.server_pid
    ))


if __name__ == "__main__":
    main()
