# 基于 WebSocket 的分布式实时聊天系统 — 课程报告

> **题目 15 增强版 | 2026 年 6 月 | 73 次提交 | 约 8,500 行源代码**

---

## 一、项目概述

本项目实现了完整的分布式实时聊天系统，支持群聊、私聊、JWT 认证、ACK 确认、离线消息、多节点消息转发，并通过手写 RFC 6455 协议层和 1000 并发压测验证网络系统性能。

**技术栈**：Python (asyncio) + Redis + 原生 JavaScript（无框架）

---

## 二、功能需求对照

| # | 需求 | 状态 | 实现说明 |
|---|---|---|---|
| 1 | 用户注册/登录（JWT 认证） | ✅ 完成 | `backend/handlers/register.py`, `login.py`，PBKDF2-SHA256 密码哈希，JWT HS256 签名，1 小时有效期，支持 token 刷新 |
| 2 | 创建/加入聊天室（多房间） | ✅ 完成 | `handlers/room.py`，支持创建、加入、退出、查看成员、房间列表浏览 |
| 3 | 实时消息广播（聊天室内） | ✅ 完成 | `core/local_delivery_service.py`，遍历参与者并在线直投 |
| 4 | 私聊（点对点） | ✅ 完成 | `handlers/private_chat.py`，基于持久化会话 ID，支持历史会话列表 |
| 5 | 在线用户列表（心跳维护） | ✅ 完成 | `core/online_presence_service.py`，Redis 存储在线状态，TTL 15 秒，每 5 秒续约；WebSocket 传输层 Ping/Pong 每 5 秒 |
| 6 | 消息 ACK 机制 | ✅ 完成 | `core/protocol.py` `send_ack()`，客户端可选 `need_ack`，服务端返回 ACK + RTT |
| 7 | 消息 ID 去重 | ✅ 完成 | `core/dedupe_service.py`，双层去重（消息级 + 节点投递级），TTL 10 分钟 |
| 8 | 离线消息 Redis 缓存（7 天） | ✅ 完成 | `core/offline_message_service.py`，Redis List 存储，TTL 7 天；补发成功才清除，失败保留 |
| 9 | 消息已读回执 | ❌ 未实现 | — |
| 10 | 输入状态提示 | ❌ 未实现 | — |

**完成度：8/10 必选，0/2 可选**

---

## 三、网络技术要求对照

| # | 需求 | 状态 | 实现说明 |
|---|---|---|---|
| 1 | WebSocket 握手（HTTP Upgrade） | ✅ 完成 | `native_ws/handshake.py`（274 行），完整实现 RFC 6455 Section 4：Header 解析、Key 校验、Accept 计算、101 响应 |
| 2 | 帧解析（文本/二进制/关闭/Ping/Pong） | ✅ 完成 | `native_ws/frame.py`（327 行），完整实现 RFC 6455 Section 5：FIN/RSV/Opcode 解析、mask/unmask、扩展载荷长度（7bit/16bit/64bit） |
| 3 | 应用层协议（JSON） | ✅ 完成 | `core/protocol.py`（约 200 行），字段：`version`, `msg_type`, `msg_id`, `code`, `content`, `err_msg`, `timestamp` |
| 4 | Redis Pub/Sub 多服务器广播 | ✅ 完成 | `core/pubsub_service.py`（116 行），独立线程监听 `chat:messages` 频道，按节点 ID 去重转发 |
| 5 | WebSocket vs HTTP 长轮询对比测试 | ✅ 完成 | `tools/load_test/` 下三套压测（WebSocket / Long Polling / SSE），各支持 1000 并发 |

---

## 四、系统架构

### 4.1 模块结构

```
backend/
├── main.py                          # 主服务入口（端口 8765）
├── config.py                        # 环境变量配置
├── core/
│   ├── connection.py                # 连接生命周期：认证 → 心跳 → 消息循环 → 清理
│   ├── protocol.py                  # 应用层协议：build/parse/validate/send
│   ├── auth.py                      # JWT：生成/验证/过期检查
│   ├── state.py                     # 全局状态：connections dict, ConnectionContext
│   ├── user_store.py                # 用户持久化：PBKDF2 + JSON 文件
│   ├── conversation_service.py      # 会话逻辑：群聊 CRUD、私聊索引
│   ├── conversation_store.py        # 会话 Redis 存储
│   ├── local_delivery_service.py    # 消息投递：在线直投 + 离线写 Redis
│   ├── offline_message_service.py   # 离线消息 Redis 读写
│   ├── offline_delivery_service.py  # 离线补发：登录后逐条推送
│   ├── online_presence_service.py   # 在线状态：设置 + 续约任务
│   ├── online_registry_service.py   # 在线状态 Redis 操作
│   ├── dedupe_service.py            # 消息去重
│   ├── pubsub_service.py            # Redis Pub/Sub 跨节点转发
│   ├── message_store.py             # 永久消息存储（聊天历史）
│   ├── redis_client.py              # Redis 连接实例
│   └── redis_health.py              # 启动健康检查
├── handlers/
│   ├── login.py, register.py        # 登录/注册
│   ├── room.py                      # 群聊：创建/加入/退出/成员/消息/列表/历史
│   ├── private_chat.py              # 私聊：创建会话/发送/会话列表
│   ├── heartbeat.py                 # 应用层心跳
│   ├── user_list.py                 # 在线用户列表（本地 + Redis 合并）
│   └── token.py                     # Token 刷新
├── native_ws/
│   ├── handshake.py                 # HTTP Upgrade 握手
│   ├── frame.py                     # RFC 6455 帧读写
│   ├── connection.py                # 手写帧 WebSocket 连接封装
│   ├── server.py                    # Echo 验证服务（8766）
│   └── chat_server.py               # 聊天服务（8768，复用全部 handler）
└── utils/logger.py                  # 日志
```

### 4.2 Redis 数据结构

| Key | 类型 | 用途 | TTL |
|---|---|---|---|
| `chat:conversation:{id}` | String | 会话元数据 | 无 |
| `chat:private_index:{a}:{b}` | String | 私聊索引 | 无 |
| `chat:online:user:{user_id}` | String | 在线状态（value=节点ID） | 15s（5s 续约） |
| `chat:offline_messages:{user_id}` | List | 离线消息队列 | 7 天 |
| `chat:messages:{conversation_id}` | List | 永久聊天历史 | 无 |
| `chat:dedupe:message:{sender}:{msg_id}` | String | 消息级去重 | 10min |
| `chat:dedupe:node_delivery:{node}:{sender}:{msg_id}` | String | 节点投递去重 | 10min |
| `chat:messages` | Pub/Sub | 跨节点消息转发 | — |

### 4.3 消息流转

```
浏览器 A 发送 {"msg_type":"room_chat","payload":{"text":"hello"},...}
  ↓ TCP
主服务 (ws 库 / 手写帧) 接收 raw text
  ↓
parse_protocol() → JSON
  ↓
validate_protocol() → 字段校验
  ↓
dispatch_message() → handle_room_chat()
  ├─ has_processed_message()          去重检查
  ├─ get_conversation()                验证会话 + 参与者
  ├─ deliver_room_message_locally()
  │   ├─ 在线 → send_json() 直投
  │   └─ 离线 → store_offline_message() → Redis LPUSH
  ├─ save_message()                    永久历史 → Redis LPUSH
  ├─ publish_distributed_message()     Redis Pub/Sub → 其他节点
  └─ mark_message_processed()          标记已处理
```

---

## 五、关键技术实现

### 5.1 WebSocket 手写协议层（RFC 6455）

架构上采用**协议层与应用层分离**设计：

| 端口 | 协议层 | 应用层 | 用途 |
|---|---|---|---|
| 8765 | `websockets` 库 | 全功能聊天 | 浏览器前端 |
| 8766 | 手写 `native_ws/` | Echo 验证 | 协议层自检 |
| 8768 | 手写 `native_ws/` | 全功能聊天 | 协议层验证 + 压测 |

手写协议层包括：

- **握手**（`handshake.py`）：解析 HTTP Upgrade 请求头 → 校验 WebSocket 握手条件 → SHA1 + GUID → Base64 计算 Accept → 返回 101。含 8 组自检用例覆盖 RFC 6455 官方示例。
- **帧解析**（`frame.py`）：支持 7/16/64 位载荷长度、客户端 mask/unmask、全部 Opcode（text/binary/close/ping/pong/continuation）。含 11 组自检用例。
- **连接封装**（`connection.py`）：在 asyncio TCP stream 上实现 `send_text()`、`recv_text()`、`send_ping()`、`send_pong()`、`close()`、`__aiter__` 异步迭代器，接口兼容 `websockets` 库。

### 5.2 消息可靠性

三层保障：

1. **ACK 机制**：客户端在消息中设 `need_ack: true`，服务端处理完毕后返回 `{"msg_type":"ack", "content":{"original_msg_id":"...","status":"processed"}}`。客户端记录 RTT。
2. **消息去重**：服务端对每个 `(sender_id, msg_id)` 记录 Redis key，相同 ID 拒绝重复处理，返回 `status: "duplicate"`。
3. **离线消息**：目标用户不在线时，消息写入 Redis List。用户上线后逐条补发，**全部发送成功才清除**，防止中途断连导致消息丢失。

### 5.3 多节点扩展

通过 Redis Pub/Sub 实现水平扩展：

```
Node A                      Redis                     Node B
  │                           │                         │
  ├─ handle_room_chat()       │                         │
  ├─ deliver_local()          │                         │
  ├─ publish(channel, msg) ──→│──→ pubsub_worker        │
  │                           │      ├─ handle_distributed_message()
  │                           │      ├─ has_node_delivery_processed()
  │                           │      └─ deliver_online_only_locally()
  └─ mark_processed()         │                         │
```

`source_node_id` 去重确保消息不会在源节点重复投递。

### 5.4 并发压测

三套独立的压测工具，均支持 1000 并发：

| 测试 | 文件 | 说明 |
|---|---|---|
| WebSocket idle | `ws_load_test.py` | 手写帧直连，支持 idle/ack_isolated/broadcast 三种模式 |
| Long Polling | `long_poll_load_test.py` + `long_poll_server.py` | HTTP 长轮询，25s 超时 |
| SSE | `sse_load_test.py` + `sse_test_server.py` | Server-Sent Events 推送流 |

采集指标：连接成功率、内存峰值（RSS）、ESTAB 连接数、CPU 占用。

---

## 六、协议文档

### 6.1 通用格式

```json
{
  "version": "1.0",
  "msg_type": "<消息类型>",
  "msg_id": "<UUID>",
  "code": 200,
  "content": {},
  "err_msg": "",
  "timestamp": 1718123456
}
```

### 6.2 消息类型一览

| msg_type | 方向 | content 字段 | 说明 |
|---|---|---|---|
| `register` | C→S | `{password}` | 注册 |
| `login` | C→S | `"password"` (纯字符串) | 登录 |
| `login` | S→C | `{token, expires_at}` | 登录响应 |
| `heartbeat` | C→S | — | 应用层心跳 |
| `create_room` | C→S | `name` | 创建群聊 |
| `room_created` | S→C | `{conversation_id, name, owner, participants}` | 创建成功 |
| `join_room` | C→S | `conversation_id` | 加入群聊 |
| `room_joined` | S→C | `{conversation_id, name, user_id}` | 加入成功 |
| `leave_room` | C→S | `conversation_id` | 退出群聊 |
| `room_chat` | C→S | `{conversation_id, payload: {text}, need_ack}` | 发送群聊消息 |
| `room_chat` | S→C | `{conversation_id, from_user_id, text}` | 接收群聊消息 |
| `list_rooms` | C→S | — | 请求房间列表 |
| `room_list` | S→C | `{rooms: [{conversation_id, name, participant_count, owner}]}` | 房间列表 |
| `create_private_conversation` | C→S | `target_user_id` | 创建私聊会话 |
| `private_conversation_created` | S→C | `{conversation_id, participants}` | 创建成功 |
| `private_chat` | C→S | `{conversation_id, payload: {text}, need_ack}` | 发送私聊 |
| `private_chat` | S→C | `{conversation_id, from_user_id, to_user_id, text}` | 接收私聊 |
| `list_my_conversations` | C→S | — | 请求会话列表 |
| `my_conversations` | S→C | `{conversations: [...]}` | 会话列表 |
| `get_chat_history` | C→S | `conversation_id` | 拉取历史消息 |
| `chat_history` | S→C | `{conversation_id, messages: [...]}` | 历史消息 |
| `get_online_users` | C→S | — | 请求在线用户 |
| `online_users` | S→C | `["user1", "user2"]` | 在线用户列表 |
| `refresh_token` | C→S | — | 刷新 JWT |
| `ack` | S→C | `{original_msg_id, status}` | ACK 确认 |
| `error` | S→C | — + `err_msg` + `code` | 错误响应 |

---

## 七、已知限制与后续改进

### 7.1 架构层面

- **协议层双轨**：主服务使用 `websockets` 库，手写帧仅在 8766/8768 侧端口运行。手写帧层已完成与全部 handler 的集成（`chat_server.py`），替换主服务协议层需补齐心跳机制等 9 处修改（方案已评估）。

### 7.2 功能层面

- 无自动重连（前端未实现指数退避重连）
- 无消息已读回执和输入状态提示
- `redis_client.keys()` 在 2 处使用，大量 key 时建议改用 SCAN（已完成一处修复）
- 在线状态续约和去重操作的 GET+SET 分两步执行，极端并发下存在理论竞态窗口

### 7.3 安全性

- `JWT_SECRET` 使用开发默认值，部署前应改为环境变量
- PBKDF2 100,000 次迭代，HMAC-SHA256 密钥 18 字节，低于 RFC 7518 建议的 32 字节
- 无消息频率限制和内容过滤

---

## 八、代码统计

| 模块 | 行数 | 占比 |
|---|---|---|
| 后端核心 (`backend/core/`) | ~1,700 | 20% |
| 后端 Handler (`backend/handlers/`) | ~550 | 7% |
| 手写协议层 (`backend/native_ws/`) | ~1,170 | 14% |
| 前端 (`frontend/demo/`) | ~3,580 | 42% |
| 压测工具 (`tools/`) | ~1,140 | 13% |
| 配置/工具 | ~320 | 4% |
| **合计** | **~8,460** | **100%** |

---

## 九、参考文献

1. RFC 6455 — The WebSocket Protocol (2011)
2. RFC 7518 — JSON Web Algorithms (JWA)
3. RFC 7519 — JSON Web Token (JWT)
4. Redis Pub/Sub Documentation — https://redis.io/docs/latest/develop/interact/pubsub/
5. Python websockets Library — https://websockets.readthedocs.io/
6. Asyncio — Python Standard Library — https://docs.python.org/3/library/asyncio.html
7. HTTP Long Polling vs WebSocket — MDN Web Docs
8. Server-Sent Events (SSE) — MDN Web Docs
9. PBKDF2 Password Hashing — NIST SP 800-132
10. Distributed Message Broadcasting with Redis — Redis Labs
