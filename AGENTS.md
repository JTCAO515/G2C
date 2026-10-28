# CJ Agent / G2C 工程入口（所有 Coding Agent）

本仓库自足可续作：不依赖任何本机文件或私聊历史。冲突时事实优先级为：JT 当前指令 > 仓库 / Git / Issue / CI 实况 > `docs/handoff.json` > 历史摘要 > 推断。

## 强制阅读顺序

1. [HANDOFF.md](HANDOFF.md)（由 [docs/handoff.json](docs/handoff.json) 生成；改 JSON 后重新渲染，不手改 HANDOFF.md）
2. [ADR-0007](docs/adr/0007-issue-closure-workflow.md)（关票流程，accepted），再按需读 [ADR 索引](docs/adr/README.md)
3. [Issue 总体规划](docs/plan/issue-plan.md)，以及当前子票和父票的正文与评论（handoff 的 `nextAction` 指明是哪一张）；`docs/dispatch/*` 已冻结为历史，只在子票引用时读
4. [README](README.md)；按改动类型再读：API/跨模块 [contracts](docs/contracts.md)、记忆 [memory](docs/memory.md)、布局 [ui](docs/ui.md)、范围 [scope](docs/scope.md)、协作与环境 [engineering](docs/engineering.md)

范围与依赖索引：[CJ-005 / #5](https://github.com/JTCAO515/G2C/issues/5)。

## 关票规则（ADR-0007）

- 目标是关闭 Issue。执行单位是子票：2–6 个验收框，每个框标明证据级别 L0–L3，预计 1–2 个 PR。
- 功能票在 L0/L1 证据全部 PASS 时关闭；只能在 L2/L3 证明的框改写为 `→ L2 #32` 或 `→ L3 #29`，并到对应验证票登记，不删除。
- 并行线：最多 3 条线，每条线一个会话、1 张父票、最多 1 个开着的 PR；只改本线拥有的文件，共享文件同一时间只允许一个 PR 修改（ADR-0007 第 2 条）。线与队列见 [docs/plan/issue-plan.md](docs/plan/issue-plan.md)“并行线”，当前位置见 handoff 的 `nextAction`。owner 为 Claude 的子票 Codex 不认领。子票级停点（含前置子票未关闭）评论阻塞后跳过，继续队列；仓库级停点停止会话（ADR-0007 第 7 条）。
- PR 正文第一行写 `Closes #<子票>`（两段式写 `Refs #<子票>` 加 `Part 1/2`）。合并后在子票勾框并附 PR 链接，同步父票。
- 范围外发现的问题开新票记录，不顺手修。
- 自动续作（ADR-0007 第 7 条）：合并后先确认 main CI 全绿，再按队列取下一张子票；main 变红先修复或 revert；队列做完或碰到仓库级停点就停，并在 handoff 写明原因。

## 工作规则

- 新增或修改校验、清理内部重复防御时，遵循 [信任边界规则](docs/engineering.md#信任边界)：边界/安全检查保留，领域对象构造时校验一次。
- 从最新 `main` 开分支，经 PR 合并；禁止直推 main、force push、改写历史。
- 合并条件：PR 精确 head 上 CI 全部 job 全绿；不继承作者上下文的 Codex 审查会话在 PR 评论写 `Review: APPROVE <head SHA>` 并附逐项核对；合并时用 `--match-head-commit` 锁定该 head。
- 红线 PR（迁移/表结构、契约、鉴权权限、签名密钥、删除用户数据、付费计费、CI 与门禁）由 Codex 审查，但审查评论必须逐条写明 ADR-0007 第 3 条的追加必查项结果。
- 审查清单补充：新增的校验是否在信任边界上，内部是否重复防御；删除项逐条确认未移除任何边界、隔离或安全检查。
- 必须停下来等 JT、不能自行合并：授权清单外的外部资源或仓库/云/密钥设置；修改 ADR、`AGENTS.md`、`docs/authorizations/**` 或放宽门禁；真实环境的不可逆操作；付费、商店或对外承诺。
- PR 描述含精确 base/head、是否红线、验收框 → 证据表（PASS / FAIL / UNRUN / UNKNOWN）。
- 新的运行日志、进程记录、压缩包、录屏不入库；放 CI artifact 或 PR 描述。仓库内不写本机绝对路径、秘密或个人凭据。
- 改技术方案先读 ADR，改行为读对应规格。功能 PR 不改 handoff，进度记在子票评论；会话结束、停点或关闭父票时用只改 handoff 的 PR 更新本线条目（ADR-0007 第 6 条），并重新渲染 `HANDOFF.md`。
- 未知写入先只读核原动作再决定重试；被平台拒绝不换路径、身份或工具绕过。mock、本地、真实服务与真机证据分层报告。
- 外部资源只在 JT 已批准的 `docs/authorizations/<里程碑>.md` 清单内使用；清单外的付费调用、云资源、权限/凭据变更、外联、公开发布或旧数据删除，先停下来问 JT。
