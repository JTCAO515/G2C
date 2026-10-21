# CJ Agent 文档与后续工程入口

JT 已授权正式开发；唯一 CJ Main 与现有常驻职责见 [engineering](docs/engineering.md#角色与写权)。PR #36 已合并，仅建立文档基线，不代表产品实现或验收通过。本次 CJ-DOC-36 返修仅改指定文档，不创建线程。

- 先读本机唯一 HANDOFF：`/Users/jtsm5p/Documents/Codex/2026-10-21/task-5/HANDOFF.md`，再读 [README](README.md) 和 [readiness](docs/readiness.md)，核当前授权、remote/base/head/dirty，保留既有改动。HANDOFF 仅由唯一 Main 维护，原 Main 不恢复。
- 范围/依赖读 [CJ-005 索引](https://github.com/JTCAO515/Go2China/issues/5)；改技术方案先读 [ADR](docs/adr/README.md)，改行为读对应规格。
- API 或跨模块变更读 [contracts](docs/contracts.md)；记忆变更读 [memory](docs/memory.md)；布局变更读 [ui](docs/ui.md)；派工、测试、集成或环境准备读 [engineering](docs/engineering.md)。
- 所有新线程归 Codex **CJ Agent** 项目；不在旧 VP 项目开发。Main 仅协调，Testing/Review/Publish 已有独立 owner；模型 effective 均为 UNKNOWN，不把 requested 或目录可用当配置成功。
- 按 Main 明确的文件/分支写权协作；本任务保留原文档工作树 owner，仅修授权/协作状态，Issue 和 HANDOFF 只读。
- 固定契约版本与正负样例后可并行；H 起工依赖与 I 真实集成门槛分开。mock、合并、真实服务和真机分层报告；未知写入先读回，不盲重试或绕过保护。

PR #36 基线没有已实现的运行命令、schema 或兼容矩阵。先从对应 Issue 交付真实结果，再更新文档；本次文档返修不启动试验或安装。开发授权不扩大到付费调用、云资源、权限/凭据变更、外联、公开发布或旧数据删除。
