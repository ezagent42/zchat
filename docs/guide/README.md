# docs/guide

按编号阅读指南。每篇独立可读，但建议从 001 顺序看一遍。

| # | 文件 | 受众 | 阅读时间 |
|---|---|---|---|
| 001 | [architecture](001-architecture.md) | 想理解 zchat 整体的人 | 15 min |
| 002 | [quick-start](002-quick-start.md) | 第一次跑 zchat 的人 | 30 min（含装环境） |
| 003 | [e2e-pre-release-test](003-e2e-pre-release-test.md) | 真机 E2E 测试人员 / 验收人 | 90 min（含跑测试） |
| 004 | [migrate-guide](004-migrate-guide.md) | 把已有客服系统（如 AutoService）迁到 zchat 的工程团队 | 30 min |
| 005 | [dev-guide](005-dev-guide.md) | 想改 zchat 内部的开发者 | 20 min（Q&A 形式可索引查询） |
| 006 | [routing-config](006-routing-config.md) | 配 / 改 routing.toml 的人 | 15 min |
| 007 | [plugin-guide](007-plugin-guide.md) | 想写新 plugin / 对接外部系统的人 | 25 min |
| 008 | [voice-setup](008-voice-setup.md) | 接入 voice 通话能力 | 10 min |

## 常见入口

- **第一次接触**: 001 → 002
- **要部署生产**: 002 → 003 → 006
- **要把自己产品接入 zchat**: 001 → 004 → 006
- **要给 zchat 提 PR**: 005 → 001
- **要调一个 bug**: 005 (按 Q 找)
- **写 / 改 routing.toml**: 006
- **加 plugin / 对接外部系统**: 007（先读 001 §3）

## 关联

- 设计 / 历史决策: `../discuss/`
- 老 upstream 文档归档: `../archive/`
- evidence chain: `../../.artifacts/`
