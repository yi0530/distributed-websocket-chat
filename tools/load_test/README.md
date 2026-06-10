# 压力测试工具

用于计算机网络大作业的 WebSocket 并发连接压力测试和 WebSocket vs SSE 对比。

## 文件说明

| 文件 | 用途 |
|------|------|
| `ws_load_test.py` | WebSocket 1000 并发压测客户端 |
| `sse_test_server.py` | 最小 SSE 服务（对比用） |
| `sse_load_test.py` | SSE 长连接压测客户端 |
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
