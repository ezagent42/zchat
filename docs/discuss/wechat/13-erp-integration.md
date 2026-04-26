# 13 · ERP 接入路线 — IM × zchat × ERP 三层集成

> **目标**：让 zchat 的客服 agent 能在对话中实时调 ERP 接口（查订单、库存、退货流程），形成"客户问 → agent → ERP API → 答 → 推 IM"闭环。
> **范围**：架构方案 + 主流 ERP 选型 + zchat 侧落地实现。
> **不在范围**：具体业务字段映射（每个客户 ERP 字段不同）。

## 1. 业务场景

PRD 隐含的 ERP 调用场景（user stories 中提到的 "订单/物流/清关/库存/CRM/价格"）：

| 客户场景 | 需要 ERP 提供 |
|---|---|
| "我的订单 ABC123 到哪了？" | 订单详情 + 物流轨迹 |
| "你们 X 商品还有货吗？" | 库存查询 |
| "我要退这单" | 订单状态 + 退货政策 + 创建退货工单 |
| "这商品多少钱？" | 价格 + 促销 |
| "我之前买过的" | 客户历史订单 |
| "加我会员" | 会员注册 + 等级查询 |

zchat 当前的 deep-agent 设计就是为这种"专家级查询"准备的（fast → delegate-to-deep）。但 deep-agent 缺一条腿：**没有 ERP API 工具**。

## 2. 百联调研结论

> 已查：百联官网、百联 E 城开发者文档、用友 / 金蝶 等通用 ERP

**百联集团**（上海百联）：
- 业务：百联股份 + 联华超市 + 百联 E 商 + 7000+ 网点
- 数字化平台：i百联（整合后的电商前端），底层是混合云 + SaaS 生态
- **没有公开的开放 API**：没找到 developer / partner / open platform 文档
- 真要接入：必须**直接对接百联 IT 部**走商务合作 → 项目级定制

**百联 → ERP 接入：可行性低**（除非有商务关系）。退路：

## 3. 通用 ERP 选型（按可接入性排序）

| ERP | 类型 | 开放 API | 适合场景 | 文档 |
|---|---|---|---|---|
| **用友 YonSuite / NC Cloud** | 大企业 ERP | ✅ developer.yonyou.com，有完整 OpenAPI | 大型零售 / 制造 / 集团 | https://developer.yonyou.com/openAPI |
| **金蝶 Cloud Galaxy / KIS** | 中大型 ERP | ✅ 开放平台 + 应用市场 | 中小企业 / 零售 | https://open.kingdee.com |
| **管易云 (阿里系)** | 电商 ERP | ✅ 偏淘宝/京东后端 | 中小电商 | https://open.guanyierp.com |
| **百胜 (BSD)** | 零售连锁 ERP | ⚠️ 闭源，需商务对接 | 大型连锁（百联 / 大润发等可能用）| — |
| **海鼎 (Haiding)** | 零售 ERP | ⚠️ 闭源，需商务 | 同上 | — |
| **SAP S/4HANA** | 大型企业 ERP | ✅ OData / RFC | 跨国企业 | api.sap.com |
| **Oracle ERP Cloud** | 大型企业 | ✅ REST | 跨国企业 | docs.oracle.com |

**zchat MVP 推荐**：
1. 用友（最常见 + 文档齐 + 国内中小企业占有率高）
2. 金蝶（同）
3. SAP（如果商户跨国）

百联具体如果客户要求，单独 case 处理（商务对接）。

## 4. 接入架构 — IM × zchat × ERP 三层

```
                                                 客户
                                                  │ 飞书 / WeCom
                                                  ▼
                                      ┌──────────────────────┐
                                      │  feishu / wecom      │
                                      │  bridge              │
                                      └──────────┬───────────┘
                                                 │ ws_messages → IRC
                                                 ▼
                                          channel_server
                                                 │
                                                 ▼
                                          fast-agent (entry)
                                            │
                                            │ delegate-to-deep
                                            ▼
                                          deep-agent
                                            │
                                            │ MCP tool
                                            ▼
        ┌────────────────────────────────────────────────────┐
        │  erp_mcp_server  (新组件)                           │
        │  - 提供 deep-agent 可调的 MCP tools                  │
        │     · query_order(order_id)                        │
        │     · query_inventory(sku)                         │
        │     · query_customer(external_id)                  │
        │     · create_return(order_id, reason)              │
        │  - 适配多种 ERP backend (driver pattern)             │
        └─────────────┬───────────┬──────────────┬────────────┘
                      │           │              │
              ┌───────▼──┐  ┌─────▼─────┐  ┌────▼─────┐
              │ Yonyou   │  │ Kingdee   │  │ SAP / etc│
              │ HTTP API │  │ HTTP API  │  │ OData    │
              └──────────┘  └───────────┘  └──────────┘
```

## 5. 选 MCP Tool 不选 plugin/bridge

为什么放在**MCP tool 层**而不是 zchat plugin / bridge？

| 选项 | 评估 |
|---|---|
| ❌ plugin (in-process CS) | plugin 设计是接 CS 事件做副作用，不适合"agent 主动调"模式 |
| ❌ bridge (独立进程接 IM) | bridge 是 IM 适配器，不适合 ERP（不是消息源）|
| ✅ MCP tool (agent 自主调) | agent 可以根据对话上下文按需调，匹配 LLM 自主决策范式 |

而且 zchat 已有 `agent_mcp.py` 里的 tool 注册机制（reply / list_peers / voice_link 等），加 ERP tool 是同模式。

## 6. erp_mcp_server 设计

新增独立 Python 包 `erp_mcp_server/`，结构跟 voice_bridge / wecom_bridge 平级：

```
src/erp_mcp_server/
├── __init__.py
├── __main__.py                  入口：python -m erp_mcp_server
├── server.py                    MCP stdio server (类似 agent_mcp.py)
├── config.py                    读 credentials/erp.json
│
├── tools/                       MCP tool 实现
│   ├── orders.py                query_order, create_return
│   ├── inventory.py             query_inventory
│   ├── customers.py             query_customer, get_history
│   └── catalog.py               query_product, query_price
│
└── drivers/                     ERP backend adapters
    ├── base.py                  ABC: ERPDriver { query_order(...), ... }
    ├── yonyou.py                用友 driver
    ├── kingdee.py               金蝶 driver
    ├── sap.py                   SAP driver
    └── mock.py                  本地 mock 用于开发
```

driver 模式让 ERP 替换不影响 tool 层。

## 7. MCP tool schema 示例

```python
# erp_mcp_server/tools/orders.py
from mcp.types import Tool

QUERY_ORDER = Tool(
    name="query_order",
    description=(
        "Query an order's status, line items, and shipment info from ERP.\n\n"
        "Use this when:\n"
        "- Customer asks 'where is my order #X' / 'order status'\n"
        "- Need to verify order before processing return\n"
        "- Customer references previous purchase\n\n"
        "Parameters:\n"
        "- order_id (required): Customer-facing order number (e.g. 'ABC123')\n"
        "- include_shipment (optional, default true): Pull logistics tracking too\n\n"
        "Returns JSON: {status, items[], shipped_at, tracking_no, total, customer_id}"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "include_shipment": {"type": "boolean", "default": True}
        },
        "required": ["order_id"]
    }
)

async def handle_query_order(args: dict, driver: ERPDriver) -> dict:
    order_id = args["order_id"]
    try:
        order = await driver.query_order(order_id)
        if args.get("include_shipment", True):
            order["tracking"] = await driver.get_shipment(order_id)
        return order
    except OrderNotFound:
        return {"error": "order_not_found", "hint": "Check order_id format"}
    except ERPDownError:
        return {"error": "erp_unavailable", "retry_after_seconds": 60}
```

## 8. driver 接口

```python
# erp_mcp_server/drivers/base.py
from abc import ABC, abstractmethod

class ERPDriver(ABC):
    @abstractmethod
    async def query_order(self, order_id: str) -> dict: ...
    @abstractmethod
    async def query_inventory(self, sku: str) -> dict: ...
    @abstractmethod
    async def query_customer(self, external_id: str) -> dict: ...
    @abstractmethod
    async def get_shipment(self, order_id: str) -> dict: ...
    @abstractmethod
    async def create_return(self, order_id: str, reason: str) -> str: ...
```

每个 driver 适配具体 ERP 的字段差异，统一返回结构。

## 9. 用友 driver 示例

```python
# erp_mcp_server/drivers/yonyou.py
import httpx
from .base import ERPDriver

class YonyouDriver(ERPDriver):
    """用友 NC Cloud / YonSuite OpenAPI driver.

    Auth: OAuth2 client_credentials. token TTL 7200s.
    Rate limit: 各接口不同，详见 developer.yonyou.com.
    """

    def __init__(self, base_url: str, client_id: str, client_secret: str,
                 tenant_id: str):
        self._base = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant_id = tenant_id
        self._http = httpx.AsyncClient(timeout=10)
        self._token: str | None = None
        self._token_exp: float = 0

    async def _get_token(self) -> str:
        import time
        if self._token and self._token_exp > time.time() + 60:
            return self._token
        resp = await self._http.post(
            f"{self._base}/iuap-api-auth/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 7200))
        return self._token

    async def query_order(self, order_id: str) -> dict:
        token = await self._get_token()
        resp = await self._http.get(
            f"{self._base}/yonbip/scm/sale/order/info",
            headers={"Authorization": f"Bearer {token}",
                      "tenant-id": self._tenant_id},
            params={"order_no": order_id},
        )
        if resp.status_code == 404:
            raise OrderNotFound(order_id)
        resp.raise_for_status()
        raw = resp.json().get("data", {})
        # 字段映射：用友 → 标准化结构
        return {
            "id": raw.get("order_no"),
            "status": _map_status(raw.get("status_code")),
            "items": [
                {"sku": i["product_code"], "qty": i["quantity"], "price": i["unit_price"]}
                for i in raw.get("lines", [])
            ],
            "total": raw.get("total_amount"),
            "customer_id": raw.get("customer_code"),
            "shipped_at": raw.get("ship_date"),
        }

    # ... 其他方法
```

## 10. 凭证 + 配置

```json
// ~/.zchat/projects/<proj>/credentials/erp.json
{
  "type": "yonyou",
  "base_url": "https://api.diwork.com",
  "client_id": "xxx",
  "client_secret": "yyy",
  "tenant_id": "tenant-001"
}
```

routing.toml 加：
```toml
[erp]
enabled = true
credentials_file = "credentials/erp.json"
```

## 11. agent template 集成

在 deep-agent template 的 `.env.example` 加：
```
ERP_MCP_SERVER_URL=stdio:///path/to/erp_mcp_server
```

deep-agent 的 `.mcp.json` 已经有 zchat-agent-mcp，再加一个 erp-mcp:
```json
{
  "mcpServers": {
    "zchat-agent-mcp": { ... },
    "erp": {
      "command": "python",
      "args": ["-m", "erp_mcp_server"],
      "env": {
        "ERP_CONFIG_PATH": "{{erp_config_path}}"
      }
    }
  }
}
```

deep-agent 启动后自动看到 `query_order` 等 tool。soul.md 加：

```markdown
## ERP Tools
- `mcp__erp__query_order(order_id)` — 查订单状态 / 物流
- `mcp__erp__query_inventory(sku)` — 查库存
- `mcp__erp__query_customer(external_id)` — 查客户档案 / 历史订单
- `mcp__erp__create_return(order_id, reason)` — 创退货工单

客户问订单 / 库存 / 退货时优先调 ERP tool。**查不到** → 走 escalate-to-operator，不要编。
```

## 12. fast → deep → ERP 完整链路

```
客户在飞书/WeCom: "我的订单 ABC123 到哪了？"
   │
   ▼
feishu/wecom_bridge → ws_messages → CS → IRC #conv-001
   │
   ▼
fast-agent 收到 → 识别"复杂查询" → delegate-to-deep skill
   │
   ▼ side: @yaosh-deep-001 客户问订单 ABC123 状态
deep-agent 收到 side → 调 mcp__erp__query_order(order_id="ABC123")
   │
   ▼
erp_mcp_server.handle_query_order → YonyouDriver.query_order
   │ HTTPS → 用友 OpenAPI
   ▼
返回 {status: "shipped", tracking: "顺丰SF123"}
   │
   ▼
deep-agent 用 reply tool 答（side=true 给 fast-agent，因为 side 协商规则）
   │
   ▼
fast-agent 收到 deep 的 side → 用 __msg 答客户："您的订单 ABC123 已发货
   │                                            (顺丰 SF123)，预计明天到达"
   ▼
ws_messages → bridge → 飞书/WeCom 群 → 客户看到
```

## 13. 安全 / 合规

| 项 | 措施 |
|---|---|
| 客户信息不流转 | erp_mcp_server 每次查后**仅返回当前问题相关字段**，不缓存全档 |
| ERP 凭证 | credentials/erp.json，chmod 600，gitignore |
| 限流 | tool 层加 token bucket（防 LLM 暴调）|
| 审计 | 每次 ERP 调用 log 到 audit plugin（who / what / when）|
| GDPR | 客户主张数据删除 → tool `forget_customer(external_id)` 调 ERP 删档 |

## 14. 失败模式

| 场景 | 处理 |
|---|---|
| ERP 网络不通 | tool 返回 `{error: "erp_unavailable"}` → agent 走 escalate "客服系统暂时无法查询，请稍候" |
| order_id 不存在 | tool 返回 `{error: "order_not_found"}` → agent 答 "未找到该订单号，请确认是否正确" |
| 用友 token 过期 | driver 自动 refresh + retry 1 次 |
| 限流命中 | tool 返回 `{error: "rate_limited", retry_after: 60}` → agent 致歉延迟 |

## 15. Phase 计划（给 ERP 集成一个独立 minor）

| Phase | 工作日 | 内容 |
|---|---|---|
| E0 | 1 | erp_mcp_server skeleton + base ERPDriver + Mock driver |
| E1 | 3 | Yonyou driver 实现 4 个核心 tool（order/inventory/customer/return）|
| E2 | 1 | deep-agent template 集成 + soul.md 加 ERP 段 |
| E3 | 2 | 真用友 sandbox 联调 + 实测 |
| E4 | 1 | audit / 限流 / 监控 |
| **总** | **8 工作日 (~2 周)** | |

## 16. 多 ERP 并存（同商户接 2 套 ERP）

某些大商户：电商单走管易云 + 线下走百胜
- erp.json schema 改 array：`[{type: "guanyiyun", ...}, {type: "baisheng", ...}]`
- driver 分发：order_id 前缀 `O-` → guanyiyun；`S-` → baisheng
- agent tool 接口不变，driver 内部分流

## 17. 跟现有架构的兼容性

| 模块 | 影响 |
|---|---|
| channel_server / IRC / agent_mcp | ✅ 零影响（erp 是新独立 MCP server）|
| feishu_bridge / wecom_bridge | ✅ 零影响 |
| audit plugin | 加一类 event："erp_query"（可选）|
| zchat CLI | 加 `zchat erp test --tool query_order --order-id X` 调试命令 |
| 飞书 WeCom | 同时可用，agent 看不到差异 |

## 18. 百联具体路径（如果客户必须接百联）

商务 + 技术双轨：

1. **商务**：联系百联 IT 部门，谈 partner 合作
2. **技术**（拿到 API 后）：写 `erp_mcp_server/drivers/bailian.py`，跟 yonyou.py 同接口
3. **闭源 spec 的话**：可能要走"接管百联客服系统出口"模式 — 让 agent 模拟客服员工调内部系统（更复杂）

实际操作：先用 yonyou / kingdee 验证整套链路，等百联商务搞定再加 driver。

## 19. 关联

- agent_mcp tool 注册参考: `zchat-channel-server/src/agent_mcp.py:_build_tool_list`
- voice_link 类似的 MCP tool: `zchat-channel-server/src/agent_mcp.py:_handle_voice_link`
- soul.md 集成参考: `zchat/cli/templates/fast-agent/soul.md` (voice_link 那段)
- Yonyou: https://developer.yonyou.com/openAPI
- Kingdee: https://open.kingdee.com
- 百联: 无公开文档，需商务对接
