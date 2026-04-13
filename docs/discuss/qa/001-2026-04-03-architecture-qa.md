# QA #001 — 架构设计问题

> 日期：2026-04-03
> 背景：阅读 docs/discuss/introduce/ 后产生的问题

---

## Q1: 历史消息怎么办？

**A**: 当前没有历史消息持久化。IRC 本身不存消息，agent 断线重连后看不到之前的对话。

ergo 配置中有 `chathistory=1000`（支持 IRCv3 CHATHISTORY 扩展），但 channel-server 没有实现 CHATHISTORY 协议的客户端请求，所以这个能力没用上。

实际影响：
- Agent 重启后丢失频道上下文
- 当前靠 Claude Code 的 `/resume` 保留 agent 侧的对话记忆，但频道里其他人说的就丢了
- 如果要做 evolver 数据收集，需要在 channel-server 或服务器侧加消息持久化

> 引用：ergo 配置 `CHATHISTORY=1000`（WeeChat 连接时可见）；channel-server 无 CHATHISTORY 实现

---

## Q2: `__zchat_sys:` 消息的用途是什么？跟 Claude SDK 输出有关吗？

**A**: 无关。`__zchat_sys:` 是 **agent 之间 / CLI 与 agent 之间的控制通信协议**，走普通 IRC PRIVMSG，跟 Claude SDK 完全无关。

用途是机器间控制（不给人看的）：

```
zchat CLI → IRC PRIVMSG → __zchat_sys:{"type":"sys.stop_request",...}
agent 回复 → IRC PRIVMSG → __zchat_sys:{"type":"sys.stop_confirmed",...}
```

流向：
1. 消息到达 channel-server 的 `on_privmsg()`
2. `decode_sys_from_irc()` 检测 `__zchat_sys:` 前缀
3. 如果是系统消息 → 走 `_handle_sys_message()`，**不推给 Claude**
4. 如果不是 → 作为普通私聊推给 Claude

WeeChat 插件会把 `__zchat_sys:` 消息渲染成可读格式（如 `[zchat] agent0: stop`），不显示原始 JSON。

**不会在 agent 之间自动发**——只有 CLI 的管理操作（stop/join/status）会发 sys 消息。Agent 之间正常沟通用普通频道消息。

> 引用：`zchat-channel-server/server.py:139-143`、`weechat-zchat-plugin/zchat.py:175-190`

---

## Q3: 线程设计与并发问题

### Q3a: 两个 agent 同时操作同一个文件，有锁吗？

**A**: 没有锁，没有保护。每个 agent 是独立的 Claude Code 进程，各自有独立的 workspace（`agents/yaosh-agent0/` 和 `agents/yaosh-helper/`）。如果两个 agent 操作 workspace 外的同一个文件，就是裸写，谁后写谁赢。

**设计意图**：zchat 只管消息通信，不管文件操作。并发控制是应用层（Socialware App）的责任，可以通过 flow/commitment 约束（比如"只有 reviewer 角色才能写 main branch"）。

### Q3b: IRC 线程和 MCP 线程分离意味着什么？有桥接吗？

**A**: 两个线程 + 一个 `asyncio.Queue` 作为桥接：

```
IRC 线程（daemon thread）           Async 主线程
  reactor.process_forever()           MCP server.run()
                                      poll_irc_queue()
  on_pubmsg() ─┐
  on_privmsg()─┤
               │ call_soon_threadsafe()
               └──→ queue.put_nowait() ──→ inject_message()
                                           → write_stream.send()
                                             → Claude Code 收到通知

  connection.privmsg() ←── _handle_reply() ←── Claude 调用 reply tool
```

- **IRC → Claude**：IRC 线程用 `loop.call_soon_threadsafe(queue.put_nowait, ...)` 安全地往 async 队列塞消息，async 侧消费。
- **Claude → IRC**：async 线程直接调 `connection.privmsg()`——irc 库的 `privmsg()` 本身是线程安全的。
- **为什么分离**：irc 库的 `Reactor` 是阻塞式事件循环（`process_forever()`），MCP server 基于 asyncio，两者不能跑在同一个线程里。

> 引用：`server.py:130`（call_soon_threadsafe）、`server.py:171-178`（IRC 线程创建）、`server.py:309-311`（task group）

---

## Q4: 为什么要清理 @mention？

**A**: `@yaosh-agent0 帮我看看 main.py` 推给 Claude 时，如果保留 `@yaosh-agent0`，Claude 会困惑——它不需要知道自己被 @ 了。

`@mention` 是**路由信号**（决定这条消息给哪个 agent），不是指令内容。清理后 Claude 收到的是纯粹的指令："帮我看看 main.py"。

```python
# zchat-channel-server/message.py:15-17
def clean_mention(body, agent_name):
    return body.replace(f"@{agent_name}", "").strip()
```

> 引用：`zchat-channel-server/message.py:15-17`

---

## Q5: 项目和 channel 的关系。Agent 是否永久存在？

**A**: 当前设计是**紧耦合**的：

```
项目 local → config.toml → default_channels: ["#socialware-sy"]
          → tmux session: zchat-e1df88e1-local
          → agents: yaosh-agent0, yaosh-helper（固定属于这个项目）
```

- 一个项目有一组固定频道（config.toml 写死）
- Agent 属于项目，不能跨项目
- Agent 是**非永久的**——`zchat shutdown` 全部销毁，`zchat agent stop` 单个停止
- 重新 `create` 是全新的 Claude Code 实例（workspace 目录保留，但进程和对话上下文是新的）

**能否解耦？** IRC 协议天然支持——Agent 可以 JOIN 任何频道（`join_channel` 工具已有），频道是 IRC 全局的，不属于某个项目。但 zchat CLI 层面没有实现这种灵活性。

**动态机制**：没有。Agent 创建/销毁都是手动 CLI 操作，没有"按需自动扩缩"或"事件驱动创建"。

> 引用：`zchat/cli/project.py:31-45`（config 结构）、`zchat/cli/agent_manager.py:58-88`（create）、`zchat/cli/agent_manager.py:90-101`（stop）

---

## Q6: MCP 工具是静态注册的，能否动态加载？

**A**: 当前不能动态加载。工具在 `register_tools()` 中硬编码：

```python
# server.py:224-268
def register_tools(server, state):
    @server.list_tools()
    async def handle_list_tools():
        return [reply_tool, join_channel_tool]  # 硬编码，只有这两个
```

要加新工具必须改 `server.py` 代码、重新部署 channel-server。

**但有另一条路**：Socialwares 的 **skills（.claude/skills/）** 不走 MCP，走 Claude Code 的 slash command 系统。`socialwares assign` 时通过符号链接动态添加 skills，不需要重启 channel-server。

所以实际分工是：
- **MCP 工具（静态）**：通信能力（reply、join_channel）—— 很少变
- **Skills（动态）**：业务逻辑（查订单、退款、翻译）—— 随 App 安装/卸载

> 引用：`server.py:224-268`（register_tools）

---

## Q7: Agent 私聊是否会新建 channel？

**A**: 不会。IRC 的私聊（PRIVMSG nick）是点对点的，不经过任何 channel，IRC 服务端不创建任何频道。

WeeChat 会自动打开一个私聊 buffer（看起来像新窗口），但那只是客户端 UI，不是 IRC 频道。

在 channel-server 中，私聊和频道消息的处理路径完全分开：

| 类型 | 触发 | context | Claude 收到的 chat_id |
|------|------|---------|----------------------|
| 频道消息 | `on_pubmsg()` | `event.target`（如 `#general`） | `#general` |
| 私聊消息 | `on_privmsg()` | `nick`（如 `alice`） | `alice` |

Claude 回复时 `reply(chat_id="alice")` 就是私聊回去，`reply(chat_id="#general")` 就是频道回复。

> 引用：`server.py:112-131`（on_pubmsg）、`server.py:133-154`（on_privmsg）

---

## Q8: 断线重连与网络波动的影响

### IRC 侧断线

channel-server 有重连机制：

```python
# server.py:156-163
def on_disconnect(conn, event):
    time.sleep(5)
    conn.reconnect()
```

重连后 `on_welcome()` 会重新 JOIN 所有 `IRC_CHANNELS` 频道。

**问题**：
- 断线期间的消息**全部丢失**——IRC 不缓存，queue 里没有新消息
- 重连后不会补发（没实现 CHATHISTORY 回放）
- 没有重连次数限制，没有指数退避——固定 5 秒重试
- 如果 IRC 线程挂了，async 侧的 `poll_irc_queue` 永远阻塞在空队列，不报错

### Claude/MCP 侧断线

MCP 走 stdio（进程间管道），不是网络连接。Claude Code 进程崩溃时：

- MCP server 的 `server.run()` 因 read_stream 关闭而退出
- `finally` 块断开 IRC 连接
- 整个 channel-server 进程结束
- zchat 的 `_check_alive()` 发现 tmux window 不在了，标记 agent offline

### 风险总结

| 场景 | 现状 | 后果 |
|------|------|------|
| IRC 短暂断线（几秒） | 5 秒重连 | 丢几条消息，重连后恢复 |
| IRC 长时间断线 | 无限重试无退避 | 刷日志，恢复后正常但消息全丢 |
| Claude Code 崩溃 | 整个 channel-server 退出 | agent 离线，需手动 `zchat agent restart` |
| ergo 服务器重启 | 所有 agent 断线重连 | 所有人同时丢消息，频道状态重置 |
| 网络波动丢一条消息 | 无确认机制，无重发 | 静默丢失，没有任何告警 |

**核心问题**：没有消息确认（ACK）机制，没有消息持久化，没有补发。IRC 协议本身是 fire-and-forget 的。

> 引用：`server.py:156-163`（on_disconnect）、`agent_manager.py:287-299`（_check_alive）

---

## Q9: 操作不幂等 — IRC 断线但 Claude 已执行

### 场景

```
用户: @agent0 帮我删除 test.db
  → Claude 收到消息，执行 rm test.db（不可逆操作已完成）
  → Claude 调用 reply(chat_id="#support", text="已删除")
  → _handle_reply() 调用 connection.privmsg()
  → 此时 IRC 已断线 → privmsg() 静默失败或抛异常
```

### 问题链

1. `_handle_reply()` 没有 try/except，不检查 `privmsg()` 是否发送成功：
   ```python
   # server.py:270-278
   connection.privmsg(target, chunk)  # 断线时静默失败
   return [TextContent(type="text", text=f"Sent to {chat_id}")]  # 无论如何返回"已发送"
   ```

2. Claude 认为"已发送"，但用户没收到回复

3. 用户没看到确认，可能重发 `@agent0 删除 test.db`

4. Claude 再执行一次——**操作不幂等**

### 根因

"先执行后回复"的模式天然不幂等。IRC 没有消息 ACK，`privmsg()` 是 fire-and-forget。

> 引用：`server.py:270-278`（_handle_reply，无错误检查）

---

## Q10: Agent 僵死 — 进程在但不响应

### 场景

```
Claude Code 进程假死（进程在，但不响应 MCP）
  → server.run() 阻塞在 read_stream.recv()
  → IRC 线程还活着，继续收 IRC 消息
  → 消息推到 queue → inject_message() 写 write_stream
  → write_stream 写成功（pipe buffer 没满，OS 会缓冲约 64KB）
  → Claude 不处理 → 消息堆积在 pipe buffer
  → tmux window 还在 → _check_alive() 返回 "running"
  → 用户 @agent0 没反应，但系统认为它在线
  → 永久僵死，无法自愈
```

### 根因

zchat 的存活检测只看 tmux window 是否存在（`window_alive()`），不检查 agent 是否真的能处理消息。**没有心跳机制**。

```python
# agent_manager.py:287-299
def _check_alive(self, name):
    window_name = info.get("window_name")
    if window_name and window_alive(self.tmux_session, window_name):
        return "running"  # window 在就算 running，不管能不能响应
    return "offline"
```

### 修复建议汇总

| 问题 | 严重性 | 建议 |
|------|--------|------|
| `privmsg()` 静默失败 | 高 | `_handle_reply` 加 try/except + 连接状态检查 |
| 操作已执行但回复没发出 | 高 | 架构问题——需要"先回复后执行"或事务性执行 |
| 无消息 ACK | 中 | IRC 协议限制，短期不好改 |
| agent 僵死检测 | 中 | 加心跳：定期发 `sys.status_request`，超时标记 offline |
| IRC 重连无退避 | 低 | 5s → 指数退避（5/10/20/40s，上限 5min） |

> 引用：`server.py:270-278`（_handle_reply）、`agent_manager.py:287-299`（_check_alive）

---

## Q11: Project 与 Channel 的解耦问题

### 现状

- Agent 与 project 绑定，channel 是 IRC 全局资源，与 project 无关
- zchat 把一个 project 硬编码对应 `default_channels`，但 agent 可以通过 `join_channel` 动态加入任意频道
- 动态加入的频道不在 zchat 管理视野内——`zchat irc status` 看不到，重启后不会自动重新 JOIN

### Agent 能否创建 channel？

**能**。IRC 协议里 JOIN 一个不存在的频道就是创建它。channel-server 的 `join_channel` 工具直接调 `connection.join()`，频道不存在时 ergo 自动创建。

### 创建的 channel 需要单独管理 members 吗？

**IRC 自己管**。谁 JOIN 就是 member，谁 PART/QUIT 就不是。但 zchat 侧完全不知道这些动态频道的存在。

### Project 关了，channel 怎么办？

`zchat shutdown` → 所有 agent 和 WeeChat 断开 → 频道变空 → ergo 自动销毁频道。下次重启频道重新创建，但历史消息丢失。

### 能否一个 project 多个 channel？

**config.toml 已支持**：`default_channels = ["#general", "#support", "#dev"]`。agent 运行时还可以动态 JOIN 更多。

### 能否跨 project？

**IRC 层面天然支持**——不同 project 的 agent 连同一个 ergo 就能 JOIN 同一个频道。但 zchat CLI 层面不知道其他 project 的存在，没有统一管理。

### 核心问题

zchat 把 project 当"管理边界"，但 IRC 的 channel 是全局资源。需要一个超越 project 的全局管理视角。

> 引用：`server.py:280-283`（join_channel）、`zchat/cli/project.py:31-45`（config 结构）

---

## Q12: ergo 的权限与管理界面的访问控制

### ergo 已有的权限体系

1. **SASL 认证**（已实现）：`irc_manager.py:116-160` 注入 OIDC 认证脚本，连接时必须用 access_token 做 SASL PLAIN 认证
2. **IRC operator**：标准的频道权限（`+o` operator、`+v` voice 等）。WeeChat 中 `@yaosh` 就是 operator
3. **Agent 所有权验证**（已实现）：`ergo_auth_script.py:62-71` 检查 agent nick 前缀是否匹配 token 用户名，防止冒名

### 本地模式无认证

当前本地开发模式（`127.0.0.1:6667`，无 TLS）认证完全关闭。生产环境（TLS + SASL）才有认证。

### 管理界面权限方案

| 方案 | 说明 | 推荐 |
|------|------|------|
| IRC operator | `@` 前缀的用户 = 管理员 | 简单但粗糙 |
| zchat 自维护 admin 列表 | config.toml 或 auth.json 扩展 | 需造轮子 |
| OIDC token 带角色 claim | Logto 支持 RBAC，token 里加 `role: admin` | ✅ 最自然，不造轮子 |

全局视角的实现：用 IRC 的 LIST/NAMES/WHO 命令查询所有频道和成员，结合 zchat state.json 展示 agent 状态。IRC 协议已有这些能力，zchat 只是没有封装。

> 引用：`zchat/cli/irc_manager.py:116-160`（_inject_auth_script）、`zchat/cli/ergo_auth_script.py:62-71`（所有权验证）

---

## Q13: 消息/频道/成员持久化

### 问题

IRC 协议的天然特性——"人在线就聊，不在就算了"。但对 zchat 的商业场景（客服、agent 协作）来说是**问题，不是设计**：

| 丢什么 | 影响 |
|--------|------|
| 消息 | evolver 没数据，用户无法回溯，agent 重启丢上下文 |
| 频道 | 最后一人离开即销毁，Socialware App 安装的频道随 shutdown 消失 |
| 成员关系 | 重启后 agent 只 JOIN 默认频道，动态加入的频道丢失 |

### 方案对比

**方案 1：ergo 自带能力（最小改动）**

- CHATHISTORY：ergo 已配置 `chathistory=1000`，channel-server 加 `on_welcome` 后请求回放即可
- ChanServ 频道注册：注册后频道不因没人而销毁
- always-on 客户端：离线消息缓存，上线推送

改动小，但能力有限。

**方案 2：channel-server 侧日志（中等改动）**

每条消息写 JSONL + state.json 记录动态频道：

```python
def _log_message(msg, direction, context):
    log_dir = os.path.join(workspace, ".zchat", "logs")
    with open(f"{log_dir}/{context}.jsonl", "a") as f:
        f.write(json.dumps({**msg, "direction": direction}) + "\n")
```

同时也是 evolver 的数据源。

**方案 3：常驻管理 bot（推荐，长期方案）**

```
ergo 服务器
  ├─ zchat-bot（永不下线的管理 bot）
  │   ├─ 加入所有频道，维持频道存活
  │   ├─ 记录所有消息 → 数据库
  │   ├─ 维护频道/成员注册表
  │   ├─ 提供 API 查询历史
  │   ├─ 提供心跳检测（解决 Q10 僵死问题）
  │   └─ 作为 evolver 数据收集入口
  ├─ WeeChat（人）
  ├─ agent0
  └─ helper
```

bot 解决了持久化、频道管理、僵死检测、数据收集四个问题。本质上是一个长期运行的基础设施 agent，不是业务 agent。

### 推荐路径

| 阶段 | 做什么 | 工作量 |
|------|--------|--------|
| 现在 | 方案 2：channel-server 写 JSONL 日志 | 2-3 天 |
| 演示前 | 方案 1：ergo CHATHISTORY 回放 | 1 天 |
| 产品化 | 方案 3：常驻 zchat-bot | 1-2 周 |

> 引用：ergo 配置 `CHATHISTORY=1000`；`server.py:97-110`（on_welcome，可扩展请求历史）

---

## Q13 补充：为什么 bot 方案更好

相比 channel-server 侧日志（每个 agent 各自记录），常驻 bot 的优势：

1. **单一数据源**：所有频道的消息汇聚到一个 bot，不用合并多个 agent 的日志
2. **频道保活**：bot 始终在频道里，频道不会因没人而被 ergo 销毁
3. **全局视角**：bot 看到所有频道的所有消息，是管理界面和 evolver 的天然数据源
4. **心跳探针**：bot 可以定期给每个 agent 发 `sys.status_request`，检测僵死
5. **独立于 project 生命周期**：project shutdown 后 bot 还在，频道和历史保留
