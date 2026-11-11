# eval 模块归属与 C→D 交接清单

供 Claude 完成 #760 框 1 后续的 issue-plan 更新。依据 2026-11-11 08:30 CST 派工；盘点基线为 `449a04fb98cd9f14b3dc9e4561a66b19324561d0`。本 PR 只提交本清单。C 保留 #32 六格、正式 66、JT 审阅和 #6 的交付责任。

本清单区分目标归属和生效时点。除已归 D 的 `eval/optimization/**` 外，待交模块在 Claude 更新 issue-plan、D 接收对应摘要与接口、C 确认当前文件和执行切片释放后才移交写入权。目录和文件在本次交付中保持原路径。 [派工](https://github.com/JTCAO515/G2C/issues/759#issuecomment-6783259650) · [#760](https://github.com/JTCAO515/G2C/issues/760) · [D 已交付评分器](https://github.com/JTCAO515/G2C/pull/774)

## 交接条件

| 条件 | 生效与验收 |
|---|---|
| C | C 继续拥有写入和验收。D 可只读消费固定接口和有出处的观测；修改需要 C 的明确切片/文件交接。 |
| T1 | 通用诊断、进度和报告移交。C/D 记录原提交、模块与对应测试摘要、导入/CLI/输出字段和退出码，D 显式运行适用回归。须核 `FAIL/UNKNOWN/UNRUN`、原尝试与分母、严重错误、缺测、费用三栏和 C 门槛的结果保持一致。涉及模块的 C 在途 PR 与批次文件锁释放，再由 Claude 更新 owner。 |
| T2 | 离线执行器和私有 harness 移交。满足 T1，并固定 Fake-only、签名 API/受限 PG/原 worker 的执行边界。`real.py` 导入 `cases.py`、`real_worker.py` 导入本地 runtime，C 的实现实验也依赖 runtime；须先完成 C 正式批次封存，或由 C/D 明确冻结兼容接口和独立版本接入并验证 C 调用方。取得相关 C 文件锁后才切换 owner。 |
| D 已接 | `eval/optimization/**` 已由 D 负责。E/B/F 按公开固定版和摘要消费。G 在 #785 获派的离线测试入口变更按明确文件锁执行。 |

目标归属共 134 个跟踪文件。C 保留 117 个；条件交 D 9 个（7 个根模块、2 个测试）；D 已接 8 个。每个文件在下表或批次范围中恰好覆盖一次。

## 根模块、策略与说明

| 模块/文件 | 目标归属 | 条件 | 调用与验收边界 |
|---|---|---|---|
| `eval/README.md` | C 保留 | C | 原评测入口、证据分层与门槛说明。D 接模块后只提交对应段落的文档变更，C 核真实验收引用。 |
| `eval/authorization_checkpoint.json` | C 保留 | C | 原授权账本基线。与 B 的唯一实际账本核同，D 消费只读快照。 |
| `eval/cases.py` | 交 D | T2 | Fake 场景执行及原 API/PG/worker 观测；real.py 也依赖这些场景函数。 |
| `eval/commit.py` | C 保留 | C | 原动作、确认与并发 Trip 写入的实现级故障实验，关联 #502。 |
| `eval/demo-script.md` | C 保留 | C | 旧 Demo 人工任务与原验收步骤的历史引用。 |
| `eval/demo-v2-script.md` | C 保留 | C | Lio 中英陌生人清单，关联 #702。 |
| `eval/demo_v2_evidence.py` | C 保留 | C | 按原发送和动作关联回执，服务于 #702 公网取证。 |
| `eval/demo_v2_report.py` | C 保留 | C | 按原 Demo RUN、独立判定及 Meter 归属汇总真实结果。 |
| `eval/demo_v2_transport.py` | C 保留 | C | 单次发送、原件回查与只读续接；涉及公网写入与未知结果。 |
| `eval/external.py` | C 保留 | C | 外部数据权限、传输与不可信内容实验，关联 #504。 |
| `eval/failure.py` | 交 D | T1 | 原日志的有界诊断和分类；调用方保留停派与重试决策。 |
| `eval/fees.py` | C 保留 | C | 完整供应商回执的公开价估算与 UNKNOWN 口径，关联 #6。 |
| `eval/gates.py` | C 保留 | C | JT 已批准的 #32 质量阈值、硬失败与证据覆盖，供 D 固定版本调用。 |
| `eval/hk.Dockerfile` | C 保留 | C | C 真实评测镜像入口，依赖 B 的部署与资源时段。 |
| `eval/hk.py` | C 保留 | C | 源码、镜像和现场入口绑定的真实执行准备。 |
| `eval/invariants.py` | C 保留 | C | 私有 PG 实现级不变量实验的总入口，关联 #28。 |
| `eval/isolation.py` | C 保留 | C | 受限角色、owner 隔离及越权故障实验，关联 #501。 |
| `eval/judge.py` | C 保留 | C | 原 33 对/66 例的独立状态与硬约束判定；D 的评分器已导入此判据。 |
| `eval/lio-planning-reliability.md` | C 保留 | C | 公网 UNKNOWN、截断及规划/相对时间回归原件，关联 #737/#744。 |
| `eval/lio-pr717-regressions.md` | C 保留 | C | 拒绝保存、追问和日期归属的既有发布回归，关联 #702。 |
| `eval/lio-run-plan.md` | C 保留 | C | 阶段验收、独立六格、固定 66、JT 审阅与 #6 的执行条件。 |
| `eval/memory.py` | C 保留 | C | 真实签名记忆生命周期、删除/fence 的实现实验，关联 #503。 |
| `eval/network_read.py` | C 保留 | C | 已有原 RUN 的只读目标网诊断；提交到正文的测量由原执行器另记。 |
| `eval/progress.py` | 交 D | T1 | 冻结计划上的只读进度审计；依赖 C 的费用、停止状态和原件约束。 |
| `eval/real.py` | C 保留 | C | 获批真实批次与原签名 API/RUN/Meter 出口，归 #32。 |
| `eval/real_budget.py` | C 保留 | C | 首派前原账核同、预算与调用量预检；当前值的修订走 C 原任务。 |
| `eval/real_phase.py` | C 保留 | C | 按生产 adapter 的一次性阶段认领与原封存，保持旧失败原身份。 |
| `eval/real_report.py` | C 保留 | C | 原真实 collector 的时延口径对账与历史报告兼容。 |
| `eval/real_worker.py` | C 保留 | C | 固定 memory-restart 场景的真实 worker 新进程入口。 |
| `eval/report.py` | 交 D | T1 | 通用报告/矩阵归一化，复用 evaluation/cj028；C 门槛和硬失败继续约束输出。 |
| `eval/rerun_report.py` | C 保留 | C | 真实复跑的原件封存、六格与正式阶段分开汇总。 |
| `eval/run.py` | 交 D | T2 | Fake-only 离线完整场景执行器，消费 C 冻结场景和判据。 |
| `eval/runtime.py` | 交 D | T2 | 新私有 PG、签名 API 与原 worker 的本地组合支持；C 实验也导入。 |
| `eval/scenarios.json` | C 保留 | C | 冻结 33 对、11 对留出、共 66 条，SHA-256 见下文。 |
| `eval/smoke.py` | C 保留 | C | 六格原题与实际工具续接门禁；按现役 Lio 支持交接开新阶段。 |
| `eval/smoke_correction.json` | C 保留 | C | 已批准的一次性历史误判修正的固定策略和摘要。 |
| `eval/smoke_correction.py` | C 保留 | C | 按上述特定策略补齐原阶段；保留原 FAIL 和原认领。 |
| `eval/worker_probe.py` | 交 D | T2 | Fake-only 新进程观测，供离线重启场景使用。 |

## 回归测试

测试随其实际判据分配。C 保留的门槛和安全断言可以消费 D 模块，未来 D 的实现 PR 仍需联验这些调用方。现有默认测试发现与漏登记问题归 #785 的获派 owner。 [#785](https://github.com/JTCAO515/G2C/issues/785)

| 测试 | 目标归属 | 条件 | 对应模块/交接检查 |
|---|---|---|---|
| `eval/tests/test_demo_v2_evidence.py` | C 保留 | C | demo_v2_evidence.py |
| `eval/tests/test_demo_v2_report.py` | C 保留 | C | demo_v2_report.py |
| `eval/tests/test_demo_v2_transport.py` | C 保留 | C | demo_v2_transport.py 的原件/续接负例 |
| `eval/tests/test_fees.py` | C 保留 | C | fees.py 的回执与估算 |
| `eval/tests/test_gates.py` | C 保留 | C | gates.py 及 report.py 的原门槛断言 |
| `eval/tests/test_hk.py` | C 保留 | C | hk.py 的实际入口和原账约束 |
| `eval/tests/test_judge.py` | C 保留 | C | judge.py 的硬约束和状态断言 |
| `eval/tests/test_network_policy.py` | C 保留 | C | 目标网及质量策略，虽消费 report.py，门槛归 C |
| `eval/tests/test_network_read.py` | C 保留 | C | 原 RUN 的只读网络诊断 |
| `eval/tests/test_phase_identity.py` | C 保留 | C | real_phase.py 的原生产 adapter 与认领 |
| `eval/tests/test_progress.py` | 交 D | T1 | progress.py，联验 test_report/test_smoke 和 C 费用判据 |
| `eval/tests/test_real.py` | C 保留 | C | 真实执行、预算和原报告证据 |
| `eval/tests/test_report.py` | 交 D | T1 | report.py，联验 C 的 gates/judge 和网络策略断言 |
| `eval/tests/test_smoke.py` | C 保留 | C | 六格和原工具续接门禁 |
| `eval/tests/test_smoke_correction.py` | C 保留 | C | 特定历史修正封存与负例 |

## D 已接模块

| 模块/数据范围 | 目标归属 | 条件 | 责任与消费方 |
|---|---|---|---|
| `eval/optimization/**` | D 已接 | D 已接 | 8 个文件，含评分器、CLI、公开案例/样例、测试与 README/REPORT。D 维护 `G2C-dialogue-score.1` 和 `G2C-dialogue-cases.1`；当前 `score.py` 导入 C 的 `eval.judge`。E #763 固定接口、数据与代码摘要，B #762 提供可信原观测，R 校准并审查。 |

## 已封存报告与数据

下面 73 个文件均由 C 保留，沿批次追加证据和引用，原文件保持原判定和摘要。D 的比较报告应另立候选/任务证据并回链真实质量票。

| 报告批次/文件范围 | 目标归属 | 文件数 | 条件 |
|---|---|---:|---|
| `eval/reports/demo-685-20261109.md` | C 保留 | 1 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/network-mac-vpn-read-001/**` | C 保留 | 3 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/network-mac-vpn-read-002/**` | C 保留 | 3 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-001/**` | C 保留 | 2 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-after-envelope-337/**` | C 保留 | 8 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-after-gzip/**` | C 保留 | 6 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-after-schema/**` | C 保留 | 6 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-after-strict/**` | C 保留 | 8 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-after547/**` | C 保留 | 2 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-body-prefix-correction/**` | C 保留 | 9 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-formal66-followup/**` | C 保留 | 3 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-formal66-v2/**` | C 保留 | 12 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-hk936/**` | C 保留 | 6 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-round2/**` | C 保留 | 2 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |
| `eval/reports/real-m4-round2-after544/**` | C 保留 | 2 | C，保留原 `FAIL/UNKNOWN/INTENT` 和样本身份 |

## 在途与本次排除范围

2026-11-11 08:34 CST 的实时 OPEN PR 盘点仅有下列两张，均不占本清单文件。写入前仍需重新核实时 PR 逐文件清单；本表只证明上述快照的状态。

| PR/任务 | 已核 head/状态 | 现有范围与本次边界 |
|---|---|---|
| [PR706](https://github.com/JTCAO515/G2C/pull/706) | OPEN，`24738b62ea5748d2a5dd86f53bb29b2f788a0b41` | Claude 的 `docs/scope.md`，原法律意见来源和首测范围由其原票处理。 |
| [PR552](https://github.com/JTCAO515/G2C/pull/552) | OPEN，`ff2be6a1f763a6986cf3a3d0aacac3a340a431f5` | iOS Memory 临时条目清理及原测试，由原 owner 处理。 |
| [#785 G](https://github.com/JTCAO515/G2C/issues/785) | 已派工，盘点时无 OPEN PR | 离线套件入口包括 `tooling/datasets`、`tooling/optimization`、`tooling/training` 与 `eval/optimization/test_score.py`。`scripts/test.py` 共享锁和 CI 红线沿原门禁；D 的目录归属与 G 的获派修改分开记录。 |
| [#32 B/C](https://github.com/JTCAO515/G2C/issues/32#issuecomment-6774244518) | 等 B 原件读取方式及独占时段 | C 的真实执行、证据采集与正式判定持续归 C。D/E 实验等待对应输入和调度。 |

已合并的 PR774、PR782、PR783、PR786 作为接口基线保留。F 的 `tooling/datasets/**`、E 的 `tooling/optimization/**`、G 的 `tooling/training/**`、B 的消息/运行/NEEDS/用量/工具与部署接口，以及 C 的草稿/Trip/记忆后端按其原票拥有，不随这份 eval 清单转移。 [#761](https://github.com/JTCAO515/G2C/issues/761) · [#768](https://github.com/JTCAO515/G2C/issues/768) · [#763](https://github.com/JTCAO515/G2C/issues/763) · [#773](https://github.com/JTCAO515/G2C/issues/773)

冻结 `eval/scenarios.json` 的 SHA-256 为 `2a5df582ee63f461afebe7a280cc5587e6281190f6aab05b458fa89f029d2e56`，仍是 C 的原 33 对/66 例及 11 对公开历史留出。D/R 新最终题按 JT 决定在仓库外加密，密钥由 JT 持有，执行比较时仅交 R；文档、Git 与 CI 制品只留允许的摘要、分母和用途。两套样本分别保管。 [JT 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6783256928)

后续预算口径修订、工具投影前原件支持、会话续期、#762 接线、优化实验、评分版本和数据内容变更、最终题加密/拒读实测、测试发现与 CI 登记分别沿原票执行。本清单不承接这些实施变更。

## 给 Claude 的落表输入

1. 按根模块、测试和批次范围写入目标 owner。T1/T2 未满足时保留 C 当前写入者，`eval/optimization/**` 维持 D。
2. 在对应 D 接入票记录原 head、接口和数据版本、C 调用方回归、当前 C 批次/文件锁与 D 接收回执，再把 owner 生效时间回贴 #760。
3. 香港窗口由 B 按 A（JT 真机）→ C（#32）→ D/E（#764）排期。真实出口、费用、签名身份和旧原件的恢复沿 #32/#495 及 B 的原交接。
4. 本 PR 完成 C→D 清单输入。#760 其余任务映射、每票角色和资源恢复、整体验收由 Claude 按本轮 Goal 更新 issue-plan。
