# 当前任务

> 本文件记录当前正在进行的任务。
> 任务完成后，将内容归档到 `task-log.md`，然后将本文件重置为"无活跃任务"状态。

---

## 任务标题

诊断同一网页窗口切换账号后的状态污染问题

## 状态

`planning` — 分析完成，等待用户确认修复方案

状态流转：`idle` → `planning` → `implementing` → `reviewing` → `done` → 归档后重置为 `idle`

## 背景

当前调试页在同一窗口中同时运行客户端 A 和客户端 B。用户在以下场景中发现问题：

1. A 以 user001 登录，创建群聊/私聊
2. A 断开连接
3. 不刷新页面，A 改为 user003 登录
4. user003 发送消息时使用 user001 的旧 conversation_id
5. 后端 participants 校验拒绝，但因前端错误提示不够明确，表现混乱

同时后端存在重复 login 静默覆盖身份、login 后不补发离线消息等问题。

## 目标

1. 精确定位前端 conversation_id 污染根因
2. 精确定位后端身份覆盖根因
3. 精确定位离线消息补发时机问题
4. 输出分级修复方案

## 非目标

- 不手写 RFC6455
- 不改 WebSocket 框架
- 不新增注册系统
- 不重构项目
- 不修改协议字段
- 不改 Redis key 前缀
- 不删除 ACK/去重/离线消息/认证

## 涉及文件

**已分析文件（只读）：**
- `frontend/index.html` — 前端调试页
- `backend/core/connection.py` — WebSocket 连接生命周期
- `backend/handlers/login.py` — 登录处理
- `backend/core/state.py` — ConnectionContext / connections
- `backend/core/online_presence_service.py` — 在线状态续约
- `backend/core/online_registry_service.py` — Redis 在线状态读写
- `backend/core/offline_message_service.py` — 离线消息存储
- `backend/core/conversation_service.py` — 会话业务逻辑
- `backend/core/conversation_store.py` — 会话 Redis 存储
- `backend/handlers/room.py` — 群聊处理
- `backend/handlers/private_chat.py` — 私聊处理

## 风险等级

**黄区** — 涉及前端状态结构变更、后端连接身份生命周期变更、离线消息补发时机变更、多文件联动修改。

## 约束

- 不修改 `CLAUDE.md`
- 不引入大型新依赖
- 不删除认证/ACK/去重/权限校验
- 修改前按 `task-boundary.md` 输出声明
- 修改后按 `task-boundary.md` 输出复盘

## 执行计划

1. ✅ 读取所有相关文件（已完成）
2. ✅ 输出诊断报告（已完成，见下方分析）
3. ⬜ 等待用户确认修复方案
4. ⬜ 按确认的方案执行修改

## 完成标准

- 前端 conversation_id 按客户端隔离，切换账号后旧 ID 被清理
- 后端已认证连接重复 login 被明确拒绝
- 匿名连接 login 后触发离线消息补发
- 15 个测试场景全部通过

## 测试要求

至少覆盖：
1. A 登录 user001 → 创建群聊 → 断开 → 不刷新页面换 user003 登录 → user003 不继续使用 user001 的旧 conversation_id
2. 同上场景，user003 收到明确错误提示
3. A/B 两个客户端分别登录不同用户，token 和 conversation_id 互不污染
4. 已认证连接再次 login 返回错误
5. B 离线 → A 给 B 发私聊 → B 用匿名连接 + login（非 token 重连）→ B 收到离线消息

## 用户确认记录

_（待记录）_
