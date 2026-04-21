# V6 Pre-release 真机测试 session 2 note

> 2026-04-20 · 承接 `v5-prerelease-test-setup-note.md`（V6 重构完成后的第二次测试）
>
> 上一轮 note §10.1 ~ §10.16 记录了 V5 测试中暴露的 16 个配置体验问题 + bug，
> 已在 V6 重构中修复或整改方向化。本 note 记录 V6 架构跑完 `zchat up` 一键启动
> 后的新问题。

## 1. 环境

- 主仓 refactor/v4 @ 936295b（V6 routing.toml [bots] + zchat up/down）
- CS refactor/v4 @ d6fae20（V6 bridge --bot）
- 3 个飞书 bot：customer / admin / squad
- 3 个群 + 1 个待建的 cs-customer-test

## 2. 问题列表

### 2.1 真 BUG：`zchat bot add` pdir 是 str 不是 Path

**症状**：
```
TypeError: unsupported operand type(s) for /: 'str' and 'str'
at  cred_dir = pdir / "credentials"
```

**根因**：V6 新命令 `cmd_bot_add/cmd_bot_remove/cmd_up` 假设 `project_dir()` 返回 `Path`，实际返回 `str`。

**修复**：三处 `pdir = project_dir(project_name)` 改为 `pdir = Path(project_dir(project_name))`。

**整改建议**：
- `project_dir()` 函数本身改返 `Path`（更干净，但全仓 grep 影响面大）
- 或在 V6 新命令 smoke-test 里覆盖

### 2.2 真 BUG：`_get_irc_config` 非幂等 → `zchat up` 报"老格式"

**症状**：
```
$ zchat up
ergo: started
cs: started
bridge-customer: started
bridge-admin: started
bridge-squad: started
Error: Project uses old config format ([irc] section).
Please delete the project and recreate it:
  zchat project remove <name> && zchat project create <name>
```

前面服务都起来了，只有 agent 创建这一步挂。

**根因**：典型的 mutation 副作用 + 非幂等检测：
1. `_get_irc_manager(ctx)` 第一次调用时，为了让 `IrcManager` 直接能读 `cfg["irc"]`，往 cfg dict 里塞了 `cfg["irc"] = _get_irc_config(cfg)`（line 147-148）
2. 后续 `_get_agent_manager(ctx)` 再调 `_get_irc_config(cfg)` 时，看到 `"irc" in cfg` → 误判为"老格式"拒绝

`zchat up` 正好触发这个序列：先 irc 后 agents。旧的单命令流程不会连调这俩，所以没暴露。

**修复**：`_get_irc_config` 改 idempotent —— 若 `cfg["irc"]` 已有 `host/port`（注入特征），直接返回；只有裸 `[irc]` section（无 host/port，老格式特征）才报错。

**整改建议**（V6+）：
- **上策**：别 mutate cfg。`IrcManager` 构造函数直接接 `irc_config` 参数
- **中策**：用不同 key（如 `_resolved_irc`）避免与 "检测字段" 冲突
- **下策**：当前的 idempotent patch（快但依赖字段特征）

这个 bug 暴露了 V5 → V6 编排层（`zchat up` 连调多个 getter）对旧有副作用式 helper 的脆弱。Ralph-loop 可以加一条：**所有 `_get_*(ctx)` helper 对同一 ctx 重复调用应幂等**。

### 2.3 真 BUG：`zchat up` 输出 `##conv-001` 双 # 显示

**症状**：
```
agent fast-001: started in ##conv-001 (type=fast-agent)
agent admin-0: started in ##admin (type=admin-agent)
```

**根因**：`cmd_up` 的 echo：
```python
typer.echo(f"agent {short}: started in #{ch_id} (type={template})")
```
`ch_id` 在 routing.toml 已带 `#`（key 形式 `[channels."#admin"]`），再拼一个 `#` 就双了。

**修复**：echo 前 `lstrip("#")`。纯显示问题，不影响 agent IRC JOIN（agent_mcp.py 已有 lstrip）。

**整改建议**：routing.toml key 的 `#` 前缀是 V3 时代历史，应该在 V6+ normalize 到裸名（写入端一次统一），避免全项目靠 lstrip 打补丁。

### 2.4 真 BUG：`zchat up` 的 tab "started" 其实静默失败（无 zellij session）

**症状**：
```
ergo: started
cs: started                    ← 假的
bridge-customer: started       ← 假的
...
up: complete
$ zellij list-sessions
No active zellij sessions found.
$ ls ~/.zchat/projects/prod/cs.log
No such file or directory
```

3 agent `offline` 而非 running，cs.log / bridge-*.log 不存在。

**根因**：`cmd_up` 调 `_zj.new_tab(session, ...)`，但 `zellij action new-tab --session X` 在 X 不存在时**静默失败**（无报错）。V5 流程下 `zchat irc start` 会隐式 `ensure_session`，V6 `zchat up` 里我没调。

**修复**：在 cs/bridge/agent 启动**之前**先 `ensure_session(session)`，并提前启动 weechat 的 `chat` tab（补回 V5 `zchat irc start` 的行为）。

**整改建议**：所有 `_zj.new_tab` 的调用点，前面都需要 ensure_session 保障（或在 `new_tab` 内部自己兜底，更 foolproof）。

### 2.5 UX 缺陷：`zchat up` 的 started 消息没经过就绪校验

**症状**：紧跟 2.4。"started" 只代表命令发出，不代表进程跑起来。

**整改**：
- `zchat up` 每起一个服务后用 `tab_exists + log 匹配关键字` 做 readiness check
- 超时 5s → 显式报 fail，而非假性 "started"

### 2.6 真 BUG：`zchat up` 调 `build_weechat_cmd(nick=...)` 参数名不对

**症状**：`weechat: skip (IrcManager.build_weechat_cmd() got an unexpected keyword argument 'nick')`

**根因**：`IrcManager.build_weechat_cmd(nick_override: str | None = None)`，我写 cmd_up 时手滑成 `nick=`。

**修复**：`nick=` → `nick_override=`。V6 `zchat up` 自己调 weechat tab（不靠 `zchat irc start`）是本 session 新引入的路径，老的 `_launch_project_session` 绕开了这个问题。

### 2.7 真 BUG：`zchat up` 把 offline agent 条目当作"已存在"跳过

**症状**：
```
$ rm -rf ~/.zchat/projects/prod/agents/yaosh-fast-001     # 删 workspace
$ zchat up
... (cs/bridge 都起来了，但 agent 创建一行都没打)
$ zchat agent list
  yaosh-fast-001  fast-agent  offline  ...                 ← 还是 offline
```

**根因**：`cmd_up` 的 agent skip 逻辑：
```python
if mgr.scoped(short) in existing:     # existing = mgr.list_agents()
    continue
```
`list_agents()` 返回**所有** state.json 条目（含 offline）。用户手动 `rm -rf` 了 workspace 但没删 state.json 条目 → 被当"已存在"跳过，不重建。

**修复**：改成只跳过 `status == "running"` 的条目；offline / dangling 的先 `mgr.stop(force=True) + _agents.pop() + _save_state()` 清理再重建。

**整改建议**（V6+）：`AgentManager.list_agents()` 语义明确化；增加 `AgentManager.clean_dead()` 一键清孤儿条目；`zchat up` 内部集成此 clean。

### 2.8 真 BUG：`zchat up` 给 zellij new-tab 做了双层 `bash -c` 嵌套

**症状**：
```
$ zchat up
cs: started                    ← cs 正常
bridge-customer: started       ← log 只有 uv warning，bridge 没真跑
bridge-admin: started          ← 同上
bridge-squad: started          ← 同上
```

`ps` 查不到 bridge python 进程；log 只有 uv 的 `VIRTUAL_ENV mismatch` warning。

**根因**：`zchat/cli/zellij.py:new_tab` 内部已经把 command 包在 `bash -c` 里。我在 `cmd_up` 里又手工外包了一层：
```python
_zj.new_tab(session, tab, command=f'bash -c "{cmd}"')     # 错
```
最终被执行的是 `bash -c 'bash -c "cd ... && uv run ..."'` —— 双 `bash -c` 的 quoting 破了 && / | / 带空格的路径。

**修复**：`command=cmd`（直接传 cmd，让 `new_tab` 做单层 wrap）。

**整改**：`new_tab` 应该在 docstring 明写"自动包 bash -c"，避免调用者误以为需自己包。或拒绝已经 `bash -c`-prefixed 的 cmd。

### 2.9 真 BUG：`zchat-agent-mcp` binary 不在全局 PATH

**症状**：agent 的 `.mcp.json` 配 `"command": "zchat-agent-mcp"`，但：
- claude 启动后 `ps ... --ppid <agent>` 无 zchat-agent-mcp 子进程
- 所以 agent 的 IRC 连接永远不会建立
- WeeChat `/names #conv-001` 只看到 `cs-bot` + 用户

**根因**：`zchat-agent-mcp` 只装在 `~/projects/zchat/zchat-channel-server/.venv/bin/`（uv sync 产物），不在 `$PATH`。Claude 起 MCP server 找不到 → 静默失败（MCP server load 错误通常不致命，claude 继续无 MCP 运行）。

**修复**：`uv tool install --force --reinstall --editable ~/projects/zchat/zchat-channel-server` → binary 进 `~/.local/bin/`，全局 PATH 可达。

**整改**：`zchat doctor` 应验证 `which zchat-agent-mcp`，缺则提示 `uv tool install --editable`；pre-release 脚本第一步跑此校验。

### 2.10 真 BUG：`agent_mcp.py` 等根目录文件没被 wheel 打包

**症状**：装完 `zchat-agent-mcp` 后直接跑：
```
ModuleNotFoundError: No module named 'agent_mcp'
```
或
```
FileNotFoundError: .../site-packages/instructions.md
```

**根因**：`pyproject.toml` 的 `[tool.hatch.build.targets.wheel].packages` 只列 `src/channel_server`、`src/plugins`、`src/feishu_bridge`，而 `agent_mcp.py` / `instructions.md` / `commands/` / `.claude-plugin/` 都在仓库根目录。editable install 不会自动带。

**修复**：
```toml
[tool.hatch.build.targets.wheel.force-include]
"agent_mcp.py" = "agent_mcp.py"
"instructions.md" = "instructions.md"
".claude-plugin" = ".claude-plugin"
"commands" = "commands"
```

**整改**：
- 长期：把 `agent_mcp.py` 搬进 `src/agent_mcp/` 成为正规子包，避免仓库根 Python 文件
- 或：`tests/unit/test_wheel_contents.py` 用 `importlib.resources` 断言运行时能找到这些文件

### 2.11 致命 BUG：`feishu_bridge/__main__.py` 缺 `if __name__ == "__main__": main()`

**症状**：
```
$ uv run python -u -m feishu_bridge --bot customer --routing ...
$ echo $?
0
# 0 秒退出，无任何 stdout / stderr
```

bridge 跑不起来，log 文件只有 uv warning 一行。

**根因**：`__main__.py` 定义了 `main()` 但**从未调用**。`python -m feishu_bridge` 按 `__main__.py` 作脚本运行，但没 `if __name__ == "__main__"` gate → 仅 import 模块 + 定义函数 + 退出 0。

**修复**：文件末尾加
```python
if __name__ == "__main__":
    main()
```

**为什么 V5 没暴露**：V5 pre-release plan 用 `zchat-feishu-bridge` 命令（pyproject scripts 入口点 = `feishu_bridge.__main__:main`，显式调 main）。V6 我改成 `python -m feishu_bridge` 就暴露了。

**整改**：
- `tests/unit/test_module_entrypoints.py` 对每个 `python -m X` 可调用模块做 smoke test：`subprocess.run([python, -m, X, --help], timeout=3)` 要有 stdout
- Ralph-loop 的 dead code 扫描加一条：所有 `__main__.py` 都得有 `if __name__ == "__main__"`

### 2.12 真 BUG：V6 `build_config_from_routing` 把 customer chat 错标为 operator

**症状**：cs-customer 群发 "你好"，bridge 日志：
```
[feishu-bridge] INFO [operator] ou_ed51...: 你好
```
然后消息没有转发到 CS / IRC，客户群也无回复。

**根因**：我的 V6 重构在 `build_config_from_routing` 里写：
```python
groups=GroupsConfig(
    squad_chats=[{"chat_id": c} for c in own_chats],   # ← 错：所有 bot 的 chat 都塞 squad
    customer_chats=own_chats,
),
```

`GroupManager.identify_role` 检查顺序：admin → squad → customer → unknown。squad_chats 匹配在前 → 所有消息被标为 operator。

operator 消息在 bridge 流程里只在"有 active conv 的 squad thread 里"才有效；customer 群发过来本该是 customer 消息。标错就走 `log.debug("operator message in squad %s but no active conversation")` → 静默丢弃。

**修复**：按 `bot_name` 区分：
```python
if bot_name == "squad":
    squad_list = [{"chat_id": c} for c in own_chats]
else:
    customer_list = own_chats     # customer / admin 的 chat 都归此
```

**根本整改**（V6+）：routing.toml `[bots]` 加显式 `role` 字段（generic enum：customer / operator / admin），删 `identify_role` 里那一堆按 chat_id 匹配的分支。一 bot 一 role 就够了。

### 2.13 真 BUG：`zchat up` agent 重建后 zellij 残留双 tab

**症状**：`zellij action query-tab-names` 看到：
```
yaosh-fast-001
yaosh-admin-0
yaosh-squad-0
yaosh-fast-001   ← 重复！一个是真的 running，一个是 stale 死 shell
```

**根因**：我的 cmd_up 清 stale state 逻辑只清了 `mgr._agents` dict 和 state.json，**没有 close 旧 zellij tab**。`mgr.create` 建新 tab 时，旧 tab 还在 zellij 里挂着。

**修复**：清 state 后额外 `_zj.close_tab(session, scoped)`。

**整改**：和 2.8 同方向 —— AgentManager 应提供 `clean_dead_tabs()` 一站式清理；cmd_up 直接调用。

### 2.14 致命 BUG：bridge `_forward_customer` 发 chat_id 当 channel，违反 spec 红线 3

**症状**：cs.log 警告：
```
[router] channel 'oc_4842ab45da4093cc77565fbc23dd360f' has no entry_agent;
message not delivered to any agent
```

bridge 把 customer 消息转发出来了，但 CS 的 router 拿 chat_id 去 routing.toml 查 channels key → 查不到（routing 里 key 是 `#conv-001`）→ 丢。

**根因**：`bridge._forward_customer` 构造 WS 消息时：
```python
self._bridge_client.send(ws_messages.build_message(
    channel=chat_id,              # ← 错：把 feishu chat_id 直接当 channel 发
    ...
))
```

spec `channel-server-v5.md §2.2 红线 3` 明写："**CS 对 external_chat_id 透明**"——路由表里 channels key 是 channel_id（`#conv-001`），不是 external_chat_id（`oc_xxx`）。bridge 必须自己做映射。

V5 出站（OutboundRouter）已经实现了 channel_id → chat_id 映射；入站路径 `_forward_customer` 漏了对称的 chat_id → channel_id。

**修复**：
```python
channel_id = self._external_to_channel.get(chat_id)
if not channel_id:
    log.warning("[forward] no channel mapping for chat_id=...")
    return
# 后续所有 build_event / build_message 用 channel_id 不用 chat_id
```

**整改**：
- `tests/e2e/test_bridge_message_flow.py` 加 case：`_forward_customer(known chat_id)` 发出的 WS msg.channel 必须等于 routing.toml 里对应的 channel_id，NOT chat_id
- 同样需要检查 `_forward_operator / _forward_admin`（也可能有同 bug）
- Ralph-loop 再加一条：grep bridge 代码里出现的 `channel=chat_id` —— 应只在 GroupManager 内部，不该在 WS 消息构造里

### 2.15 真 BUG：bridge `_forward_to_bridge` 无 try/except 吞掉下游异常

**症状**：customer 群发 "你好" → bridge log 出现：
```
[customer] ou_...: 你好
[outbound] WARNING on_conversation_created: no squad chat for #conv-001
(然后彻底静默，WSS ping/pong 停，40s 后 CS 报 bridge disconnected)
```

customer bridge 进程死掉。CS 路由器没收到消息（因为 build_message.send 从未被调用）。

**根因**：`_forward_to_bridge` 调 `handler(chat_id, ...)` 没 try/except。handler 中任何一步的异常都会 bubble 到 lark_oapi 的事件 dispatcher，被 lark 内部静默吞或者让 dispatcher 线程死掉 → WSS 心跳停 → bridge 进程名存实亡。

**当前修复**：加 try/except + log.exception，至少能看到 traceback。

**仍待诊断**：为什么 customer bridge 在"no squad chat"warning 之后会挂？outbound 返回 None 正常，后续的 build_message.send 应该继续。等新 log 暴露实际 exception。

**整改**：
- `_forward_to_bridge` / `_handle_*_event` 都必须 `log.exception` 包裹 —— 入站事件处理器是最外层，不能让异常吞到 SDK
- 单元测试补：mock `outbound.on_conversation_created` raise，验证 bridge 仍完成 build_message.send

## 3. 修改汇总（本 session 内）

| 文件 | 改动 |
|------|------|
| `zchat/cli/app.py` cmd_bot_add | `Path(project_dir(...))` |
| `zchat/cli/app.py` cmd_bot_remove | 同上 |
| `zchat/cli/app.py` cmd_up | pdir 类型 + echo lstrip # + ensure_session + weechat tab |
| `zchat/cli/app.py` `_get_irc_config` | idempotent 检测（按字段特征） |

## 4. 测试进度

- [x] §0.1 ~ §0.4 主机 + 仓库 + 项目 + 3 bot
- [x] §0.5 用 list_chats.py 确认 bot 隔离
- [ ] §0.6 3 channel（待测）
- [ ] §0.7 第 4 群 cs-customer-test（lazy create 用）
- [ ] §1 zchat up 全栈验证
- [ ] §2 PRD TC 逐条跑
- [ ] §3 飞书 SDK 6.3 清单

## 5. 下次起手式

```bash
# 若之前 shell 已退出
alias zchat='uv --project ~/projects/zchat run zchat'
source ~/.zchat/projects/prod/.env 2>/dev/null  # 如有

zchat bot list                       # 确认 3 bot
zchat channel list                   # 确认 3 channel 或 0
zchat agent list                     # 确认 agent 状态
zellij list-sessions                 # 确认会话状态
```
