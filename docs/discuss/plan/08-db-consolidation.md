# Plan: SQLite 数据库合并

> Phase 4.6 补丁 — engine 层数据库重构
> Spec: `spec/channel-server/11-db-consolidation.md`

## 概览

| 项 | 值 |
|-----|-----|
| 分支 | `fix/db-consolidation`（从 `refactor/channel-server` 创建） |
| 影响范围 | engine/ + server.py + tests/ |
| 新增文件 | `engine/db.py` |
| 修改文件 | 3 engine 组件 + server.py + ~10 test 文件 |
| 零改动 | protocol/ bridge_api/ transport/ feishu_bridge/ |
| 预计代码量 | ~200 行修改 |

## Dev-loop 闭环

Artifact ID 前缀: `cs-*-db-consolidation`

### Step 1: eval-doc

```
/dev-loop-skills:skill-5-feature-eval simulate
# 主题: "SQLite 数据库合并 — 3 文件 → 1 文件 5 表 + FK + CASCADE"
# 产出: .artifacts/eval-docs/cs-eval-db-consolidation.md
```

行为预期:
1. 单一 conversations.db 包含 5 张表（conversations, participants, resolutions, events, messages）
2. PRAGMA foreign_keys = ON 生效
3. 删除 conversation → participants/resolutions/messages CASCADE 删除，events.conversation_id SET NULL
4. messages.edit_of 引用的原消息删除 → edit_of SET NULL（保留编辑版本）
5. ConversationManager/EventBus/MessageStore 公开方法签名不变
6. resolve() + event_bus.publish() 在同一连接内可用事务包裹
7. CS_EVENT_DB_PATH / CS_MESSAGE_DB_PATH 环境变量移除，只保留 CS_DB_PATH

### Step 2: test-plan

```
/dev-loop-skills:skill-2-test-plan-generator
# 输入: eval-doc + spec/11-db-consolidation.md
# 产出: .artifacts/test-plans/cs-plan-db-consolidation.md
```

| # | 测试名 | 类型 | 验证点 |
|---|--------|------|--------|
| 1 | test_init_db_creates_all_tables | unit | init_db() 建 5 张表 |
| 2 | test_foreign_keys_enabled | unit | PRAGMA foreign_keys 返回 1 |
| 3 | test_cascade_delete_participants | unit | 删对话 → participants 自动删除 |
| 4 | test_cascade_delete_resolutions | unit | 删对话 → resolutions 自动删除 |
| 5 | test_cascade_delete_messages | unit | 删对话 → messages 自动删除 |
| 6 | test_events_set_null_on_delete | unit | 删对话 → events.conversation_id 变 NULL |
| 7 | test_edit_of_set_null | unit | 删原消息 → 编辑版本 edit_of 变 NULL |
| 8 | test_shared_connection_three_components | unit | 3 组件共享同一连接，互相可见对方写入 |
| 9 | test_invalid_conversation_id_rejected | unit | FK 约束阻止插入不存在的 conversation_id |
| 10 | test_full_lifecycle_single_db | E2E | create → message → resolve → close → 验证所有表一致 |
| 11 | test_existing_240_tests_pass | regression | 回归 240 tests 全部 PASS |

### Step 3: test-code

```
/dev-loop-skills:skill-3-test-code-writer
# 产出:
#   tests/unit/test_db_consolidation.py (9 个 unit)
#   tests/e2e/test_db_lifecycle.py (1 个 E2E)
```

### Step 4: TDD 实现

按顺序:

1. **新建 `engine/db.py`**（~50行）
   - `init_db(path: str) -> sqlite3.Connection`
   - 建 5 张表 + 索引 + PRAGMA

2. **改造 `engine/conversation_manager.py`**
   - `__init__(self, conn: sqlite3.Connection, ...)` — 移除 `_create_tables()`
   - 所有 `self._conn.execute(...)` 不变（已经是 sqlite3 操作）

3. **改造 `engine/event_bus.py`**
   - `__init__(self, conn: sqlite3.Connection)` — 移除 `_create_tables()`

4. **改造 `engine/message_store.py`**
   - `__init__(self, conn: sqlite3.Connection)` — 移除 `_create_tables()`

5. **改造 `server.py` build_components()**
   - 删除 CS_EVENT_DB_PATH / CS_MESSAGE_DB_PATH
   - `conn = init_db(CS_DB_PATH)` → 传给 3 个组件

6. **改造测试 fixtures**
   - unit tests: `tmp_path / "test.db"` → `init_db()` → 传 conn
   - e2e conftest: 3 个 DB env var → 1 个
   - e2e test files (test_routing.py, test_sla_timers.py 等): 同上

```
/dev-loop-skills:skill-6-artifact-registry register --type code-diff --id cs-diff-db-consolidation
```

### Step 5: test-run

```
/dev-loop-skills:skill-4-test-runner
# 新增: uv run pytest tests/unit/test_db_consolidation.py tests/e2e/test_db_lifecycle.py -v
# 回归: uv run pytest tests/ feishu_bridge/tests/ -v
# Expected: 240+ passed, 0 failed
```

### Step 6: artifact registry

```
/dev-loop-skills:skill-6-artifact-registry register --type e2e-report --id cs-report-db-consolidation
```

## 闭环完成标志

1. `.artifacts/` 下 4 个 artifact: cs-eval/plan/diff/report-db-consolidation
2. registry.json 更新（44 → 48 artifacts）
3. 只生成 1 个 `conversations.db` 文件（不再有 `_events.db` / `_messages.db`）
4. 回归 240+ tests 全部 PASS + 新增 10+ tests PASS

## 提交

```bash
git add engine/db.py engine/conversation_manager.py engine/event_bus.py \
        engine/message_store.py server.py \
        tests/unit/test_db_consolidation.py tests/e2e/test_db_lifecycle.py \
        tests/ .artifacts/
git commit -m "refactor: SQLite 合并 — 3 文件 → 1 文件 5 表 + FK + CASCADE"
```
