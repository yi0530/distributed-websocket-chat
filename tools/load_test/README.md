# 压力测试工具

用于计算机网络大作业的 WebSocket vs HTTP Long Polling vs SSE 并发连接
内存占用对比测试。

## 三种对照方案

| 方案 | 协议 | 方向 | 连接生命周期 |
|------|------|------|-------------|
| **WebSocket** | ws:// (RFC6455) | 双向 | TCP 长连接，持续保持 |
| **HTTP Long Polling** | http:// | 双向模拟 | 每次 /poll 挂起→超时→重连 |
| **SSE** | http:// (text/event-stream) | 单向推送 | TCP 长连接，持续保持 |

报告优先对比 WebSocket vs HTTP Long Polling，SSE 作为补充对照。

## 文件说明

| 文件 | 用途 |
|------|------|
| `ws_load_test.py` | WebSocket 1000 并发压测客户端 |
| `sse_test_server.py` | 最小 SSE 服务（补充对照） |
| `sse_load_test.py` | SSE 长连接压测客户端 |
| `long_poll_server.py` | HTTP Long Polling 服务（主对照） |
| `long_poll_load_test.py` | Long Polling 压测客户端 |
| `results/` | 压测结果输出目录 |

## 使用顺序

1. 启动被测试服务
2. 运行压测脚本（从小到大递增规模）
3. 查看 results/ 下的 JSON 结果
4. 生成 load_test_summary.md

## 环境要求

- Python 3.10+
- 无第三方依赖（仅标准库）

## 注意

- 优先在本地或测试环境运行
- 不要对生产服务器执行大规模压测
- 如果错误率超过 10%，立即停止
