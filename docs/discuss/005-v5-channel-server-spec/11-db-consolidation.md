# Spec: SQLite 数据库合并

> channel-server engine 层数据库重构 — 3 文件 → 1 文件 5 表

## 问题

当前 3 个 engine 组件各持独立 SQLite 文件：

| 组件 | 文件 | 表 |
|------|------|-----|
| ConversationManager | conversations.db | conversations, participants, resolutions |
| EventBus | conversations_events.db | events |
| MessageStore | conversations_messages.db | messages |

所有表通过 `conversation_id` 强关联，但跨文件无法建外键。

### 具体风险

1. **孤儿数据** — 删对话后 events/messages 永久残留，无 CASCADE
2. **事务不一致** — `resolve()` 写 conversations.db → `event_bus.publish()` 写 events.db，中间 crash 状态分裂
3. **无 FK 约束** — 即使 conversations.db 内部，participants/resolutions 也没有 FK
4. **edit 链断裂** — messages.edit_of 引用同表 message ID 但无 FK

## 目标 Schema

```sql
-- 单一数据库: conversations.db
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'created',
    mode TEXT NOT NULL DEFAULT 'auto',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE participants (
    conversation_id TEXT NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    participant_id TEXT NOT NULL,
    role TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (conversation_id, participant_id)
);

CREATE TABLE resolutions (
    conversation_id TEXT PRIMARY KEY
        REFERENCES conversations(id) ON DELETE CASCADE,
    outcome TEXT NOT NULL,
    resolved_by TEXT NOT NULL,
    csat_score INTEGER,
    timestamp TEXT NOT NULL
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    conversation_id TEXT
        REFERENCES conversations(id) ON DELETE SET NULL,
    data TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL
);
CREATE INDEX idx_events_conv ON events(conversation_id, timestamp);
CREATE INDEX idx_events_type ON events(type, timestamp);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'public',
    timestamp TEXT NOT NULL,
    edit_of TEXT
        REFERENCES messages(id) ON DELETE SET NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_messages_conv ON messages(conversation_id, timestamp);
```

## CASCADE 策略

| 关系 | 策略 | 原因 |
|------|------|------|
| participants → conversations | CASCADE | 对话删除 = 参与者记录无意义 |
| resolutions → conversations | CASCADE | 对话删除 = 解决记录无意义 |
| events → conversations | SET NULL | 事件是审计日志，保留但解除关联 |
| messages → conversations | CASCADE | 对话删除 = 消息无意义 |
| messages.edit_of → messages | SET NULL | 被编辑的原消息删除时保留编辑版本 |

## 架构变更

### 新建: `engine/db.py`

统一数据库初始化模块：

```python
def init_db(path: str) -> sqlite3.Connection:
    """创建/打开数据库，建表，启用 WAL + FK。返回共享连接。"""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _create_tables(conn)
    return conn
```

### 改造: 3 个 engine 组件

构造函数从接收 `db_path: str` 改为接收 `conn: sqlite3.Connection`：

```python
# Before
class ConversationManager:
    def __init__(self, db_path: str, ...):
        self._conn = sqlite3.connect(db_path)
        self._create_tables()

# After
class ConversationManager:
    def __init__(self, conn: sqlite3.Connection, ...):
        self._conn = conn  # 共享连接，db.py 已建表
```

EventBus 和 MessageStore 同理。

### 改造: `server.py` build_components()

```python
# Before (3 paths, 3 connections)
event_bus = EventBus(CS_EVENT_DB_PATH)
conversation_manager = ConversationManager(CS_DB_PATH)
message_store = MessageStore(CS_MESSAGE_DB_PATH)

# After (1 path, 1 connection, 共享)
from engine.db import init_db
conn = init_db(CS_DB_PATH)
event_bus = EventBus(conn)
conversation_manager = ConversationManager(conn)
message_store = MessageStore(conn)
```

环境变量从 3 个缩减为 1 个：
- 保留: `CS_DB_PATH`（默认 `conversations.db`）
- 删除: `CS_EVENT_DB_PATH`, `CS_MESSAGE_DB_PATH`

## 约束

- engine 组件的**公开方法签名不变**（create/query/publish/save 等）
- server.py handler 逻辑不变
- protocol/ bridge_api/ transport/ feishu_bridge/ 零改动
- 所有现有测试修改后继续 PASS

## 不做的事

- 数据迁移脚本 — 当前无生产数据，新建即可
- 连接池 — SQLite 单连接 + WAL 足够当前规模
- ORM — 保持原始 sqlite3，不引入 SQLAlchemy
