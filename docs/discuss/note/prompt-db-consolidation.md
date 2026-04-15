# Task: SQLite 数据库合并

> 复制以下 prompt 到新 session 中执行。
> 单个 Task，走 dev-loop 六步闭环。

---

## Prompt

```
你被启动在 zchat 项目根目录 (`~/projects/zchat/`)。
代码在 `zchat-channel-server/` submodule 内，`refactor/channel-server` 分支。

## 目标

重构 engine 层数据库：3 个独立 SQLite 文件合并为 1 个文件 5 张表，添加外键约束和 CASCADE。
这是 Phase Final (pre-release) 的前置依赖。

Spec 在 `docs/discuss/spec/channel-server/11-db-consolidation.md`。
Plan 在 `docs/discuss/plan/08-db-consolidation.md`。

## 当前状态

- refactor/channel-server 分支，240 tests passed, 0 failed
- 44 个 artifact 在 .artifacts/registry.json
- 问题：3 个 engine 组件各持独立 SQLite 文件，跨文件无 FK

## 工作环境

```bash
cd zchat-channel-server
git checkout refactor/channel-server
git checkout -b fix/db-consolidation

# 验证基线
uv run pytest tests/ feishu_bridge/tests/ -v --tb=short
# Expected: 240 passed, 0 failed
```

## 问题详情

3 个独立 SQLite 文件通过 conversation_id 强关联但无法建外键：

```python
# server.py:50-56 — 当前 3 个路径
CS_DB_PATH = "conversations.db"
CS_EVENT_DB_PATH = "conversations_events.db"
CS_MESSAGE_DB_PATH = "conversations_messages.db"

# server.py:524-562 — 当前 3 个独立连接
event_bus = EventBus(CS_EVENT_DB_PATH)          # 自己建表、自己连接
conversation_manager = ConversationManager(CS_DB_PATH)  # 自己建表、自己连接
message_store = MessageStore(CS_MESSAGE_DB_PATH) # 自己建表、自己连接
```

导致：无 CASCADE 删除、无事务一致性、edit 链可断、孤儿数据。

## Dev-loop 六步闭环

Artifact ID 前缀: `cs-*-db-consolidation`

### Step 1: eval-doc

/dev-loop-skills:skill-5-feature-eval simulate
# 主题: "SQLite 数据库合并 — 3 文件 → 1 文件 5 表 + FK + CASCADE"
# 产出: .artifacts/eval-docs/cs-eval-db-consolidation.md

行为预期（必须覆盖）:
1. 单一 conversations.db 包含 5 张表
2. PRAGMA foreign_keys = ON 生效
3. 删对话 → participants/resolutions/messages CASCADE，events SET NULL
4. messages.edit_of 原消息删除 → SET NULL
5. 3 组件公开方法签名不变
6. 同一连接内可做事务
7. 只保留 CS_DB_PATH 环境变量

### Step 2: test-plan

/dev-loop-skills:skill-2-test-plan-generator
# 输入: eval-doc + plan/08-db-consolidation.md 的 test-plan 表
# 产出: .artifacts/test-plans/cs-plan-db-consolidation.md

| # | 测试名 | 类型 | 验证点 |
|---|--------|------|--------|
| 1 | test_init_db_creates_all_tables | unit | 5 张表全部存在 |
| 2 | test_foreign_keys_enabled | unit | PRAGMA foreign_keys = 1 |
| 3 | test_cascade_delete_participants | unit | 删对话 → participants 删除 |
| 4 | test_cascade_delete_resolutions | unit | 删对话 → resolutions 删除 |
| 5 | test_cascade_delete_messages | unit | 删对话 → messages 删除 |
| 6 | test_events_set_null_on_delete | unit | 删对话 → events.conversation_id = NULL |
| 7 | test_edit_of_set_null | unit | 删原消息 → edit_of = NULL |
| 8 | test_shared_connection | unit | 3 组件共享连接，互相可见写入 |
| 9 | test_fk_rejects_invalid_conv_id | unit | FK 阻止插入不存在的 conversation_id |
| 10 | test_full_lifecycle_single_db | E2E | create → message → resolve → close 全链路 |
| 11 | test_240_regression | regression | 回归全部 PASS |

### Step 3: test-code

/dev-loop-skills:skill-3-test-code-writer
# 产出:
#   tests/unit/test_db_consolidation.py (9 unit)
#   tests/e2e/test_db_lifecycle.py (1 E2E)

### Step 4: TDD 实现

必须先读 spec `docs/discuss/spec/channel-server/11-db-consolidation.md` 了解目标 schema。

按顺序实现:

1. **新建 engine/db.py** (~50行)
   - init_db(path) → Connection，建 5 表 + 索引 + PRAGMA
   - 目标 schema 见 spec

2. **改造 engine/conversation_manager.py**
   - __init__ 改为 (conn: sqlite3.Connection, ...)
   - 删除内部 _create_tables()
   - 其余代码不变（已经用 self._conn.execute）

3. **改造 engine/event_bus.py**
   - __init__ 改为 (conn: sqlite3.Connection)
   - 删除内部 _create_tables()

4. **改造 engine/message_store.py**
   - __init__ 改为 (conn: sqlite3.Connection)
   - 删除内部 _create_tables()

5. **改造 server.py build_components()**
   - 删除 CS_EVENT_DB_PATH / CS_MESSAGE_DB_PATH（L52-56）
   - 新增: from engine.db import init_db; conn = init_db(CS_DB_PATH)
   - 3 个组件传 conn

6. **改造测试 fixtures**（最多的工作量）
   读取当前测试文件了解各自如何创建 store：
   - tests/unit/test_conversation_manager.py — fixture 用 tmp_path
   - tests/unit/test_event_bus.py — fixture 用 tmp_path
   - tests/unit/test_message_store.py — fixture 用 tmp_path
   - tests/unit/test_command_handlers.py — monkeypatch DB env vars
   - tests/unit/test_review_command.py — monkeypatch DB env vars
   - tests/e2e/conftest.py — 3 个 DB env vars
   - tests/e2e/test_routing.py, test_sla_timers.py 等 — 3 个 DB env vars
   全部改为: init_db(tmp_path / "test.db") → 传 conn 或设单个 CS_DB_PATH

注册: /dev-loop-skills:skill-6-artifact-registry register --type code-diff --id cs-diff-db-consolidation

## 约束

- engine/ 组件公开方法签名（create/query/publish/save 等）不变
- protocol/ bridge_api/ transport/ feishu_bridge/ 全部 0 改动
- 不做数据迁移脚本（无生产数据）
- 不引入 ORM
- 回归: 所有已有测试必须 PASS

### Step 5: test-run

/dev-loop-skills:skill-4-test-runner
# 新增: uv run pytest tests/unit/test_db_consolidation.py tests/e2e/test_db_lifecycle.py -v
# 回归: uv run pytest tests/ feishu_bridge/tests/ -v
# Expected: 250+ passed (240 existing + 10 new), 0 failed

### Step 6: artifact registry

/dev-loop-skills:skill-6-artifact-registry register --type e2e-report --id cs-report-db-consolidation

## 闭环完成标志

1. .artifacts/ 下 4 个 artifact: cs-eval/plan/diff/report-db-consolidation，全部 confirmed
2. registry.json 从 44 → 48 artifacts
3. 运行时只生成 1 个 conversations.db（无 _events.db / _messages.db）
4. 回归 240+ tests 全部 PASS + 新增 10+ tests PASS

## 提交

```bash
git add engine/db.py engine/conversation_manager.py engine/event_bus.py \
        engine/message_store.py server.py \
        tests/unit/test_db_consolidation.py tests/e2e/test_db_lifecycle.py \
        tests/ .artifacts/
git commit -m "refactor: SQLite 合并 — 3 文件 → 1 文件 5 表 + FK + CASCADE"
```
```
