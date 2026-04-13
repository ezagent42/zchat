# zchat 完整介绍指南

从底层原理到上层应用，3 小时掌握 zchat 多 Agent 协作系统。

## 目录

| 章 | 主题 | 时间 |
|----|------|------|
| [第零章](./00-overview.md) | 全局概览与学习路线 | 15 min |
| [第一章](./01-irc-fundamentals.md) | IRC 协议基础——为什么选 IRC | 20 min |
| [第二章](./02-protocol.md) | zchat-protocol——命名规范与系统消息 | 20 min |
| [第三章](./03-channel-server.md) | zchat-channel-server——MCP ↔ IRC 桥接 | 30 min |
| [第四章](./04-cli-project.md) | zchat CLI——项目与配置管理 | 25 min |
| [第五章](./05-agent-lifecycle.md) | zchat CLI——Agent 生命周期管理 | 25 min |
| [第六章](./06-irc-auth.md) | zchat CLI——IRC 与认证管理 | 20 min |
| [第七章](./07-weechat-plugin.md) | WeeChat 插件——用户界面层 | 15 min |
| [第八章](./08-end-to-end.md) | 消息全链路 + 运维 + 扩展 | 30 min |

**总计约 3 小时**

## 阅读建议

- 按顺序阅读，每章都依赖前一章的知识
- 每章都标注了源码位置（文件路径 + 行号），可随时跳转查看实际代码
- 第八章的"快速参考"表格可作为日常速查卡
