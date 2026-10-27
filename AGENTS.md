# CJ Agent / G2C 工程入口（所有 Coding Agent）

本仓库自足可续作：不依赖任何本机文件或私聊历史。冲突时事实优先级为：JT 当前指令 > 仓库 / Git / Issue / CI 实况 > `docs/handoff.json` > 历史摘要 > 推断。

## 强制阅读顺序

1. [HANDOFF.md](HANDOFF.md)（由 [docs/handoff.json](docs/handoff.json) 生成；改 JSON 后重新渲染，不手改 HANDOFF.md）
2. [ADR 索引](docs/adr/README.md)，尤其 [ADR-0004](docs/adr/0004-delivery-flow-and-repo-hygiene.md)（交付流程，accepted）
3. 当前派工单 `docs/dispatch/*`（handoff 的 `nextAction` 指明哪一份）
4. [README](README.md)；按改动类型再读：API/跨模块 [contracts](docs/contracts.md)、记忆 [memory](docs/memory.md)、布局 [ui](docs/ui.md)、范围 [scope](docs/scope.md)、协作与环境 [engineering](docs/engineering.md)

范围与依赖索引：[CJ-005 / #5](https://github.com/JTCAO515/G2C/issues/5)。

## 工作规则

- 一个 PR 对应一个 Issue 切片；从最新 `main` 开分支，经 PR 合并；禁止直推 main、force push、改写历史。
- 合并条件：CI 绿 + 一次独立 Review（作者不自批）。PR 描述含精确 base/head 与 PASS / FAIL / UNRUN / UNKNOWN 表。
- 新的运行日志、进程记录、压缩包、录屏不入库；放 CI artifact 或 PR 描述。仓库内不写本机绝对路径、秘密或个人凭据。
- 改技术方案先读 ADR，改行为读对应规格；变更后同步 `docs/handoff.json` 与 `HANDOFF.md`。
- 未知写入先只读核原动作再决定重试；被平台拒绝不换路径、身份或工具绕过。mock、合并、真实服务与真机证据分层报告。
- 开发授权不扩大到付费调用、云资源、权限/凭据变更、外联、公开发布或旧数据删除；这些需 JT 另行明确授权。
