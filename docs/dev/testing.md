# 测试

## 测试架构

| 类型 | 目录 | 特点 |
|------|------|------|
| Unit | `tests/unit/` | Mock IRC client，快速，无外部依赖 |
| Integration | `tests/integration/` | 真实 IRC 连接，需要 ergo server 运行 |
| E2E | `tests/e2e/` | 完整系统测试，需要 ergo + tmux |

## 运行测试

```bash
# Unit 测试
cd weechat-channel-server && uv run python -m pytest ../tests/unit/ -v

# E2E 测试
pytest tests/e2e/ -v -m e2e

# 单个测试
pytest tests/unit/test_message.py::test_specific -v
```

## 添加测试

### Unit Test

- 放在 `tests/unit/` 下
- 文件命名：`test_<模块名>.py`
- 异步测试自动支持（`asyncio_mode = auto`）

### E2E Test

- 放在 `tests/e2e/` 下
- 使用 `@pytest.mark.e2e` 标记
- 需要 ergo IRC server + tmux 运行环境
