---
type: eval-doc
id: eval-doc-014
status: confirmed
producer: skill-5
created_at: "2026-04-22T07:45:00Z"
confirmed_at: "2026-04-22T08:00:00Z"
mode: simulate
feature: cs-plugin-config-autonomy
submitter: yaosh
related: []
spec: docs/guide/007-plugin-guide.md
plan: inline §"确认决策" (2026-04-22)
target_repo: zchat-channel-server
branch: refactor/plugin (cut from dev)
---

# Eval: CS Plugin 架构 — config 自治 + 目录即模块

## 基本信息

- **模式**：模拟（pre-impl evaluation）
- **提交人**：yaosh
- **日期**：2026-04-22
- **状态**：draft（等用户 confirm）
- **基线**：dev 分支 (CS repo refactor/v4 = 726540d)
- **工作量预估**：~1-1.5 人日（plugin 改签名机械 + __main__ loader 新建 + 测试修）

## 背景与核心论点

### 当前痛点（源码事实）

1. **`channel_server/__main__.py:81-93`** 硬编码 6 个 plugin 的 register + 手工 DI：
   ```python
   registry.register(ModePlugin(emit_event=emit_event))
   registry.register(SlaPlugin(emit_event=emit_event, emit_command=emit_command, timeout_seconds=180))
   registry.register(ResolvePlugin(emit_event=emit_event))
   audit_plugin = AuditPlugin(persist_path=data_dir / "audit.json")   # ← path 由 main 决定
   registry.register(audit_plugin)
   registry.register(ActivationPlugin(state_file=data_dir / "activation-state.json",
                                       emit_event=emit_event))          # ← 同上
   registry.register(CsatPlugin(emit_event=emit_event, audit_plugin=audit_plugin))
   ```

2. **6 个 plugin 的 `__init__` 签名各不相同**（plugins/*/plugin.py:22-72）：
   - `ModePlugin(emit_event)`
   - `SlaPlugin(emit_event, emit_command, timeout_seconds, help_timeout_seconds)`
   - `ResolvePlugin(emit_event)`
   - `AuditPlugin(persist_path)` ← 只吃 path，无 emit_event
   - `ActivationPlugin(state_file, emit_event)`
   - `CsatPlugin(emit_event, audit_plugin)` ← 注入兄弟 plugin

3. **新加 plugin 必须改 `__main__.py`**（注册点 + DI 接线），违反"目录即模块"直觉。

4. **两类 plugin 看起来不同但本质同构**（详见主库 `docs/guide/007-plugin-guide.md` §7）：
   - Forwarder（如 Shopify exporter）：订阅 event → 外部 API 调用 → 可选 dedup 落盘
   - Internal collector（如 audit）：订阅 event → 内部账本 → 落盘
   - 区别只是 config schema 的饱满度（前者有 endpoint/token，后者只有 data_dir）

5. **plugin 无法作为独立后台服务拆出** — 因为 config 耦合在 CS main；路径是 main 决定的，plugin 不知道自己数据放哪。

### 核心论点（要验证的设计决策）

**两类 plugin 是同一抽象**，区别只是 config schema 饱满度。统一契约 = `(config_dict, emit_event, **injections)`，内部 collector 只是"没填 runtime 参数的 forwarder"。

## Testcase 表格

| # | 场景 | 前置条件 | 操作步骤 | 预期效果 | 模拟效果 | 差异描述 | 优先级 |
|---|------|---------|---------|---------|---------|---------|--------|
| 1 | audit plugin config 自治 | plugins.toml 存在 `[plugins.audit] data_dir="./audit"` | CS 启动 | AuditPlugin 读 config["data_dir"] 组装 `./audit/state.json` 路径 | 可行。AuditPlugin.__init__ 改为 `(config, emit_event)`，内部 `self._path = Path(config.get("data_dir", default_for("audit"))) / "state.json"`。config 为空时用默认 `<project>/plugins/audit/`。现有 `_load/_save` 逻辑完全不变 | 无 — 纯签名改动 | P0 |
| 2 | activation plugin config 自治 + 业务参数 | plugins.toml `[plugins.activation] data_dir="./activation" dormant_threshold_hours=72` | CS 启动 | ActivationPlugin 读 data_dir + 业务参数 | 可行。同 audit pattern；`self._dormant_threshold = config.get("dormant_threshold_hours", 72)`。若未来业务参数丰富，hold in config 比加 __init__ 参数干净 | 现在 dormant 判定硬编码，改 config 后可调 | P0 |
| 3 | mode/resolve 无 config plugin 仍可运行 | plugins.toml 无对应 section | CS 启动 | 传入空 dict，plugin 正常 register | 可行。`config=plugins_cfg.get("mode", {})`；BasePlugin default `config.get(key, fallback)` 全部走 fallback 分支 | 无 | P0 |
| 4 | sla timer 参数移到 config | plugins.toml `[plugins.sla] takeover_timeout=180 help_timeout=180` | CS 启动 | SlaPlugin 从 config 读两个 timeout | 可行。当前 `__main__.py:82` 硬编码 `timeout_seconds=180` + `help_timeout_seconds` 用 fallback。改后 `self._timeout = config.get("takeover_timeout", 180)`。**破坏点**：e2e 测试 `test_help_request_lifecycle.py` 直接实例化 SlaPlugin 传 kwargs，要改为传 config dict | 现在是 main.py 写死，改后运营方可调 | P1 |
| 5 | csat 的 DI 保留（依赖注入 audit 引用） | plugins.toml 两个 plugin 都存在 | CS 启动 | CsatPlugin 仍能拿到 AuditPlugin 引用 | 可行但需新机制。方案：loader 在实例化 csat 时通过 `registry.get_plugin("audit")` 补齐 **injections** 参数。CsatPlugin.__init__ 签名 `(config, emit_event, *, audit=None)`，loader 探测 kw-only 需求后注入。**替代方案**：所有 plugin 拿 registry 引用（更彻底但散漫），用户决策点 | csat 的耦合从 __main__ 硬编码挪到 loader 的自动注入；语义等价 | P0 |
| 6 | 扫目录自动 register | `src/plugins/shopify_exporter/plugin.py` + plugins.toml `[plugins.shopify_exporter]` | CS 启动 | 自动发现 + 加载 + register，无需改 __main__ | 可行。loader 逻辑：① `pkgutil.iter_modules(plugins.__path__)` → ② 每个 name 动态 `importlib.import_module(f"plugins.{name}.plugin")` → ③ 找 `*Plugin` 类 → ④ 读 plugins.toml `[plugins.<name>]` → ⑤ 实例化 register。约束：每个 plugin 目录必须有一个 `<Name>Plugin` 类，且 `name` 字段与目录名一致（冲突检测在 PluginRegistry 已有） | __main__.py register 段删掉，变成 10 行 loader 调用 | P0 |
| 7 | 删 plugin 目录 = 禁用 | 删除 `src/plugins/csat/` 整目录 | CS 启动 | CS 启动不报错，csat 功能缺失 | 可行。discovery 基于目录存在性，删了就发现不到。**风险**：如果其它 plugin 通过 injections 依赖 csat（当前无此依赖），loader 要降级处理或报错。实证：csat 依赖 audit 单向，audit 不依赖 csat，删 csat 无影响 | 当前 __main__.py 硬编码 register，删 plugin 文件会 ImportError 启动失败 | P1 |
| 8 | plugins.toml 标 `enabled=false` 禁用 | plugin 目录存在但 config 标禁用 | CS 启动 | loader 跳过该 plugin | 可行。loader 早读 config；`if config.get("enabled", True) is False: skip`。对运营环境"临时禁用某 plugin 做故障排查"场景有用 | 无（当前无此能力） | P1 |
| 9 | 全新 shopify_exporter plugin 0 改动 main | 新建 `plugins/shopify_exporter/plugin.py` + plugins.toml 加 section | CS 启动 | 自动生效，无需改 __main__ | 可行。走 #6 的 discovery 路径。Shopify plugin 自己 __init__ 从 config 拿 endpoint/token_env/min_csat/data_dir，订阅 csat_recorded + channel_resolved。外部 API 调用 via `aiohttp` 放在 `on_ws_event` 内。幂等性自己管（见 007-guide §7.3 exporter 例子） | 新加 plugin 体验从"改 __main__ + 添依赖注入" → "加一个目录 + TOML 一段"；收益显著 | P0 |
| 10 | CS_DATA_DIR env 兜底仍有效 | plugins.toml 无 data_dir；CS_DATA_DIR=/tmp/test | CS 启动 | plugin 路径解析为 /tmp/test/plugins/audit/state.json | 可行。优先级链：config.data_dir → PLUGIN_NAME_DATA_DIR env → CS_DATA_DIR → routing.toml 同目录。在 `paths.default_plugin_data_dir(name)` 里一次性实现，每个 plugin 调它 | E2E 测试 `CS_DATA_DIR=tmpdir` 的 fixture 仍工作 | P0 |
| 11 | PluginRegistry 的冲突检测不变 | 同目录两个 class 都声明 name="audit" | CS 启动 | 启动抛 ValueError | 不变。register 路径不变，只是调用方从 __main__ 硬编码变成 loader 循环。`PluginRegistry.register` (plugin.py:67-79) 冲突检测逻辑保留 | 无 | P0 |
| 12 | Forwarder 和 Collector 代码完全对称 | 两个类都继承 BasePlugin | 读 audit.py 和 shopify_exporter.py | 结构对称：`__init__(config, emit_event)` / `on_ws_event` / 可选 `_save/_load` | 可行。BasePlugin 已 5 方法全默认实现。Forwarder 实际和 Collector 没有任何代码路径差异，都是"读 config → 订阅 → 处理"。文档 007-guide §7 的"分两类"那段可以删（误导） | 核心论点验证通过 — 本来就是一个抽象 | P1 |

## 6 个官方 plugin 的迁移示意

### AuditPlugin（改动最机械）

**前**（`plugins/audit/plugin.py:41`）：
```python
def __init__(self, persist_path: str | Path) -> None:
    self._path = Path(persist_path)
    self._state = self._load()
```

**后**：
```python
def __init__(self, config: dict, emit_event: Callable = None) -> None:
    data_dir = Path(config.get("data_dir") or default_plugin_data_dir("audit"))
    self._path = data_dir / "state.json"
    self._state = self._load()
    # emit_event 接收但不用（audit 不 emit），保留是为了契约统一
```

_load/_save/record_csat/query 全部不改。

### ActivationPlugin（直接迁移）

**前**：`__init__(state_file, emit_event)`
**后**：`__init__(config, emit_event)` — 同样从 `config["data_dir"]` 组装 state_file 路径。`config.get("dormant_threshold_hours", 72)` 替代当前硬编码。

### CsatPlugin（DI 问题的核心）

**前**（`plugins/csat/plugin.py:25-31`）：
```python
def __init__(self, emit_event, audit_plugin=None):
    self._emit_event = emit_event
    self._audit = audit_plugin
```

**后方案 A — loader 做 DI**（推荐）：
```python
def __init__(self, config: dict, emit_event, *, audit=None):
    self._emit_event = emit_event
    self._audit = audit

# loader 检测到 csat 的 __init__ 有 `audit` kw 参数：
#   → `registry.get_plugin("audit")` 取引用
#   → 在 `audit=...` kwarg 注入
#   → 若 audit plugin 未启用，audit=None（csat 的 `if self._audit:` 分支已处理）
```

**后方案 B — plugin 主动 lookup**：
```python
def __init__(self, config: dict, emit_event, registry=None):
    self._audit = registry.get_plugin("audit") if registry else None
```

方案 A 更明确（signature-driven DI），方案 B 更灵活（运行时查询）。**决策点**：见下方用户决策 §2。

### ModePlugin / ResolvePlugin（最简）

只改 `__init__(config, emit_event)`。body 0 改动。

### SlaPlugin

**前**：`__init__(emit_event, emit_command, timeout_seconds=180, help_timeout_seconds=None)`
**后**：`__init__(config, emit_event, emit_command)` — 两个 timeout 从 `config.get("takeover_timeout", 180)` / `config.get("help_timeout", takeover_timeout)` 读。

### ShopifyExporterPlugin（新加，全 config 自治）

```python
# src/plugins/shopify_exporter/plugin.py
class ShopifyExporterPlugin(BasePlugin):
    name = "shopify_exporter"

    def __init__(self, config: dict, emit_event):
        self._emit_event = emit_event
        self._endpoint = config["endpoint"]          # required
        self._token = os.environ.get(config.get("token_env", "SHOPIFY_TOKEN"), "")
        self._min_csat = config.get("min_csat", 4)
        data_dir = Path(config.get("data_dir") or default_plugin_data_dir("shopify_exporter"))
        self._path = data_dir / "exported.json"
        self._state = self._load()

    async def on_ws_event(self, event: dict) -> None:
        if event.get("event") != "csat_recorded":
            return
        if (event.get("data") or {}).get("score", 0) < self._min_csat:
            return
        channel = event.get("channel") or ""
        if channel in self._state["exported"]:
            return
        # aiohttp POST ... 见主库 docs/guide/007-plugin-guide.md §7.3
```

**零改动 `__main__.py`** — 加目录 + plugins.toml section 即上线。

## `__main__.py` 改造后形态

```python
# 前（现状）：~14 行硬编码 register
# 后：
from channel_server.plugin_loader import load_plugins
plugins_cfg = tomllib.loads((project_dir / "plugins.toml").read_text()) \
    if (project_dir / "plugins.toml").exists() else {}
load_plugins(
    registry=registry,
    config_map=plugins_cfg.get("plugins", {}),
    injections={"emit_event": emit_event, "emit_command": emit_command},
    plugin_packages=["plugins"],  # 未来可加第三方路径
)
```

`plugin_loader.load_plugins()` 负责：
1. 枚举每个 `plugins.<name>` package
2. 找 `<Name>Plugin` 类（或从 `plugin.py::MAIN_CLASS`）
3. 读 `config_map[name]`，`enabled=False` → skip
4. Inspect `__init__` signature 决定要注入哪些 kw（emit_event/emit_command/audit/…）
5. `registry.register(instance)`

## 测试影响

### 要改的测试文件

**影响程度低（改 fixture 实例化方式）**：
- `zchat-channel-server/tests/unit/test_audit_plugin.py` — fixture `AuditPlugin(persist_path=tmp_path/"x.json")` → `AuditPlugin(config={"data_dir": str(tmp_path)}, emit_event=mock)`
- `tests/unit/test_activation_plugin.py` — 同 pattern
- `tests/unit/test_mode_plugin.py` — `ModePlugin(emit_event=mock)` → `ModePlugin({}, mock)`
- `tests/unit/test_resolve_plugin.py` — 同
- `tests/unit/test_sla_plugin.py` — 12 个测试，每个 fixture 都要改，但改动是机械的
- `tests/unit/test_csat_plugin.py` — `(emit_event, audit_plugin)` → `(config, emit_event, audit=audit_plugin)`

**影响程度中**：
- `tests/unit/test_plugin_registry.py` — 11 个测试跑 register/query 逻辑，不受影响（loader 是新组件，registry 契约不变）
- `tests/e2e/test_plugin_pipeline.py` / `test_csat_lifecycle.py` / `test_help_request_lifecycle.py` / `test_bridge_lazy_create.py` — 启动 CS 时走新 loader，但 fixture 层提供 plugins.toml 模拟即可

### 新增测试

- `tests/unit/test_plugin_loader.py`（新建）：
  - enumerates packages
  - 读 config_map 并 skip `enabled=false`
  - signature-driven DI（csat 能拿到 audit）
  - 同名冲突（两个 plugin 都声明 `name="audit"`）
  - 删 plugin 目录后 discovery skip 它
  - plugins.toml 不存在时行为（全部走默认）

预计 ~15 个 test case。

### 测试预期基线（迁移完成）

- unit 从 179 → ~190（+11 新 loader tests）
- e2e 12 保持不变
- all 从 191 → ~202

## 用户决策点

**D-1：是否支持第三方 plugin 目录？**

选项：
- (a) 只扫 builtin `src/plugins/` — 简单，第三方用户要把目录 copy 进来
- (b) 扫 builtin + `~/.zchat/plugins/` 用户目录 — 用户自己可加 plugin 无需改 CS repo
- (c) 走 Python entry_points（`entry_points = {"zchat.plugins": ["foo = pkg.plugin:FooPlugin"]}`）— 标准 setuptools 模式，打包发布友好

**推荐**：先做 (a)+(b)，后续（如真有第三方生态需求）再做 (c)。

**D-2：是否保留 CS_DATA_DIR env 兜底？**

选项：
- (a) 保留 — 对 E2E 测试隔离和简单部署友好
- (b) 删掉，完全靠 plugins.toml — 更"纯粹"但 E2E fixture 要每个都写 plugins.toml

**推荐**：(a)，保留作为 plugin 未配置 data_dir 时的 fallback 链条第 3 级。

**D-3：plugin 互访方式？**

选项：
- (a) signature-driven DI — loader 检查 `__init__` kw 名，自动注入（csat 的 `audit=None`）。只显式声明的能注入。
- (b) 所有 plugin 有 `registry` 引用，可随时 lookup — 太宽松，打破隔离
- (c) 显式 `[plugins.csat] requires = ["audit"]` 在 plugins.toml 里声明 — 最显性但冗余

**推荐**：(a) 和 (c) 结合 — `__init__` 里有 kw 参数隐含依赖，plugins.toml 里可选 `requires` 列表做双重保险（loader 优先 requires，fallback 到 signature inspection）。

**D-4：破坏性改动时机？**

dev 分支目前 `69f4f78`（含 V6 Skill 1 regen），CS 子模块 `726540d`（V6 finalize）。这次重构要在 CS 子模块 `refactor/v4` 上开新分支还是继续在 `refactor/v4` 上推？

**推荐**：开 `refactor/cs-plugin-autonomy` 分支做，完整测试过后 PR 回 `refactor/v4` → dev。

**D-5：文档同步**

完整版会让主库 `docs/guide/007-plugin-guide.md` 里的几段过时：
- §7 "两类 plugin" 分类要删（核心论点验证后）
- §6 "添加 plugin 的 6 步流程" 要改为"3 步：加目录 + plugin.py + plugins.toml section"
- §4.1 存储路径小节从"`__main__` 集中注入"改为"plugin 从 config 读 data_dir"

是否此次重构**同步更新 guide**？

**推荐**：是。code + doc 一起合到 dev，保持一致。

## 工作量拆解

| 步骤 | 估时 | 产出 |
|---|---|---|
| 1. 写 `channel_server/plugin_loader.py`（discovery + config + DI）| 3h | ~150 LOC + 单测 |
| 2. 改 6 个 plugin 的 `__init__` 签名 | 2h | 每个 ~10 行 delta |
| 3. 改 6 个 plugin 的测试 fixture | 2h | 机械改动 |
| 4. 改 `__main__.py` register 段为 loader 调用 | 0.5h | -14 +10 lines |
| 5. 写 `paths.default_plugin_data_dir()` helper | 0.5h | ~20 LOC + 单测 |
| 6. 新 loader 单元测试 `test_plugin_loader.py` | 2h | 15 test case |
| 7. 更新 pre-release e2e fixture 构造 plugins.toml | 1h | 影响 4 个 e2e file |
| 8. 更新主库 `docs/guide/007-plugin-guide.md` | 1h | 改 §4 / §6 / §7 |
| 9. 写 sample `plugins.toml` + routing.example.toml 加说明 | 0.5h | 文档 |
| 10. 代码审查 + ralph-loop 1-2 轮稳定 | 2h | 收敛 |

**总计**：~14.5h ≈ 1.5-2 人日。比之前估的 1-1.5 人日稍多（加了 loader 单测 + 文档同步）。

## 确认决策（2026-04-22）

- **D-1**：✅ (a)+(b) — 扫 builtin `src/plugins/` + 用户 `~/.zchat/plugins/`。不做 entry_points。
- **D-2**：✅ **删掉 CS_DATA_DIR** env 兜底。plugin data_dir fallback 链条缩成：`config.data_dir` → `<project>/plugins/<name>/`（由 `paths.default_plugin_data_dir(name)` 统一决定，基于 routing.toml 所在目录）。E2E 测试 fixture 要构造 plugins.toml。
- **D-3**：✅ (a) **signature-driven DI**。Loader 检查 `__init__` 的 kw-only 参数名，从 registry 按名字注入已 register 的 plugin 引用。plugins.toml 不加 `requires` 字段（避免两处真相）。
- **D-4**：✅ 从 **dev 分支切 `refactor/plugin`** 开始。完成后 PR → dev。
- **D-5**：✅ 全量同步：
  - docs/guide/007-plugin-guide.md 重写 §4 / §6 / §7（删两类分法、改步骤、改路径说明）
  - 扫 docs/guide/ 所有文档涉及 plugin 的表述都查一遍并同步
  - 按 Skill 0 Step 7 流程重生 Skill 1（主库 project-discussion-zchat + CS project-discussion-channel-server）
  - `.artifacts/bootstrap/module-reports/plugins.json` 等受影响文件同步更新

## 后续行动

- [x] eval-doc 已写入 `.artifacts/eval-docs/eval-cs-plugin-config-autonomy-014.md`
- [x] 注册到 `.artifacts/registry.json`（id=eval-doc-014）
- [x] 用户 confirm 5 个决策点 + testcase 表格 → status draft → **confirmed**
- [ ] 切分支 `refactor/plugin` from dev
- [ ] 实现 plugin_loader + paths.default_plugin_data_dir + 迁移 6 个 plugin __init__
- [ ] 改 `__main__.py` register 段为 loader 调用
- [ ] 更新所有 plugin unit test fixture
- [ ] 写 `test_plugin_loader.py`（~15 case）
- [ ] 更新 e2e fixture（构造 plugins.toml）
- [ ] 主库 `docs/guide/007-plugin-guide.md` 重写 §4/§6/§7
- [ ] 主库 `docs/guide/` 其他文档 plugin 表述扫查同步
- [ ] 按 Skill 0 Step 7 重生 主库 + CS 的 Skill 1
- [ ] 同步 `.artifacts/bootstrap/module-reports/`（主库 + CS）
- [ ] CS 子模块 PR `refactor/plugin` → `dev`
- [ ] 主库 PR `refactor/plugin` → `dev`（bump CS submodule 指针）
- [ ] **Ralph-loop 收敛**（≥2 轮）：扫失效测试 + 旧代码 + 文档 vs 实现一致性
  - 关键扫查：grep 所有 `persist_path=` / `state_file=` / `CS_DATA_DIR` / `AuditPlugin(` / `ActivationPlugin(` / `_handle_register_plugin` 等旧 pattern
  - 确认 `docs/guide/007-plugin-guide.md` 里的代码示例全部对齐新签名
  - 确认 `.artifacts/bootstrap/module-reports/plugins.json` 的 file:line 引用与新代码一致
