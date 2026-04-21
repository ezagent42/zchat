# Channel-Server v1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Dev-loop methodology:** Each Task Group = one dev-loop-skill closure (eval-doc → test-plan → test-code → implement → test-run → merge).

**Goal:** Implement channel-server v1.0 as a generic conversation protocol with mode control, message gating, and multi-role Bridge API.

**Architecture:** Protocol primitives (pure Python, zero deps) → Engine runtime (asyncio + SQLite) → Transport adapters (IRC + Bridge WebSocket). Each layer is a separate worktree enabling parallel development.

**Tech Stack:** Python 3.11+ · pytest + pytest-asyncio · SQLite · websockets · irc ≥20.0 · mcp[cli] ≥1.2.0

**Repos:** `zchat-channel-server` (main work) · `zchat` (CLI config + E2E tests)

---

## Development Model

```
每个 Task Group = 一个 dev-loop-skill 闭环:

  ┌─ eval-doc ──────────────────────────────┐
  │  功能提案 (skill-5:feature-eval simulate)│
  └──────────┬──────────────────────────────┘
             │
  ┌──────────▼──────────────────────────────┐
  │  test-plan (skill-2:test-plan-generator) │
  └──────────┬──────────────────────────────┘
             │
  ┌──────────▼──────────────────────────────┐
  │  test-code (skill-3:test-code-writer)    │
  └──────────┬──────────────────────────────┘
             │
  ┌──────────▼──────────────────────────────┐
  │  implement (TDD: red → green → refactor) │
  └──────────┬──────────────────────────────┘
             │
  ┌──────────▼──────────────────────────────┐
  │  test-run (skill-4:test-runner)          │
  │  unit → e2e → (pre-release for final)    │
  └──────────┬──────────────────────────────┘
             │
         merge to main
```

---

## Worktree Topology & Dependency Graph

```
                    ┌─────────────┐
                    │  Phase 0    │
                    │ Infra Setup │
                    │ (main)      │
                    └──────┬──────┘
                           │
              ┌─────────────┬────────────┐
              ▼             ▼            │
        ┌──────────┐  ┌──────────┐      │ (Phase 0 dev-loop bootstrap
        │ WT-1     │  │ WT-5     │      │  在 main 上执行，不需要 worktree)
        │ protocol/│  │ zchat CLI│      │
        │          │  │ config   │      │
        └────┬─────┘  └──────────┘      │
             │ merge
        ┌────▼─────────────────────┐
        │                          │
   ┌────▼─────┐           ┌───────▼────┐
   │ WT-2     │           │ WT-3       │
   │ engine/  │           │ bridge_api/│
   │          │           │            │
   └────┬─────┘           └───────┬────┘
        │ merge                   │ merge
        ├─────────────────────────┤
        │                         │
   ┌────▼─────────────────────────▼────┐
   │ WT-4                              │
   │ transport/ + server.py refactor   │
   │ + integration                     │
   └──────────────┬────────────────────┘
                  │ merge
   ┌──────────────▼────────────────────┐
   │ Phase Final                        │
   │ E2E + Pre-release                 │
   │ (main)                            │
   └───────────────────────────────────┘
```

**并行开发可能性：**
- WT-1 (protocol) + WT-5 (zchat CLI): 完全并行（Phase 0 在 main 上先完成 dev-loop bootstrap）
- WT-2 (engine) + WT-3 (bridge_api): protocol merge 后可并行
- WT-4 (transport + server): 等 engine + bridge_api merge 后

---

## Testing Architecture

```
zchat-channel-server/
├── tests/
│   ├── unit/                    # 纯逻辑测试，无外部依赖
│   │   ├── test_conversation.py # Conversation CRUD + 状态机
│   │   ├── test_mode.py         # Mode 转换 + 验证
│   │   ├── test_gate.py         # Gate 算法 (核心!)
│   │   ├── test_timer.py        # Timer 设置/取消/超时
│   │   ├── test_commands.py     # 命令解析
│   │   ├── test_event_bus.py    # 事件发布/订阅/持久化
│   │   ├── test_message_store.py# 消息存储/编辑/查询
│   │   └── test_conversation_manager.py  # 并发上限/参与者管理
│   ├── e2e/                     # 需要 IRC server + Bridge
│   │   ├── conftest.py          # ergo fixture + bridge fixture
│   │   ├── test_conversation_lifecycle.py # 创建→激活→idle→关闭
│   │   ├── test_mode_switching.py         # auto→copilot→takeover 全流程
│   │   ├── test_bridge_api.py             # Bridge 连接/消息/命令
│   │   └── test_gate_enforcement.py       # Gate 实际拦截验证
│   └── pre_release/             # 真实渠道端到端
│       ├── walkthrough.sh       # asciinema 录制
│       └── feishu_e2e.py        # 飞书真实消息收发验证
│
│ (zchat 主仓库的测试)
zchat/tests/
├── unit/test_config_channel_server.py  # config.toml 新段
└── e2e/test_channel_server_integration.py  # zchat + channel-server 集成

测试命令:
  cd zchat-channel-server && uv run pytest tests/unit/ -v           # Unit
  cd zchat-channel-server && uv run pytest tests/e2e/ -v -m e2e     # E2E
  cd zchat && uv run pytest tests/unit/ -v                           # zchat Unit
  cd zchat && uv run pytest tests/e2e/ -v -m e2e                     # zchat E2E
  ./tests/pre_release/walkthrough.sh                                 # Pre-release
```

---

## Phase 0: Infrastructure Setup (main branch, 不需要 worktree)

### Task 0.1: channel-server 测试基础设施

**Files:**
- Create: `zchat-channel-server/tests/__init__.py`
- Create: `zchat-channel-server/tests/unit/__init__.py`
- Create: `zchat-channel-server/tests/e2e/__init__.py`
- Create: `zchat-channel-server/tests/e2e/conftest.py`
- Create: `zchat-channel-server/pytest.ini`
- Modify: `zchat-channel-server/pyproject.toml`
- Move: `zchat-channel-server/tests/test_channel_server.py` → `tests/unit/test_message.py`

- [ ] **Step 1: 创建测试目录结构**

```bash
cd zchat-channel-server
mkdir -p tests/unit tests/e2e tests/pre_release
touch tests/__init__.py tests/unit/__init__.py tests/e2e/__init__.py
```

- [ ] **Step 2: 移动现有测试到 unit/**

```bash
# 现有 12 个测试在 tests/test_channel_server.py
# 拆分为按模块的测试文件
mv tests/test_channel_server.py tests/unit/test_message.py
```

修改 `tests/unit/test_message.py` 开头的导入：
```python
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from message import detect_mention, clean_mention, chunk_message
```

把 `test_sys_message_*` 和 `test_load_instructions_*` 测试移到单独文件 `tests/unit/test_legacy.py`。

- [ ] **Step 3: 创建 pytest.ini**

```ini
[pytest]
testpaths = tests
markers =
    e2e: end-to-end tests requiring ergo + channel-server
    prerelease: pre-release acceptance tests
asyncio_mode = auto
```

- [ ] **Step 4: 更新 pyproject.toml 依赖**

```toml
[project]
name = "zchat-channel-server"
version = "1.0.0-dev"
dependencies = [
    "mcp[cli]>=1.2.0",
    "irc>=20.0",
    "zchat-protocol>=0.1.0",
    "websockets>=12.0",
]

[project.optional-dependencies]
test = [
    "pytest>=9.0.2",
    "pytest-asyncio>=0.23.0",
    "pytest-order>=1.3.0",
    "pytest-timeout",
]

[tool.hatch.build.targets.wheel]
packages = ["protocol", "engine", "transport", "bridge_api", "."]
only-include = [
    "server.py", "message.py", "instructions.md",
    "protocol/", "engine/", "transport/", "bridge_api/",
]
```

- [ ] **Step 5: 验证现有测试仍然通过**

```bash
cd zchat-channel-server && uv run pytest tests/unit/ -v
```

Expected: 12 tests PASS (和之前一样)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: restructure tests into unit/e2e/pre_release layers"
```

### Task 0.2: dev-loop-skills bootstrap (channel-server 仓库)

**Files:**
- Create: `zchat-channel-server/.artifacts/` 目录结构
- Create: `zchat-channel-server/.claude/skills/project-discussion-channel-server/`

- [ ] **Step 1: 在 channel-server 仓库运行 skill-0 bootstrap**

```
使用 /dev-loop-skills:skill-0-project-builder 对 zchat-channel-server 仓库进行 bootstrap。
这会生成 .artifacts/ 目录和 skill-1 (project-discussion) 知识库。
```

- [ ] **Step 2: 验证 dev-loop 可用**

```
使用 skill-1 查询: "channel-server 当前有哪些 MCP tools?"
预期: 返回 reply + join_channel 两个 tools 的信息
```

- [ ] **Step 3: Commit**

```bash
git add .artifacts/ .claude/skills/
git commit -m "chore: bootstrap dev-loop-skills for channel-server"
```

---

## Phase 1: Protocol Module (WT-1, 独立 worktree)

**Worktree:** `zchat-channel-server-protocol`
**Branch:** `feat/protocol-primitives`
**依赖:** 无（纯 Python，零外部依赖）
**可并行:** 是

### Dev-loop closure:

```
eval-doc:  "添加通用对话协议原语层（Conversation/Mode/Gate/Timer/Event/Command）"
test-plan: 8 个 unit test 文件覆盖全部原语
test-code: 先写测试（TDD）
implement: 实现 protocol/ 目录下 8 个文件
test-run:  uv run pytest tests/unit/test_protocol_*.py -v
```

### Task 1.1: protocol/conversation.py + 测试

**Files:**
- Create: `protocol/__init__.py`
- Create: `protocol/conversation.py`
- Test: `tests/unit/test_conversation.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_conversation.py
import pytest
from protocol.conversation import (
    Conversation, ConversationState, ConversationResolution,
    create_conversation, transition_state, VALID_STATE_TRANSITIONS,
)

def test_create_conversation():
    conv = create_conversation("feishu_oc_abc", metadata={"source": "feishu"})
    assert conv.id == "feishu_oc_abc"
    assert conv.state == ConversationState.CREATED
    assert conv.metadata["source"] == "feishu"

def test_activate():
    conv = create_conversation("test_1")
    transition_state(conv, ConversationState.ACTIVE)
    assert conv.state == ConversationState.ACTIVE

def test_idle_and_reactivate():
    conv = create_conversation("test_2")
    transition_state(conv, ConversationState.ACTIVE)
    transition_state(conv, ConversationState.IDLE)
    assert conv.state == ConversationState.IDLE
    transition_state(conv, ConversationState.ACTIVE)  # reactivate
    assert conv.state == ConversationState.ACTIVE

def test_resolve_directly_from_active():
    conv = create_conversation("test_3")
    transition_state(conv, ConversationState.ACTIVE)
    transition_state(conv, ConversationState.CLOSED)  # /resolve path
    assert conv.state == ConversationState.CLOSED

def test_invalid_transition_raises():
    conv = create_conversation("test_4")
    with pytest.raises(ValueError, match="Invalid state transition"):
        transition_state(conv, ConversationState.IDLE)  # created → idle 不合法

def test_resolution():
    conv = create_conversation("test_5")
    transition_state(conv, ConversationState.ACTIVE)
    conv.resolution = ConversationResolution(
        outcome="resolved", resolved_by="xiaoli", csat_score=5
    )
    assert conv.resolution.outcome == "resolved"
    assert conv.resolution.csat_score == 5
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd zchat-channel-server && uv run pytest tests/unit/test_conversation.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'protocol'`

- [ ] **Step 3: 实现 protocol/conversation.py**

```python
# protocol/__init__.py
"""Channel-Server Protocol — 通用对话协作协议原语"""

# protocol/conversation.py
"""Conversation 数据模型和状态机。"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ConversationState(Enum):
    CREATED = "created"
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


VALID_STATE_TRANSITIONS = {
    (ConversationState.CREATED, ConversationState.ACTIVE),
    (ConversationState.ACTIVE, ConversationState.IDLE),
    (ConversationState.ACTIVE, ConversationState.CLOSED),   # /resolve
    (ConversationState.IDLE, ConversationState.ACTIVE),     # reactivate
    (ConversationState.IDLE, ConversationState.CLOSED),     # timeout or /abandon
}


@dataclass
class ConversationResolution:
    outcome: str          # "resolved" | "abandoned" | "escalated"
    resolved_by: str
    csat_score: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Conversation:
    id: str
    state: ConversationState = ConversationState.CREATED
    mode: str = "auto"  # 由 mode.py 管理，这里只存值
    participants: list = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
    resolution: Optional[ConversationResolution] = None


def create_conversation(conversation_id: str, metadata: dict = None) -> Conversation:
    return Conversation(id=conversation_id, metadata=metadata or {})


def transition_state(conv: Conversation, new_state: ConversationState) -> None:
    if (conv.state, new_state) not in VALID_STATE_TRANSITIONS:
        raise ValueError(
            f"Invalid state transition: {conv.state.value} → {new_state.value}"
        )
    conv.state = new_state
    conv.updated_at = datetime.now()
```

- [ ] **Step 4: 运行测试通过**

```bash
cd zchat-channel-server && uv run pytest tests/unit/test_conversation.py -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add protocol/ tests/unit/test_conversation.py
git commit -m "feat(protocol): Conversation data model + state machine"
```

### Task 1.2: protocol/participant.py + 测试

**Files:**
- Create: `protocol/participant.py`
- Test: `tests/unit/test_participant.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_participant.py
from protocol.participant import Participant, ParticipantRole

def test_create_customer():
    p = Participant(id="feishu_ou_david", role=ParticipantRole.CUSTOMER)
    assert p.role == ParticipantRole.CUSTOMER

def test_create_agent():
    p = Participant(id="fast-agent", role=ParticipantRole.AGENT)
    assert p.role == ParticipantRole.AGENT

def test_create_operator():
    p = Participant(id="xiaoli", role=ParticipantRole.OPERATOR)
    assert p.role == ParticipantRole.OPERATOR

def test_roles_are_distinct():
    roles = set(ParticipantRole)
    assert len(roles) == 4  # customer, agent, operator, observer
```

- [ ] **Step 2: 运行测试确认失败** → **Step 3: 实现**

```python
# protocol/participant.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ParticipantRole(Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    OPERATOR = "operator"
    OBSERVER = "observer"


@dataclass
class Participant:
    id: str
    role: ParticipantRole
    joined_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
```

- [ ] **Step 4: 运行测试通过** → **Step 5: Commit**

```bash
git commit -m "feat(protocol): Participant + ParticipantRole"
```

### Task 1.3: protocol/mode.py + 测试

**Files:**
- Create: `protocol/mode.py`
- Test: `tests/unit/test_mode.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_mode.py
import pytest
from protocol.mode import (
    ConversationMode, ModeTransition, 
    validate_transition, VALID_MODE_TRANSITIONS,
)

def test_auto_to_copilot():
    t = validate_transition(ConversationMode.AUTO, ConversationMode.COPILOT, 
                           trigger="operator_joined", triggered_by="xiaoli")
    assert t.from_mode == ConversationMode.AUTO
    assert t.to_mode == ConversationMode.COPILOT

def test_copilot_to_takeover():
    t = validate_transition(ConversationMode.COPILOT, ConversationMode.TAKEOVER,
                           trigger="/hijack", triggered_by="xiaoli")
    assert t.trigger == "/hijack"

def test_takeover_to_auto():
    validate_transition(ConversationMode.TAKEOVER, ConversationMode.AUTO,
                       trigger="/release", triggered_by="xiaoli")

def test_auto_to_auto_invalid():
    with pytest.raises(ValueError, match="Invalid mode transition"):
        validate_transition(ConversationMode.AUTO, ConversationMode.AUTO,
                           trigger="noop", triggered_by="test")

def test_all_valid_transitions_count():
    assert len(VALID_MODE_TRANSITIONS) == 6
```

- [ ] **Step 2: 运行失败** → **Step 3: 实现**

```python
# protocol/mode.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ConversationMode(Enum):
    AUTO = "auto"
    COPILOT = "copilot"
    TAKEOVER = "takeover"


VALID_MODE_TRANSITIONS = {
    (ConversationMode.AUTO, ConversationMode.COPILOT),
    (ConversationMode.AUTO, ConversationMode.TAKEOVER),
    (ConversationMode.COPILOT, ConversationMode.TAKEOVER),
    (ConversationMode.COPILOT, ConversationMode.AUTO),
    (ConversationMode.TAKEOVER, ConversationMode.AUTO),
    (ConversationMode.TAKEOVER, ConversationMode.COPILOT),
}


@dataclass
class ModeTransition:
    from_mode: ConversationMode
    to_mode: ConversationMode
    trigger: str
    triggered_by: str
    timestamp: datetime = field(default_factory=datetime.now)


def validate_transition(from_mode: ConversationMode, to_mode: ConversationMode,
                        trigger: str, triggered_by: str) -> ModeTransition:
    if (from_mode, to_mode) not in VALID_MODE_TRANSITIONS:
        raise ValueError(f"Invalid mode transition: {from_mode.value} → {to_mode.value}")
    return ModeTransition(from_mode=from_mode, to_mode=to_mode,
                         trigger=trigger, triggered_by=triggered_by)
```

- [ ] **Step 4: 测试通过** → **Step 5: Commit**

```bash
git commit -m "feat(protocol): ConversationMode + state transitions"
```

### Task 1.4: protocol/message_types.py + protocol/gate.py + 测试

**Files:**
- Create: `protocol/message_types.py`
- Create: `protocol/gate.py`
- Test: `tests/unit/test_gate.py`

- [ ] **Step 1: 写 gate 测试（核心！）**

```python
# tests/unit/test_gate.py
from protocol.message_types import Message, MessageVisibility
from protocol.participant import Participant, ParticipantRole
from protocol.conversation import Conversation, ConversationState
from protocol.mode import ConversationMode
from protocol.gate import gate_message


def _make_conv(mode: ConversationMode) -> Conversation:
    conv = Conversation(id="test", state=ConversationState.ACTIVE)
    conv.mode = mode.value
    return conv

# --- AUTO mode ---

def test_auto_agent_public():
    conv = _make_conv(ConversationMode.AUTO)
    agent = Participant(id="fast-agent", role=ParticipantRole.AGENT)
    result = gate_message(conv, agent, MessageVisibility.PUBLIC)
    assert result == MessageVisibility.PUBLIC

def test_auto_customer_public():
    conv = _make_conv(ConversationMode.AUTO)
    customer = Participant(id="david", role=ParticipantRole.CUSTOMER)
    result = gate_message(conv, customer, MessageVisibility.PUBLIC)
    assert result == MessageVisibility.PUBLIC

# --- COPILOT mode ---

def test_copilot_agent_public_passes():
    conv = _make_conv(ConversationMode.COPILOT)
    agent = Participant(id="fast-agent", role=ParticipantRole.AGENT)
    result = gate_message(conv, agent, MessageVisibility.PUBLIC)
    assert result == MessageVisibility.PUBLIC

def test_copilot_operator_public_downgraded_to_side():
    """核心 Gate 行为: copilot 模式下 operator 的 public 消息被降级为 side"""
    conv = _make_conv(ConversationMode.COPILOT)
    operator = Participant(id="xiaoli", role=ParticipantRole.OPERATOR)
    result = gate_message(conv, operator, MessageVisibility.PUBLIC)
    assert result == MessageVisibility.SIDE

# --- TAKEOVER mode ---

def test_takeover_agent_public_downgraded_to_side():
    """核心 Gate 行为: takeover 模式下 agent 的 public 消息被降级为 side"""
    conv = _make_conv(ConversationMode.TAKEOVER)
    agent = Participant(id="fast-agent", role=ParticipantRole.AGENT)
    result = gate_message(conv, agent, MessageVisibility.PUBLIC)
    assert result == MessageVisibility.SIDE

def test_takeover_operator_public_passes():
    conv = _make_conv(ConversationMode.TAKEOVER)
    operator = Participant(id="xiaoli", role=ParticipantRole.OPERATOR)
    result = gate_message(conv, operator, MessageVisibility.PUBLIC)
    assert result == MessageVisibility.PUBLIC

# --- Side/System 不受 gate 影响 ---

def test_explicit_side_stays_side():
    conv = _make_conv(ConversationMode.AUTO)
    agent = Participant(id="fast-agent", role=ParticipantRole.AGENT)
    result = gate_message(conv, agent, MessageVisibility.SIDE)
    assert result == MessageVisibility.SIDE

def test_system_stays_system():
    conv = _make_conv(ConversationMode.TAKEOVER)
    agent = Participant(id="fast-agent", role=ParticipantRole.AGENT)
    result = gate_message(conv, agent, MessageVisibility.SYSTEM)
    assert result == MessageVisibility.SYSTEM
```

- [ ] **Step 2: 运行失败** → **Step 3: 实现**

```python
# protocol/message_types.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class MessageVisibility(Enum):
    PUBLIC = "public"
    SIDE = "side"
    SYSTEM = "system"


@dataclass
class Message:
    id: str
    source: str                          # participant_id
    conversation_id: str
    content: str
    visibility: MessageVisibility = MessageVisibility.PUBLIC
    timestamp: datetime = field(default_factory=datetime.now)
    edit_of: Optional[str] = None
    metadata: dict = field(default_factory=dict)
```

```python
# protocol/gate.py
"""Message Gate — 根据 mode + role 决定消息最终 visibility。"""
from protocol.conversation import Conversation
from protocol.mode import ConversationMode
from protocol.participant import Participant, ParticipantRole
from protocol.message_types import MessageVisibility


def gate_message(conversation: Conversation, sender: Participant,
                 requested_visibility: MessageVisibility) -> MessageVisibility:
    """决定消息最终 visibility。这是 mechanism，不是 convention。"""
    if requested_visibility in (MessageVisibility.SYSTEM, MessageVisibility.SIDE):
        return requested_visibility

    mode = ConversationMode(conversation.mode)
    role = sender.role

    if mode == ConversationMode.AUTO:
        return MessageVisibility.PUBLIC

    if mode == ConversationMode.COPILOT:
        if role == ParticipantRole.OPERATOR:
            return MessageVisibility.SIDE
        return MessageVisibility.PUBLIC

    if mode == ConversationMode.TAKEOVER:
        if role == ParticipantRole.AGENT:
            return MessageVisibility.SIDE
        return MessageVisibility.PUBLIC

    return requested_visibility
```

- [ ] **Step 4: 测试通过** → **Step 5: Commit**

```bash
git commit -m "feat(protocol): Message + MessageVisibility + Gate algorithm"
```

### Task 1.5: protocol/event.py + protocol/timer.py + protocol/commands.py

**Files:**
- Create: `protocol/event.py`
- Create: `protocol/timer.py`
- Create: `protocol/commands.py`
- Test: `tests/unit/test_event.py`
- Test: `tests/unit/test_commands.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_event.py
from protocol.event import Event, EventType

def test_event_creation():
    e = Event(type=EventType.CONVERSATION_CREATED, conversation_id="test_1",
              data={"source": "feishu"})
    assert e.type == EventType.CONVERSATION_CREATED
    assert e.id  # auto-generated UUID

def test_event_types_complete():
    # 确保所有需要的事件类型都定义了
    required = [
        "CONVERSATION_CREATED", "CONVERSATION_ACTIVATED", "CONVERSATION_CLOSED",
        "CONVERSATION_RESOLVED", "MODE_CHANGED", "MESSAGE_SENT", "MESSAGE_EDITED",
        "MESSAGE_GATED", "PARTICIPANT_JOINED", "PARTICIPANT_LEFT",
        "TIMER_SET", "TIMER_EXPIRED", "SLA_BREACH",
    ]
    for name in required:
        assert hasattr(EventType, name), f"Missing EventType.{name}"
```

```python
# tests/unit/test_commands.py
from protocol.commands import parse_command, Command

def test_parse_hijack():
    cmd = parse_command("/hijack")
    assert cmd.name == "hijack"
    assert cmd.args == {}

def test_parse_dispatch_with_args():
    cmd = parse_command("/dispatch feishu_oc_abc deep-agent")
    assert cmd.name == "dispatch"
    assert cmd.args["conversation_id"] == "feishu_oc_abc"
    assert cmd.args["agent_nick"] == "deep-agent"

def test_parse_status():
    cmd = parse_command("/status")
    assert cmd.name == "status"

def test_parse_resolve():
    cmd = parse_command("/resolve")
    assert cmd.name == "resolve"

def test_parse_assign():
    cmd = parse_command("/assign fast-agent xiaoli")
    assert cmd.name == "assign"
    assert cmd.args["agent_nick"] == "fast-agent"
    assert cmd.args["operator_id"] == "xiaoli"

def test_non_command_returns_none():
    assert parse_command("hello world") is None

def test_unknown_command_returns_unknown():
    cmd = parse_command("/foobar")
    assert cmd.name == "unknown"
```

- [ ] **Step 2: 运行失败** → **Step 3: 实现 event.py + timer.py + commands.py**

```python
# protocol/event.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class EventType(Enum):
    CONVERSATION_CREATED = "conversation.created"
    CONVERSATION_ACTIVATED = "conversation.activated"
    CONVERSATION_IDLED = "conversation.idled"
    CONVERSATION_REACTIVATED = "conversation.reactivated"
    CONVERSATION_CLOSED = "conversation.closed"
    CONVERSATION_RESOLVED = "conversation.resolved"
    CONVERSATION_CSAT_RECORDED = "conversation.csat_recorded"
    PARTICIPANT_JOINED = "participant.joined"
    PARTICIPANT_LEFT = "participant.left"
    MODE_CHANGED = "mode.changed"
    MESSAGE_SENT = "message.sent"
    MESSAGE_EDITED = "message.edited"
    MESSAGE_GATED = "message.gated"
    MESSAGE_DELETED = "message.deleted"
    TIMER_SET = "timer.set"
    TIMER_EXPIRED = "timer.expired"
    TIMER_CANCELLED = "timer.cancelled"
    SLA_BREACH = "sla.breach"
    SQUAD_ASSIGNED = "squad.assigned"
    SQUAD_REASSIGNED = "squad.reassigned"


@dataclass
class Event:
    type: EventType
    conversation_id: str
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: uuid4().hex[:12])
```

```python
# protocol/timer.py
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class TimerAction:
    type: str       # "mode_change" | "state_change" | "system_message" | "event"
    params: dict = field(default_factory=dict)


@dataclass
class Timer:
    conversation_id: str
    name: str
    duration: timedelta
    on_expire: TimerAction
    started_at: datetime = field(default_factory=datetime.now)
    cancelled: bool = False
```

```python
# protocol/commands.py
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Command:
    name: str
    args: dict = field(default_factory=dict)
    raw: str = ""


COMMAND_DEFINITIONS = {
    "hijack": [],
    "release": [],
    "copilot": [],
    "resolve": [],
    "abandon": [],
    "status": ["conversation_id?"],
    "dispatch": ["conversation_id", "agent_nick"],
    "assign": ["agent_nick", "operator_id"],
    "reassign": ["agent_nick", "from_operator", "to_operator"],
    "squad": [],
}


def parse_command(text: str) -> Optional[Command]:
    if not text.startswith("/"):
        return None
    parts = text.strip().split()
    name = parts[0][1:]  # remove /
    if name not in COMMAND_DEFINITIONS:
        return Command(name="unknown", raw=text)
    
    expected_args = COMMAND_DEFINITIONS[name]
    args = {}
    for i, arg_name in enumerate(expected_args):
        is_optional = arg_name.endswith("?")
        arg_name = arg_name.rstrip("?")
        if i + 1 < len(parts):
            args[arg_name] = parts[i + 1]
        elif not is_optional:
            pass  # missing required arg — handled by caller
    
    return Command(name=name, args=args, raw=text)
```

- [ ] **Step 4: 测试通过** → **Step 5: Commit**

```bash
git commit -m "feat(protocol): Event + Timer + Command definitions"
```

### Task 1.6: protocol/ 完整性验证

- [ ] **Step 1: 运行 protocol/ 全部单元测试**

```bash
cd zchat-channel-server && uv run pytest tests/unit/test_conversation.py tests/unit/test_participant.py tests/unit/test_mode.py tests/unit/test_gate.py tests/unit/test_event.py tests/unit/test_commands.py -v
```

Expected: 全部 PASS (~25 个测试)

- [ ] **Step 2: 使用 dev-loop skill-4 生成测试报告**

```
使用 /dev-loop-skills:skill-4-test-runner 运行全部测试并生成报告
```

- [ ] **Step 3: Merge WT-1 到 main**

```bash
git checkout main
git merge feat/protocol-primitives
```

---

## Phase 2: Engine Module (WT-2, 依赖 Phase 1 merge)

**Worktree:** `zchat-channel-server-engine`
**Branch:** `feat/engine-runtime`
**依赖:** Phase 1 (protocol/) 已 merge
**可并行:** 和 WT-3 (bridge_api/) 并行

### Task 2.1: engine/event_bus.py + 测试

**Files:**
- Create: `engine/__init__.py`
- Create: `engine/event_bus.py`
- Test: `tests/unit/test_event_bus.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_event_bus.py
import asyncio
import tempfile
import pytest
from protocol.event import Event, EventType
from engine.event_bus import EventBus


@pytest.fixture
def event_bus(tmp_path):
    db_path = str(tmp_path / "test_events.db")
    return EventBus(db_path)


@pytest.mark.asyncio
async def test_publish_and_subscribe(event_bus):
    received = []
    event_bus.subscribe(EventType.CONVERSATION_CREATED, 
                       lambda e: received.append(e))
    
    event = Event(type=EventType.CONVERSATION_CREATED, 
                  conversation_id="test_1", data={"source": "feishu"})
    await event_bus.publish(event)
    
    assert len(received) == 1
    assert received[0].conversation_id == "test_1"


@pytest.mark.asyncio
async def test_event_persisted_to_sqlite(event_bus):
    event = Event(type=EventType.MODE_CHANGED, conversation_id="test_2",
                  data={"from": "auto", "to": "copilot"})
    await event_bus.publish(event)
    
    results = event_bus.query(conversation_id="test_2")
    assert len(results) == 1
    assert results[0].type == EventType.MODE_CHANGED


@pytest.mark.asyncio
async def test_query_by_type(event_bus):
    await event_bus.publish(Event(type=EventType.MODE_CHANGED, conversation_id="c1"))
    await event_bus.publish(Event(type=EventType.MESSAGE_SENT, conversation_id="c1"))
    await event_bus.publish(Event(type=EventType.MODE_CHANGED, conversation_id="c2"))
    
    results = event_bus.query(event_type=EventType.MODE_CHANGED)
    assert len(results) == 2
```

- [ ] **Step 2: 运行失败** → **Step 3: 实现 engine/event_bus.py**

```python
# engine/__init__.py
"""Channel-Server Engine — 有状态运行时"""

# engine/event_bus.py
"""事件发布/订阅 + SQLite 持久化。"""
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Callable, Optional
from protocol.event import Event, EventType


class EventBus:
    def __init__(self, db_path: str):
        self._subscribers: dict[EventType, list[Callable]] = defaultdict(list)
        self._db = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                conversation_id TEXT,
                data JSON DEFAULT '{}',
                timestamp TEXT NOT NULL
            )
        """)
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_conv ON events(conversation_id, timestamp)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(type, timestamp)"
        )
        self._db.commit()

    def subscribe(self, event_type: EventType, callback: Callable) -> None:
        self._subscribers[event_type].append(callback)

    async def publish(self, event: Event) -> None:
        self._persist(event)
        for callback in self._subscribers.get(event.type, []):
            try:
                result = callback(event)
                if hasattr(result, '__await__'):
                    await result
            except Exception as e:
                import sys
                print(f"[event_bus] subscriber error: {e}", file=sys.stderr)

    def _persist(self, event: Event):
        self._db.execute(
            "INSERT INTO events (id, type, conversation_id, data, timestamp) VALUES (?, ?, ?, ?, ?)",
            (event.id, event.type.value, event.conversation_id,
             json.dumps(event.data), event.timestamp.isoformat())
        )
        self._db.commit()

    def query(self, conversation_id: str = None, event_type: EventType = None,
              since: datetime = None) -> list[Event]:
        sql = "SELECT id, type, conversation_id, data, timestamp FROM events WHERE 1=1"
        params = []
        if conversation_id:
            sql += " AND conversation_id = ?"
            params.append(conversation_id)
        if event_type:
            sql += " AND type = ?"
            params.append(event_type.value)
        if since:
            sql += " AND timestamp >= ?"
            params.append(since.isoformat())
        sql += " ORDER BY timestamp"
        
        rows = self._db.execute(sql, params).fetchall()
        return [
            Event(id=r[0], type=EventType(r[1]), conversation_id=r[2],
                  data=json.loads(r[3]), timestamp=datetime.fromisoformat(r[4]))
            for r in rows
        ]
```

- [ ] **Step 4: 测试通过** → **Step 5: Commit**

```bash
git commit -m "feat(engine): EventBus with SQLite persistence"
```

### Task 2.2: engine/conversation_manager.py + 测试

**Files:**
- Create: `engine/conversation_manager.py`
- Test: `tests/unit/test_conversation_manager.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_conversation_manager.py
import pytest
from engine.conversation_manager import ConversationManager, ConcurrencyLimitExceeded
from protocol.conversation import ConversationState
from protocol.participant import Participant, ParticipantRole


@pytest.fixture
def manager(tmp_path):
    db_path = str(tmp_path / "test.db")
    return ConversationManager(db_path, max_operator_concurrent=2)


def test_create_and_get(manager):
    conv = manager.create("conv_1", metadata={"source": "web"})
    assert conv.state == ConversationState.CREATED
    fetched = manager.get("conv_1")
    assert fetched.id == "conv_1"


def test_create_idempotent(manager):
    c1 = manager.create("conv_1")
    c2 = manager.create("conv_1")
    assert c1.id == c2.id  # 不重复创建


def test_activate_and_idle(manager):
    manager.create("conv_1")
    manager.activate("conv_1")
    assert manager.get("conv_1").state == ConversationState.ACTIVE
    manager.idle("conv_1")
    assert manager.get("conv_1").state == ConversationState.IDLE


def test_reactivate(manager):
    manager.create("conv_1")
    manager.activate("conv_1")
    manager.idle("conv_1")
    manager.reactivate("conv_1")
    assert manager.get("conv_1").state == ConversationState.ACTIVE


def test_add_participant(manager):
    manager.create("conv_1")
    p = Participant(id="agent1", role=ParticipantRole.AGENT)
    manager.add_participant("conv_1", p)
    conv = manager.get("conv_1")
    assert len(conv.participants) == 1


def test_operator_concurrency_limit(manager):
    manager.create("conv_1")
    manager.create("conv_2")
    manager.create("conv_3")
    op = Participant(id="xiaoli", role=ParticipantRole.OPERATOR)
    manager.add_participant("conv_1", op)
    manager.add_participant("conv_2", op)
    with pytest.raises(ConcurrencyLimitExceeded):
        manager.add_participant("conv_3", op)


def test_resolve(manager):
    manager.create("conv_1")
    manager.activate("conv_1")
    manager.resolve("conv_1", outcome="resolved", resolved_by="xiaoli")
    conv = manager.get("conv_1")
    assert conv.state == ConversationState.CLOSED
    assert conv.resolution.outcome == "resolved"


def test_list_active(manager):
    manager.create("conv_1")
    manager.activate("conv_1")
    manager.create("conv_2")
    manager.activate("conv_2")
    manager.create("conv_3")  # still CREATED, not active
    assert len(manager.list_active()) == 2
```

- [ ] **Step 2: 运行失败** → **Step 3: 实现 engine/conversation_manager.py**

```python
# engine/conversation_manager.py
"""ConversationManager — 对话 CRUD + 状态机 + 并发上限 + SQLite 持久化"""
import json
import sqlite3
from datetime import datetime
from typing import Optional

from protocol.conversation import (
    Conversation, ConversationState, ConversationResolution,
    create_conversation, transition_state,
)
from protocol.participant import Participant, ParticipantRole


class ConcurrencyLimitExceeded(Exception):
    pass


class ConversationManager:
    def __init__(self, db_path: str, max_operator_concurrent: int = 5):
        self._conversations: dict[str, Conversation] = {}
        self._db = sqlite3.connect(db_path)
        self.max_operator_concurrent = max_operator_concurrent
        self._init_db()
        self._load_active()

    def _init_db(self):
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL DEFAULT 'created',
                mode TEXT NOT NULL DEFAULT 'auto',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata JSON DEFAULT '{}'
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                conversation_id TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                role TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                metadata JSON DEFAULT '{}',
                PRIMARY KEY (conversation_id, participant_id)
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS resolutions (
                conversation_id TEXT PRIMARY KEY,
                outcome TEXT NOT NULL,
                resolved_by TEXT NOT NULL,
                csat_score INTEGER,
                timestamp TEXT NOT NULL
            )
        """)
        self._db.commit()

    def _load_active(self):
        rows = self._db.execute(
            "SELECT id, state, mode, created_at, updated_at, metadata FROM conversations WHERE state != 'closed'"
        ).fetchall()
        for r in rows:
            conv = Conversation(
                id=r[0], state=ConversationState(r[1]),
                mode=r[2],
                created_at=datetime.fromisoformat(r[3]),
                updated_at=datetime.fromisoformat(r[4]),
                metadata=json.loads(r[5]),
            )
            self._load_participants(conv)
            self._conversations[conv.id] = conv

    def _load_participants(self, conv: Conversation):
        rows = self._db.execute(
            "SELECT participant_id, role, joined_at, metadata FROM participants WHERE conversation_id = ?",
            (conv.id,)
        ).fetchall()
        conv.participants = [
            Participant(id=r[0], role=ParticipantRole(r[1]),
                       joined_at=datetime.fromisoformat(r[2]),
                       metadata=json.loads(r[3]))
            for r in rows
        ]

    def create(self, conversation_id: str, metadata: dict = None) -> Conversation:
        if conversation_id in self._conversations:
            return self._conversations[conversation_id]
        conv = create_conversation(conversation_id, metadata)
        self._conversations[conversation_id] = conv
        self._db.execute(
            "INSERT OR IGNORE INTO conversations (id, state, mode, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (conv.id, conv.state.value, conv.mode,
             conv.created_at.isoformat(), conv.updated_at.isoformat(),
             json.dumps(conv.metadata))
        )
        self._db.commit()
        return conv

    def get(self, conversation_id: str) -> Optional[Conversation]:
        return self._conversations.get(conversation_id)

    def activate(self, conversation_id: str) -> None:
        conv = self._conversations[conversation_id]
        transition_state(conv, ConversationState.ACTIVE)
        self._persist_state(conv)

    def idle(self, conversation_id: str) -> None:
        conv = self._conversations[conversation_id]
        transition_state(conv, ConversationState.IDLE)
        self._persist_state(conv)

    def reactivate(self, conversation_id: str) -> None:
        conv = self._conversations[conversation_id]
        transition_state(conv, ConversationState.ACTIVE)
        self._persist_state(conv)

    def close(self, conversation_id: str) -> None:
        conv = self._conversations[conversation_id]
        transition_state(conv, ConversationState.CLOSED)
        self._persist_state(conv)

    def resolve(self, conversation_id: str, outcome: str, resolved_by: str) -> None:
        conv = self._conversations[conversation_id]
        conv.resolution = ConversationResolution(outcome=outcome, resolved_by=resolved_by)
        self._db.execute(
            "INSERT OR REPLACE INTO resolutions (conversation_id, outcome, resolved_by, timestamp) VALUES (?, ?, ?, ?)",
            (conversation_id, outcome, resolved_by, datetime.now().isoformat())
        )
        self.close(conversation_id)

    def set_csat(self, conversation_id: str, score: int) -> None:
        conv = self._conversations.get(conversation_id)
        if conv and conv.resolution:
            conv.resolution.csat_score = score
            self._db.execute(
                "UPDATE resolutions SET csat_score = ? WHERE conversation_id = ?",
                (score, conversation_id)
            )
            self._db.commit()

    def add_participant(self, conversation_id: str, participant: Participant) -> None:
        conv = self._conversations[conversation_id]
        if participant.role == ParticipantRole.OPERATOR:
            current = sum(
                1 for c in self._conversations.values()
                if c.state in (ConversationState.ACTIVE, ConversationState.CREATED)
                and any(p.id == participant.id for p in c.participants)
            )
            if current >= self.max_operator_concurrent:
                raise ConcurrencyLimitExceeded(
                    f"Operator {participant.id} 已达并发上限 ({current}/{self.max_operator_concurrent})"
                )
        if not any(p.id == participant.id for p in conv.participants):
            conv.participants.append(participant)
            self._db.execute(
                "INSERT OR IGNORE INTO participants (conversation_id, participant_id, role, joined_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, participant.id, participant.role.value,
                 participant.joined_at.isoformat(), json.dumps(participant.metadata))
            )
            self._db.commit()

    def remove_participant(self, conversation_id: str, participant_id: str) -> None:
        conv = self._conversations[conversation_id]
        conv.participants = [p for p in conv.participants if p.id != participant_id]
        self._db.execute(
            "DELETE FROM participants WHERE conversation_id = ? AND participant_id = ?",
            (conversation_id, participant_id)
        )
        self._db.commit()

    def list_active(self) -> list[Conversation]:
        return [c for c in self._conversations.values()
                if c.state == ConversationState.ACTIVE]

    def _persist_state(self, conv: Conversation):
        self._db.execute(
            "UPDATE conversations SET state = ?, mode = ?, updated_at = ? WHERE id = ?",
            (conv.state.value, conv.mode, datetime.now().isoformat(), conv.id)
        )
        self._db.commit()
```

- [ ] **Step 4: 测试通过** → **Step 5: Commit**

```bash
git commit -m "feat(engine): ConversationManager with SQLite + concurrency limit"
```

### Task 2.3: engine/mode_manager.py + engine/timer_manager.py + 测试

**Files:**
- Create: `engine/mode_manager.py`
- Create: `engine/timer_manager.py`
- Test: `tests/unit/test_mode_manager.py`
- Test: `tests/unit/test_timer.py`

- [ ] **Step 1: 写 mode_manager 测试**

```python
# tests/unit/test_mode_manager.py
import pytest
from engine.mode_manager import ModeManager
from engine.event_bus import EventBus
from protocol.conversation import Conversation, ConversationState
from protocol.mode import ConversationMode
from protocol.event import EventType


@pytest.fixture
def mode_manager(tmp_path):
    bus = EventBus(str(tmp_path / "events.db"))
    return ModeManager(bus)


def test_transition_auto_to_copilot(mode_manager):
    conv = Conversation(id="c1", state=ConversationState.ACTIVE)
    mode_manager.transition(conv, ConversationMode.COPILOT,
                           trigger="operator_joined", triggered_by="xiaoli")
    assert conv.mode == ConversationMode.COPILOT.value


def test_transition_emits_event(mode_manager):
    conv = Conversation(id="c1", state=ConversationState.ACTIVE)
    received = []
    mode_manager.event_bus.subscribe(EventType.MODE_CHANGED, lambda e: received.append(e))
    
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        mode_manager.transition_async(conv, ConversationMode.COPILOT,
                                      trigger="/copilot", triggered_by="xiaoli")
    )
    assert len(received) == 1
    assert received[0].data["to"] == "copilot"


def test_invalid_transition_raises(mode_manager):
    conv = Conversation(id="c1", state=ConversationState.ACTIVE)
    # auto → auto 不合法
    with pytest.raises(ValueError):
        mode_manager.transition(conv, ConversationMode.AUTO,
                               trigger="test", triggered_by="test")
```

- [ ] **Step 2: 写 timer 测试**

```python
# tests/unit/test_timer.py
import asyncio
import pytest
from engine.timer_manager import TimerManager
from engine.event_bus import EventBus
from protocol.timer import TimerAction
from protocol.event import EventType
from datetime import timedelta


@pytest.fixture
def timer_setup(tmp_path):
    bus = EventBus(str(tmp_path / "events.db"))
    tm = TimerManager(bus)
    return tm, bus


@pytest.mark.asyncio
async def test_timer_fires(timer_setup):
    tm, bus = timer_setup
    fired = []
    bus.subscribe(EventType.TIMER_EXPIRED, lambda e: fired.append(e))
    
    tm.set_timer("conv_1", "test_timer", timedelta(seconds=0.1),
                 TimerAction(type="event", params={}))
    await asyncio.sleep(0.3)
    assert len(fired) == 1


@pytest.mark.asyncio
async def test_timer_cancel(timer_setup):
    tm, bus = timer_setup
    fired = []
    bus.subscribe(EventType.TIMER_EXPIRED, lambda e: fired.append(e))
    
    tm.set_timer("conv_1", "test_timer", timedelta(seconds=0.5),
                 TimerAction(type="event", params={}))
    tm.cancel_timer("conv_1", "test_timer")
    await asyncio.sleep(0.7)
    assert len(fired) == 0


@pytest.mark.asyncio
async def test_timer_reset(timer_setup):
    tm, bus = timer_setup
    fired = []
    bus.subscribe(EventType.TIMER_EXPIRED, lambda e: fired.append(e))
    
    tm.set_timer("conv_1", "t1", timedelta(seconds=0.3),
                 TimerAction(type="event", params={}))
    await asyncio.sleep(0.1)
    tm.set_timer("conv_1", "t1", timedelta(seconds=0.3),
                 TimerAction(type="event", params={}))  # reset
    await asyncio.sleep(0.25)
    assert len(fired) == 0  # 第一个被取消了
    await asyncio.sleep(0.2)
    assert len(fired) == 1  # 第二个到期
```

- [ ] **Step 3: 实现 mode_manager.py + timer_manager.py**

```python
# engine/mode_manager.py
from protocol.conversation import Conversation
from protocol.mode import ConversationMode, validate_transition
from protocol.event import Event, EventType
from engine.event_bus import EventBus


class ModeManager:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    def transition(self, conv: Conversation, new_mode: ConversationMode,
                   trigger: str, triggered_by: str):
        old_mode = ConversationMode(conv.mode)
        validate_transition(old_mode, new_mode, trigger, triggered_by)
        conv.mode = new_mode.value

    async def transition_async(self, conv: Conversation, new_mode: ConversationMode,
                               trigger: str, triggered_by: str):
        old_mode = ConversationMode(conv.mode)
        validate_transition(old_mode, new_mode, trigger, triggered_by)
        conv.mode = new_mode.value
        await self.event_bus.publish(Event(
            type=EventType.MODE_CHANGED,
            conversation_id=conv.id,
            data={"from": old_mode.value, "to": new_mode.value,
                  "trigger": trigger, "triggered_by": triggered_by}
        ))
```

```python
# engine/timer_manager.py
import asyncio
from datetime import timedelta
from protocol.timer import Timer, TimerAction
from protocol.event import Event, EventType
from engine.event_bus import EventBus


class TimerManager:
    def __init__(self, event_bus: EventBus):
        self._timers: dict[tuple[str, str], asyncio.Task] = {}
        self._event_bus = event_bus

    def set_timer(self, conv_id: str, name: str,
                  duration: timedelta, on_expire: TimerAction) -> Timer:
        key = (conv_id, name)
        if key in self._timers:
            self._timers[key].cancel()
        timer = Timer(conversation_id=conv_id, name=name,
                     duration=duration, on_expire=on_expire)
        task = asyncio.ensure_future(self._wait_and_fire(timer))
        self._timers[key] = task
        return timer

    def cancel_timer(self, conv_id: str, name: str) -> None:
        key = (conv_id, name)
        if key in self._timers:
            self._timers[key].cancel()
            del self._timers[key]

    async def _wait_and_fire(self, timer: Timer):
        try:
            await asyncio.sleep(timer.duration.total_seconds())
            await self._event_bus.publish(Event(
                type=EventType.TIMER_EXPIRED,
                conversation_id=timer.conversation_id,
                data={"timer_name": timer.name,
                      "action": timer.on_expire.type,
                      "params": timer.on_expire.params}
            ))
        except asyncio.CancelledError:
            pass
        finally:
            key = (timer.conversation_id, timer.name)
            self._timers.pop(key, None)
```

- [ ] **Step 4: 测试通过** → **Step 5: Commit**

```bash
git commit -m "feat(engine): ModeManager + TimerManager"
```

### Task 2.4: engine/message_store.py + engine/plugin_manager.py + engine/participant_registry.py + engine/squad_registry.py

**Files:** 4 个 engine 模块 + 测试

- [ ] **Step 1-5: 实现剩余 engine 模块**

每个模块遵循相同的 TDD 循环：写测试 → 失败 → 实现 → 通过 → commit。

关键测试点：
- `message_store`: save/get/edit/query_by_conversation
- `plugin_manager`: load hooks from directory, call on_message/on_mode_changed
- `participant_registry`: register agent/operator, identify by nick
- `squad_registry`: assign/reassign/get_squad/get_operator

- [ ] **Step 6: engine/ 全部测试通过**

```bash
cd zchat-channel-server && uv run pytest tests/unit/ -v
```

Expected: 全部 PASS (~50 个测试)

- [ ] **Step 7: Merge WT-2 到 main**

---

## Phase 3: Bridge API (WT-3, 依赖 Phase 1, 可与 Phase 2 并行)

**Worktree:** `zchat-channel-server-bridge`
**Branch:** `feat/bridge-api`

### Dev-loop closure 步骤

```bash
# 1. eval-doc
/dev-loop-skills:skill-5-feature-eval simulate
# 主题: "Bridge WebSocket API — 多角色接入（customer/operator/admin）"

# 2. test-plan
/dev-loop-skills:skill-2-test-plan-generator
# 输入: eval-doc + 02-channel-server.md §5 Bridge API

# 3. test-code
/dev-loop-skills:skill-3-test-code-writer
# 输出: tests/unit/test_bridge_api.py

# 4. 实现 (TDD)
# 5. test-run
/dev-loop-skills:skill-4-test-runner

# 6. artifact 注册
/dev-loop-skills:skill-6-artifact-registry
```

### Task 3.1: bridge_api/ws_server.py + 测试

**Files:**
- Create: `bridge_api/__init__.py`
- Create: `bridge_api/ws_server.py`
- Test: `tests/unit/test_bridge_api.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_bridge_api.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from bridge_api.ws_server import BridgeAPIServer, BridgeConnection


@pytest.fixture
def mock_conversation_manager():
    cm = MagicMock()
    cm.create.return_value = MagicMock(id="test_conv", state="active", mode="auto")
    cm.get.return_value = MagicMock(id="test_conv", state="active", mode="auto")
    return cm


@pytest.fixture
def bridge_server(mock_conversation_manager):
    return BridgeAPIServer(
        conversation_manager=mock_conversation_manager,
        port=0,  # 不实际监听
    )


def test_register_message_parsed(bridge_server):
    msg = {"type": "register", "bridge_type": "feishu",
           "instance_id": "fb-1", "capabilities": ["customer", "operator"]}
    conn = bridge_server._parse_register(msg)
    assert conn.bridge_type == "feishu"
    assert "customer" in conn.capabilities
    assert "operator" in conn.capabilities


def test_customer_connect_creates_conversation(bridge_server, mock_conversation_manager):
    msg = {"type": "customer_connect", "conversation_id": "feishu_oc_abc",
           "customer": {"id": "david", "name": "David"}}
    bridge_server._handle_customer_connect(msg)
    mock_conversation_manager.create.assert_called_once_with(
        "feishu_oc_abc", metadata={"customer_id": "david", "customer_name": "David"}
    )


def test_operator_command_hijack(bridge_server):
    msg = {"type": "operator_command", "conversation_id": "feishu_oc_abc",
           "operator_id": "xiaoli", "command": "/hijack"}
    cmd = bridge_server._parse_operator_command(msg)
    assert cmd.name == "hijack"


def test_visibility_routing_public():
    """public 消息: customer + operator + admin 都收到"""
    routing = BridgeAPIServer.compute_visibility_targets("public")
    assert routing == {"customer", "operator", "admin"}


def test_visibility_routing_side():
    """side 消息: 只有 operator + admin 收到"""
    routing = BridgeAPIServer.compute_visibility_targets("side")
    assert routing == {"operator", "admin"}


def test_visibility_routing_system():
    """system 消息: 只有 operator + admin 收到"""
    routing = BridgeAPIServer.compute_visibility_targets("system")
    assert routing == {"operator", "admin"}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd zchat-channel-server && uv run pytest tests/unit/test_bridge_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'bridge_api'`

- [ ] **Step 3: 实现 bridge_api/ws_server.py**

```python
# bridge_api/__init__.py
"""Bridge WebSocket API — 多角色接入"""

# bridge_api/ws_server.py
"""WebSocket server for Bridge connections (Feishu/Web/etc)."""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional
import websockets
from websockets.asyncio.server import ServerConnection
from protocol.commands import parse_command, Command


@dataclass
class BridgeConnection:
    ws: Optional[ServerConnection]
    bridge_type: str
    instance_id: str
    capabilities: list[str] = field(default_factory=list)
    conversation_subscriptions: set[str] = field(default_factory=set)


class BridgeAPIServer:
    def __init__(self, conversation_manager=None, mode_manager=None,
                 event_bus=None, port: int = 9999):
        self._connections: list[BridgeConnection] = []
        self._conversation_manager = conversation_manager
        self._mode_manager = mode_manager
        self._event_bus = event_bus
        self.port = port

    def _parse_register(self, msg: dict) -> BridgeConnection:
        return BridgeConnection(
            ws=None,
            bridge_type=msg.get("bridge_type", "unknown"),
            instance_id=msg.get("instance_id", ""),
            capabilities=msg.get("capabilities", []),
        )

    def _handle_customer_connect(self, msg: dict):
        conv_id = msg["conversation_id"]
        customer = msg.get("customer", {})
        self._conversation_manager.create(
            conv_id,
            metadata={"customer_id": customer.get("id", ""),
                      "customer_name": customer.get("name", "")}
        )

    def _parse_operator_command(self, msg: dict) -> Command:
        return parse_command(msg["command"])

    @staticmethod
    def compute_visibility_targets(visibility: str) -> set[str]:
        if visibility == "public":
            return {"customer", "operator", "admin"}
        elif visibility in ("side", "system"):
            return {"operator", "admin"}
        return set()

    async def send_to_bridges(self, conversation_id: str, message: dict,
                              visibility: str = "public"):
        targets = self.compute_visibility_targets(visibility)
        message["visibility"] = visibility
        raw = json.dumps(message, ensure_ascii=False)
        for conn in self._connections:
            if conversation_id in conn.conversation_subscriptions:
                matching_caps = set(conn.capabilities) & targets
                if matching_caps:
                    try:
                        await conn.ws.send(raw)
                    except Exception:
                        pass

    async def run(self):
        async with websockets.serve(self._handle_client, "localhost", self.port):
            await asyncio.Future()  # run forever

    async def _handle_client(self, ws: ServerConnection):
        conn: Optional[BridgeConnection] = None
        try:
            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                if msg_type == "register":
                    conn = self._parse_register(msg)
                    conn.ws = ws
                    self._connections.append(conn)
                    await ws.send(json.dumps({"type": "registered",
                                              "instance_id": conn.instance_id}))
                elif msg_type == "customer_connect":
                    self._handle_customer_connect(msg)
                    if conn:
                        conn.conversation_subscriptions.add(msg["conversation_id"])
                elif msg_type == "customer_message":
                    pass  # 路由到 engine
                elif msg_type == "operator_command":
                    cmd = self._parse_operator_command(msg)
                    # 路由到 CommandParser
                elif msg_type == "admin_command":
                    cmd = parse_command(msg.get("command", ""))
                    # 路由到 CommandParser
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if conn and conn in self._connections:
                self._connections.remove(conn)
```

- [ ] **Step 4: 运行测试通过**

```bash
cd zchat-channel-server && uv run pytest tests/unit/test_bridge_api.py -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(bridge_api): WebSocket server with multi-role support"
```

- [ ] **Step 6: Merge WT-3 到 main**

---

## Phase 4: Transport + Server Refactor (WT-4, 依赖 Phase 2 + 3)

**Worktree:** `zchat-channel-server-integration`
**Branch:** `feat/server-v1`

### Dev-loop closure 步骤

```bash
# 1. eval-doc
/dev-loop-skills:skill-5-feature-eval simulate
# 主题: "IRC Transport 提取 + server.py v1.0 集成重构"

# 2. test-plan
/dev-loop-skills:skill-2-test-plan-generator
# 输入: eval-doc + 现有 server.py 代码 + 02-channel-server.md §6-§7

# 3. test-code (unit + E2E)
/dev-loop-skills:skill-3-test-code-writer
# 输出: tests/unit/test_irc_transport.py + tests/e2e/*.py

# 4. 实现 (TDD)
# 5. test-run (unit + E2E 两层)
/dev-loop-skills:skill-4-test-runner

# 6. artifact 注册
/dev-loop-skills:skill-6-artifact-registry
```

### Task 4.1: transport/irc_transport.py

从现有 `server.py` L76-180 的 `setup_irc()` 提取到独立模块。

**Files:**
- Create: `transport/__init__.py`
- Create: `transport/irc_transport.py`
- Modify: `server.py` — 删除 setup_irc()，改为调用 IRCTransport
- Test: `tests/unit/test_irc_transport.py`

- [ ] **Step 1: 写 IRCTransport 单元测试（mock IRC 连接）**
- [ ] **Step 2: 实现 transport/irc_transport.py**
- [ ] **Step 3: 通过** → **Commit**

### Task 4.2: server.py 重构

**Modify:** `server.py`

- [ ] **Step 1: 保留** inject_message + poll_irc_queue + create_server（不改）
- [ ] **Step 2: 新增** engine 组件初始化（ConversationManager + ModeManager + EventBus + TimerManager + PluginManager）
- [ ] **Step 3: 新增** Bridge API server 启动
- [ ] **Step 4: 改造** on_pubmsg:
  ```python
  participant = registry.identify(nick)
  if body.startswith("/"):
      command_parser.handle(body, participant, channel)
      return
  message = Message(...)
  message = gate.process(conversation, participant, message)
  # visibility 路由: public/side/system → Bridge + Agent MCP
  ```
- [ ] **Step 5: 新增** on_join handler（operator → copilot 自动切换）
- [ ] **Step 6: 新增** App tools 注册（从 config 加载 plugin_loader）
- [ ] **Step 7: 改造** register_tools — 新增 edit_message / join_conversation / send_side_message 等 tools
- [ ] **Step 8: 运行现有 12 个 unit 测试确认无回归**

```bash
uv run pytest tests/unit/test_message.py tests/unit/test_legacy.py -v
```

- [ ] **Step 9: Commit**

### Task 4.3: E2E 测试

**Files:**
- Create: `tests/e2e/conftest.py` — ergo fixture + channel-server 启动
- Create: `tests/e2e/test_conversation_lifecycle.py`
- Create: `tests/e2e/test_mode_switching.py`
- Create: `tests/e2e/test_bridge_api.py`
- Create: `tests/e2e/test_gate_enforcement.py`

E2E 测试架构：
```python
# tests/e2e/conftest.py

@pytest.fixture(scope="session")
def e2e_port():
    return 16667 + (os.getpid() % 1000)

@pytest.fixture(scope="session")
def bridge_port():
    return 19999 + (os.getpid() % 1000)

@pytest.fixture(scope="session")
def ergo_server(e2e_port, tmp_path_factory):
    """启动 ergo IRC server"""
    ...

@pytest.fixture(scope="session")
def channel_server(ergo_server, e2e_port, bridge_port, tmp_path_factory):
    """启动 channel-server（连接 ergo + 开 Bridge API）"""
    ...

@pytest.fixture
def bridge_client(bridge_port):
    """WebSocket client 模拟 Bridge"""
    async def connect():
        ws = await websockets.connect(f"ws://localhost:{bridge_port}")
        await ws.send(json.dumps({
            "type": "register",
            "bridge_type": "test",
            "instance_id": "test-bridge",
            "capabilities": ["customer", "operator", "admin"]
        }))
        return ws
    return connect
```

关键 E2E 测试场景：
1. **test_conversation_lifecycle**: customer_connect → 消息交换 → idle → reactivate → /resolve → closed
2. **test_mode_switching**: customer 消息 → operator_join → copilot → /hijack → takeover → /release → auto
3. **test_gate_enforcement**: copilot 下 operator 消息不到 customer；takeover 下 agent 消息不到 customer
4. **test_bridge_api**: register → customer_connect → customer_message → reply → edit

- [ ] **Merge WT-4 到 main**

---

## Phase 5: zchat CLI (WT-5, 独立，可与 Phase 1 并行)

**Worktree:** `zchat-cli-channel-config`
**Branch:** `feat/channel-server-config`
**仓库:** zchat (主仓库)

### Dev-loop closure 步骤

```bash
# 1. eval-doc
/dev-loop-skills:skill-5-feature-eval simulate
# 主题: "zchat CLI 扩展 — channel-server v1.0 配置支持"

# 2. test-plan
/dev-loop-skills:skill-2-test-plan-generator
# 输入: eval-doc + zchat CLAUDE.md + project.py 现有配置结构

# 3. test-code
/dev-loop-skills:skill-3-test-code-writer
# 输出: tests/unit/test_config_channel_server.py

# 4. 实现 (TDD)
# 5. test-run
/dev-loop-skills:skill-4-test-runner
```

### Task 5.1: config.toml 新增 [channel_server] 段

**Files:**
- Modify: `zchat/cli/project.py`
- Test: `tests/unit/test_config_channel_server.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_config_channel_server.py
import tomllib
from pathlib import Path

def test_default_config_has_channel_server_section(tmp_path):
    """project create 生成的 config.toml 应包含 [channel_server] 段。"""
    from zchat.cli.project import generate_default_config
    config_text = generate_default_config("test-project", server="127.0.0.1", port=6667)
    config = tomllib.loads(config_text)
    assert "channel_server" in config
    assert config["channel_server"]["bridge_port"] == 9999

def test_channel_server_timer_defaults(tmp_path):
    from zchat.cli.project import generate_default_config
    config = tomllib.loads(generate_default_config("test", server="127.0.0.1", port=6667))
    timers = config["channel_server"]["timers"]
    assert timers["takeover_wait"] == 180
    assert timers["idle_timeout"] == 300

def test_channel_server_participant_defaults(tmp_path):
    from zchat.cli.project import generate_default_config
    config = tomllib.loads(generate_default_config("test", server="127.0.0.1", port=6667))
    participants = config["channel_server"]["participants"]
    assert participants["max_operator_concurrent"] == 5
```

- [ ] **Step 2: 运行失败** → **Step 3: 修改 project.py 添加默认配置** → **Step 4: 通过** → **Step 5: Commit**

### Task 5.2: Agent 模板

**Files:**
- Create: `zchat/cli/templates/autoservice-fast/template.toml`
- Create: `zchat/cli/templates/autoservice-fast/soul.md`
- Create: `zchat/cli/templates/autoservice-deep/template.toml`
- Create: `zchat/cli/templates/autoservice-deep/soul.md`

- [ ] **Step 1: 创建模板文件**（内容参考 07-migration-plan.md 的 soul.md 模板）
- [ ] **Step 2: 测试 template_loader 能发现新模板**

```bash
uv run pytest tests/unit/test_template_loader.py -v
```

- [ ] **Step 3: Commit**

### Task 5.3: channel-server submodule 更新

```bash
cd zchat
git submodule update --remote zchat-channel-server
git add zchat-channel-server
git commit -m "chore: update channel-server to v1.0"
```

- [ ] **Merge WT-5 到 yao-dev**

---

## Phase Final: Pre-release Testing (main branch)

### Dev-loop closure 步骤

```bash
# 1. eval-doc (verify mode)
/dev-loop-skills:skill-5-feature-eval verify
# 主题: "channel-server v1.0 端到端验收"

# 2. test-plan (从 eval-doc 生成验收 checklist)
/dev-loop-skills:skill-2-test-plan-generator

# 3. test-code (walkthrough + Playwright)
/dev-loop-skills:skill-3-test-code-writer

# 4. 执行验收
# 5. test-run 生成报告
/dev-loop-skills:skill-4-test-runner
```

### Task F.1: Pre-release walkthrough (asciinema 录制)

**Files:**
- Create: `tests/pre_release/channel_server_walkthrough.sh`

```bash
#!/bin/bash
# Pre-release walkthrough for channel-server v1.0
# 录制为 asciinema，人工 review

set -e

echo "=== Channel-Server v1.0 Pre-release Walkthrough ==="

# 1. 启动基础设施
echo ">>> Starting ergo..."
zchat irc daemon start

echo ">>> Starting channel-server..."
zchat-channel --bridge-port 9999 &
CS_PID=$!
sleep 3

# 2. 测试 Bridge API 连接
echo ">>> Testing Bridge API..."
python3 -c "
import asyncio, websockets, json
async def test():
    ws = await websockets.connect('ws://localhost:9999')
    await ws.send(json.dumps({'type': 'register', 'bridge_type': 'test', 'instance_id': 'walkthrough', 'capabilities': ['customer']}))
    resp = json.loads(await ws.recv())
    assert resp['type'] == 'registered', f'Expected registered, got {resp}'
    print('Bridge API: OK')
    await ws.close()
asyncio.run(test())
"

# 3. 测试对话创建
echo ">>> Testing conversation creation..."
# ... (通过 Bridge API 创建对话，发送消息，验证回复)

# 4. 测试 mode 切换
echo ">>> Testing mode switching..."
# ... (operator_join → copilot → /hijack → takeover → /release)

# 5. 测试 Gate 拦截
echo ">>> Testing Gate enforcement..."
# ... (takeover 下验证 agent 消息被降级为 side)

echo ">>> All checks passed!"
kill $CS_PID
```

### Task F.2: Bridge API 验收 (Playwright WebSocket 测试)

**Files:**
- Create: `tests/pre_release/test_bridge_acceptance.py`
- Create: `tests/pre_release/conftest.py`

使用 Playwright 验证 Web Bridge 端到端流程（不依赖飞书，纯 WebSocket）：

```python
# tests/pre_release/conftest.py
"""Pre-release 测试 fixtures — 启动完整 channel-server + ergo + Bridge"""
import asyncio
import subprocess
import time
import pytest

@pytest.fixture(scope="session")
def full_stack(tmp_path_factory):
    """启动完整的 ergo + channel-server + web bridge 栈"""
    work_dir = tmp_path_factory.mktemp("prerelease")
    
    # 1. 启动 ergo
    ergo_port = 16667 + (os.getpid() % 1000)
    ergo_proc = subprocess.Popen(
        ["ergo", "run", "--conf", str(work_dir / "ergo.yaml")],
        cwd=str(work_dir)
    )
    time.sleep(2)
    
    # 2. 启动 channel-server
    bridge_port = 19999 + (os.getpid() % 1000)
    cs_proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "server"],
        env={**os.environ,
             "IRC_SERVER": "127.0.0.1", "IRC_PORT": str(ergo_port),
             "BRIDGE_PORT": str(bridge_port),
             "AGENT_NAME": "test-agent"},
    )
    time.sleep(3)
    
    yield {"ergo_port": ergo_port, "bridge_port": bridge_port,
           "ergo_proc": ergo_proc, "cs_proc": cs_proc}
    
    cs_proc.terminate()
    ergo_proc.terminate()
```

```python
# tests/pre_release/test_bridge_acceptance.py
"""Pre-release 验收测试 — 通过 WebSocket 模拟完整用户旅程"""
import asyncio
import json
import pytest
import websockets


@pytest.mark.prerelease
@pytest.mark.asyncio
async def test_full_conversation_lifecycle(full_stack):
    """验收旅程 1+4: 客户接入 → Agent 回复 → operator 接管 → /resolve"""
    bridge_port = full_stack["bridge_port"]
    
    # 1. 连接 Bridge API (模拟飞书 Bridge)
    ws = await websockets.connect(f"ws://localhost:{bridge_port}")
    await ws.send(json.dumps({
        "type": "register", "bridge_type": "test",
        "instance_id": "acceptance-test",
        "capabilities": ["customer", "operator", "admin"]
    }))
    resp = json.loads(await ws.recv())
    assert resp["type"] == "registered"
    
    # 2. 客户接入
    await ws.send(json.dumps({
        "type": "customer_connect",
        "conversation_id": "test_acceptance_001",
        "customer": {"id": "david", "name": "David"}
    }))
    
    # 3. 客户发送消息
    await ws.send(json.dumps({
        "type": "customer_message",
        "conversation_id": "test_acceptance_001",
        "text": "B套餐多少钱",
        "message_id": "msg_001"
    }))
    
    # 4. 等待 agent 回复（或超时）
    reply = await asyncio.wait_for(ws.recv(), timeout=30)
    reply_data = json.loads(reply)
    assert reply_data["type"] == "reply"
    assert reply_data["visibility"] == "public"
    
    # 5. Operator 加入 (copilot)
    await ws.send(json.dumps({
        "type": "operator_join",
        "conversation_id": "test_acceptance_001",
        "operator": {"id": "xiaoli", "name": "小李"}
    }))
    
    # 6. 验证 mode 切换事件
    event = await asyncio.wait_for(ws.recv(), timeout=5)
    event_data = json.loads(event)
    assert event_data.get("event_type") == "mode.changed"
    assert event_data["data"]["to"] == "copilot"
    
    # 7. Operator /hijack
    await ws.send(json.dumps({
        "type": "operator_command",
        "conversation_id": "test_acceptance_001",
        "operator_id": "xiaoli",
        "command": "/hijack"
    }))
    
    event = await asyncio.wait_for(ws.recv(), timeout=5)
    event_data = json.loads(event)
    assert event_data["data"]["to"] == "takeover"
    
    # 8. /resolve
    await ws.send(json.dumps({
        "type": "operator_command",
        "conversation_id": "test_acceptance_001",
        "operator_id": "xiaoli",
        "command": "/resolve"
    }))
    
    # 9. 验证 CSAT 请求
    csat_req = await asyncio.wait_for(ws.recv(), timeout=5)
    csat_data = json.loads(csat_req)
    assert csat_data["type"] == "csat_request"
    
    await ws.close()


@pytest.mark.prerelease
@pytest.mark.asyncio
async def test_gate_enforcement_via_bridge(full_stack):
    """验收 Gate: takeover 模式下 agent 消息对 customer 不可见"""
    bridge_port = full_stack["bridge_port"]
    
    # 建立两个连接: 一个模拟 customer 端，一个模拟 operator 端
    customer_ws = await websockets.connect(f"ws://localhost:{bridge_port}")
    await customer_ws.send(json.dumps({
        "type": "register", "bridge_type": "test-customer",
        "instance_id": "customer-view",
        "capabilities": ["customer"]
    }))
    
    operator_ws = await websockets.connect(f"ws://localhost:{bridge_port}")
    await operator_ws.send(json.dumps({
        "type": "register", "bridge_type": "test-operator",
        "instance_id": "operator-view",
        "capabilities": ["operator"]
    }))
    
    # ... 建立对话，切到 takeover ...
    # 验证: agent 的 side 消息到 operator_ws 但不到 customer_ws
    
    await customer_ws.close()
    await operator_ws.close()
```

运行命令：
```bash
cd zchat-channel-server && uv run pytest tests/pre_release/ -v -m prerelease --timeout=60
```

### Task F.3: 飞书真实环境验证（可选，需要凭证）

如果有飞书 app 凭证可用，使用 `agent-browser` skill 进行真实飞书验证：

```bash
# 使用 agent-browser skill 自动化飞书 Web 客户端
/agent-browser:agent-browser
# 步骤:
# 1. 打开飞书 Web (https://www.feishu.cn/messenger/)
# 2. 登录到测试账号
# 3. 找到测试客户群
# 4. 发送消息 "B套餐多少钱"
# 5. 截图验证 agent 回复出现
# 6. 在管理群发送 /status
# 7. 截图验证状态返回
```

或者使用飞书 CLI（lark-cli）发送和接收消息：
```bash
# 通过飞书 API 直接发消息到测试群
python3 -c "
import lark_oapi as lark
client = lark.Client.builder().app_id('$APP_ID').app_secret('$APP_SECRET').build()
# 发送测试消息到群
# 轮询检查 agent 回复
# 断言回复内容
"
```

**证据保存**：所有 pre-release 测试的截图、录屏、日志保存到 `tests/pre_release/evidence/` 目录。

---

## Dev-loop Skill 闭环对照

| Phase | Worktree | eval-doc 主题 | test-plan 范围 | 测试层 | merge 目标 |
|-------|----------|-------------|---------------|--------|-----------|
| 0 | main | 基础设施搭建 | — | — | — |
| 1 | WT-1 | 通用对话协议原语 | 8 个 protocol 测试文件 | Unit | main |
| 2 | WT-2 | 对话引擎运行时 | 8 个 engine 测试文件 | Unit | main |
| 3 | WT-3 | Bridge WebSocket API | 1 个 bridge_api 测试文件 | Unit | main |
| 4 | WT-4 | 集成 + server 重构 | 4 个 E2E 测试文件 | Unit + E2E | main |
| 5 | WT-5 | zchat CLI 配置扩展 | 2 个 zchat 测试文件 | Unit | yao-dev |
| Final | main | 端到端验收 | walkthrough + 飞书 E2E | Pre-release | — |

每个 Phase 的 dev-loop 执行命令：
```
1. /dev-loop-skills:skill-5-feature-eval simulate  → 生成 eval-doc
2. /dev-loop-skills:skill-2-test-plan-generator     → 生成 test-plan
3. /dev-loop-skills:skill-3-test-code-writer        → 生成 test code
4. 实现代码 (TDD)
5. /dev-loop-skills:skill-4-test-runner             → 运行测试 + 报告
6. /dev-loop-skills:skill-6-artifact-registry       → 注册 artifact
```

---

## 估算

| Phase | 新增代码 | 测试代码 | 耗时（Claude Code 执行） |
|-------|---------|---------|------------------------|
| Phase 0 | ~50 行 | — | 0.5h |
| Phase 1 (protocol/) | ~350 行 | ~200 行 | 2-3h |
| Phase 2 (engine/) | ~640 行 | ~300 行 | 3-4h |
| Phase 3 (bridge_api/) | ~150 行 | ~100 行 | 1-2h |
| Phase 4 (integration) | ~200 行 | ~300 行 | 3-4h |
| Phase 5 (zchat CLI) | ~100 行 | ~50 行 | 1h |
| Phase Final | — | ~200 行 | 2-3h |
| **合计** | **~1490 行** | **~1150 行** | **~13-17h** |

---

*Plan created: 2026-04-14 · Based on spec docs 00-07 in docs/discuss/spec/channel-server/*
