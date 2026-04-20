# V7+ Roadmap: Squad 监管扩展

> 2026-04-20 · 承接 V6 的 `[bots].supervises = ["<bot-name>"]` 基础能力，
> 记录未来多 squad 精细化监管的升级路径。

## V6 现状（已实现）

一对 N 关系：**一个 squad bot 监管一个或多个 customer-类 bot 的所有 channels**。

```toml
[bots."customer"]
app_id = "..."

[bots."squad"]
app_id = "..."
supervises = ["customer"]          # 监管 bot="customer" 的全部 channels

[channels."conv-001"]
bot = "customer"
external_chat_id = "oc_客户A"

[channels."conv-002"]
bot = "customer"
external_chat_id = "oc_客户B"
```

### 实现机制
- `routing_reader.read_supervised_channels(routing, bot_name)` 扫 `[bots."<bot>"].supervises` 列表，返回该 bot 负责监管的所有 channels
- squad bridge 启动时 + routing.toml 变化时重算监管集（动态）
- `_on_bridge_event` filter 接受 `own ∪ supervised`
- 新增 `_handle_supervised_message`：首次见 conv → 发 card；后续消息 → thread 回复

### 红线自检
- `supervises` 字段只在 bridge 层读（非 CS 核心） ✓ spec §2.2 红线 3
- customer bot **完全无感知**被谁监管（声明在 squad 一侧） ✓ 解耦

## V7+ 升级：多 squad 精细化监管

### 动机

实际运营中可能出现：
- **按地域分**：`squad-east` / `squad-west`，各管自己区域的客户
- **按 VIP 级别**：`squad-vip` 专管高价值客户
- **按产品线**：`squad-ecommerce` / `squad-saas`
- **上下级监管**：`squad-manager` 监管所有 `squad-*` 也监管的 conv

要求：
- **仍然一个 customer bot**（不 bot 爆炸）
- 细粒度 channel-level 分组
- squad 按组别灵活订阅

### 升级方案：channel-level tag

**唯一新字段**：`[channels.<id>].tags: list[str]`

**升级 `supervises` 语法**（向后兼容）：

| 语法 | 含义 | V6 | V7 |
|------|------|----|----|
| `"customer"` | 按 bot 名匹配（默认） | ✓ | ✓ |
| `"bot:customer"` | 同上，显式前缀 | — | ✓ |
| `"tag:east"` | 按 channel tag 匹配 | — | ✓ |
| `"pattern:conv-east-*"` | 按 channel 名 glob | — | ✓ 可选 |

**典型 V7 配置**：

```toml
[bots."customer"]                     # 仍然只有一个 customer bot
app_id = "cli_a954..."

[channels."conv-east-001"]
bot = "customer"
tags = ["east"]                       # ← channel 打 tag

[channels."conv-east-002"]
bot = "customer"
tags = ["east"]

[channels."conv-west-001"]
bot = "customer"
tags = ["west"]

[channels."conv-vip-001"]
bot = "customer"
tags = ["vip", "west"]                # 多 tag

[bots."squad-east"]
supervises = ["tag:east"]             # 只管东区

[bots."squad-west"]
supervises = ["tag:west"]             # 只管西区（含 conv-vip-001，因它有 west tag）

[bots."squad-vip"]
supervises = ["tag:vip"]              # 跨区域 VIP 组

[bots."squad-manager"]
supervises = ["tag:east", "tag:west"]  # 上级监管全部
```

### 关键点

1. **Customer bot 数量不变**：全系统只需 1 个 `[bots."customer"]`（或按业务隔离的 N 个，但与 tag 机制解耦）
2. **Channel 扩容无感**：新建客户群打 tag，所有匹配 tag 的 squad 自动接收
3. **一个 conv 可被多 squad 监管**：多 tag × 多 squad 监管 = 自然 M×N
4. **`bot:` 与 `tag:` 共存**：同一 `supervises` 列表可混写 `["bot:customer", "tag:vip"]`（并集）

## V7 实现工作量估算

### Schema 变更（0.1 人日）
- `routing.py` `ChannelRoute` 加 `tags: list[str] = field(default_factory=list)`
- `routing.py` `Bot` 已有 `supervises` 字段 V6 支持

### routing_reader 扩展（0.3 人日）
```python
def read_supervised_channels(routing, squad_bot) -> dict[chat_id, channel_id]:
    data = _load_toml(routing)
    bot_cfg = (data.get("bots") or {}).get(squad_bot, {})
    supervises = bot_cfg.get("supervises", [])
    result = {}
    for entry in supervises:
        # 解析前缀语法
        if entry.startswith("tag:"):
            target_tag = entry[4:]
            matcher = lambda ch: target_tag in (ch.get("tags") or [])
        elif entry.startswith("pattern:"):
            import fnmatch
            pat = entry[8:]
            matcher = lambda ch, ch_id: fnmatch.fnmatch(ch_id, pat)
        else:
            # 默认 = bot:<name>
            target_bot = entry[4:] if entry.startswith("bot:") else entry
            matcher = lambda ch: ch.get("bot") == target_bot
        for ch_id, ch in (data.get("channels") or {}).items():
            if matcher(ch):
                ext = ch.get("external_chat_id")
                if ext:
                    result[ext] = ch_id
    return result
```

### CLI（0.3 人日）
- `zchat channel set-tag <channel> <tag>` 加/删 tag
- `zchat channel tag --add east conv-001` 便捷语法
- `[bots.<name>].default_channel_tags` 懒创建时默认打 tag（可选）

### 测试（0.3 人日）
- `test_routing_reader.py::test_supervises_by_tag` 覆盖 tag 匹配
- `test_routing_reader.py::test_supervises_by_pattern` 覆盖 glob
- `test_routing_reader.py::test_supervises_mixed_syntax` 混用 bot + tag
- `test_routing_reader.py::test_channel_with_no_tags_not_matched` 无 tag 的不被 tag 订阅的 squad 看到

**合计：约 1 人日**。

## V8+ 继续可能性

### 场景变得复杂到 V7 也撑不住时

| 需求 | 方案 |
|------|------|
| 基于客户标签动态路由（"今天这个客户升级 VIP → 自动给 squad-vip"） | channel.tags 运行时变更 + bridge 重新订阅 |
| N 个 squad 间竞争接管同一 conv | 引入 "ownership" 概念 + 抢单 API |
| 按时段动态分配（夜间由 squad-oncall 接管） | 加 `[schedule]` 规则表 |
| 业务规则表（if-then） | rules-based routing 引擎（慎入，易陷入 DSL 泥潭） |

**原则**：V7 tag 机制是**升级天花板的 80%**。真到 V8 规则引擎那一天，通常已经该换架构层（比如引入 Temporal / 事件总线），不是小改 routing.toml 的事。

## V7 触发条件

**开始做 V7 的标志**：
- 用户明确提出"我有 3+ squad 要分别管不同客户"
- 单一 squad 群太拥挤（一天 100+ 卡片）影响工作效率
- 需要"按部门/地域"做数据隔离

**未达这些条件前，继续 V6 的简单模型**。

## 与现有 spec / note 的关系

- spec `docs/spec/channel-server-v5.md` §6.1 "双层映射" 提到 supervision，但是 YAML 形式（V5 遗留）
- V6 把 supervises 提到 routing.toml + bot-level，删除 YAML
- V7 继承 V6 扩展，spec 需同步更新 §6.1

## 实现上的"代码预留点"（V6 做的时候提前埋好）

`routing_reader.py` 的 `read_supervised_channels` 解析函数里：

```python
for entry in supervises:
    if ":" not in entry:
        # V6 默认语义：bot 名
        _match_by_bot(entry, ...)
    elif entry.startswith("bot:"):
        _match_by_bot(entry[4:], ...)
    elif entry.startswith("tag:"):
        log.warning("V7 feature: tag supervision not yet implemented")
        # or: raise NotImplementedError
    # ... 未来扩展
```

这样 V6 解析 `["customer"]` 正常工作；V7 加 `tag:` 分支时老配置仍然合法。

---

*撰写人：Claude (V6 实施中) · 下一次 review：V6 pre-release 完成后*
