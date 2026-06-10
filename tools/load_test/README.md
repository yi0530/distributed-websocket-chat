# 压力测试工具

用于计算机网络大作业的 WebSocket vs HTTP Long Polling vs SSE 并发连接
内存占用对比测试。

## 三种对照方案

| 方案 | 协议 | 方向 | 连接生命周期 |
|------|------|------|-------------|
| **WebSocket** | ws:// (RFC6455) | 双向 | TCP 长连接，持续保持 |
| **HTTP Long Polling** | http:// | 双向模拟 | 每次 /poll 挂起→超时→重连 |
| **SSE** | http:// (text/event-stream) | 单向推送 | TCP 长连接，持续保持 |

正式报告优先对比 **WebSocket vs HTTP Long Polling**，SSE 作为补充对照。

## WebSocket 压测模式

| 模式 | 用途 | 规模 | 说明 |
|------|------|------|------|
| `idle` | **1000 并发内存主对比** | 100-1000 | connect→login→保持连接，不发送聊天 |
| `ack_isolated` | ACK 功能验证 | 100-500 | 每批独立房间，验证 msg_id 匹配的 ACK |
| `broadcast` | 房间广播验证 | 仅 10/50 | 同房间广播，验证消息送达 |

### 用法

```bash
# 1000 并发内存测试（主对照）
python tools/load_test/ws_load_test.py --mode idle --connections 1000 --duration 30

# ACK 功能验证
python tools/load_test/ws_load_test.py --mode ack_isolated --connections 100 --batch-size 5

# 小型广播验证
python tools/load_test/ws_load_test.py --mode broadcast --connections 10
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `ws_load_test.py` | WebSocket 压测（支持 idle/ack_isolated/broadcast 三模式） |
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
- Linux 服务器（/proc 资源监控）

## 资源监控

正式压测必须传入服务 PID 以获得有效 RSS/CPU/ESTABLISHED 峰值数据：

```bash
# 获取服务 PID
ps aux | grep -E 'chat_server|long_poll_server'

# 带资源监控的压测
python tools/load_test/ws_load_test.py --mode idle --connections 100 \
  --server-pid <PID> --duration 30

python tools/load_test/long_poll_load_test.py --connections 100 \
  --server-pid <PID> --duration 30
```

* 测试期间每 0.5 秒采样一次，记录 RSS/CPU/ESTABLISHED 峰值
* 不传 --server-pid 时资源指标为 0，不得写入报告

## 注意

- 优先在本地或测试环境运行
- 不要对生产服务器执行大规模压测
- 如果错误率超过 10%，立即停止