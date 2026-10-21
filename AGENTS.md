# CJ Agent 文档与后续工程入口

当前仅开工前文档准备。产品开发须等待 JT 明确确认；README 与 readiness 的状态不能由文档提交或 Issue 无 blocker 自动改成已开工。

- 先读 [README](README.md) 和 [readiness](docs/readiness.md)，核当前授权、remote/base/head/dirty，保留既有改动。
- 范围/依赖读 [CJ-005 索引](https://github.com/JTCAO515/Go2China/issues/5)；改技术方案先读 [ADR](docs/adr/README.md)，改行为读对应规格。
- API 或跨模块变更读 [contracts](docs/contracts.md)；记忆变更读 [memory](docs/memory.md)；布局变更读 [ui](docs/ui.md)；派工、测试、集成或环境准备读 [engineering](docs/engineering.md)。
- 所有新线程归 Codex **CJ Agent** 项目；不在旧 VP 项目开发。Main 仅协调，Testing/Review/Publish 职责独立；实际创建仍需开工授权。
- 本轮唯一仓库文档 writer；Issue 由独立规划任务维护，本任务只读。未来按明确文件/分支写权协作。
- 固定契约版本与正负样例后可并行；H 起工依赖与 I 真实集成门槛分开。mock、合并、真实服务和真机分层报告；未知写入先读回，不盲重试或绕过保护。

本仓库没有已实现的运行命令、schema 或兼容矩阵。先从对应 Issue 交付真实结果，再更新文档；不为补文档而开始试验或安装。
