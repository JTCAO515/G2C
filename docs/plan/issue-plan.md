# Issue 总体规划

依据 [ADR-0007](../adr/0007-issue-closure-workflow.md)。本文件只记录**结构**：里程碑、队列、子票和依赖。**进度**以 GitHub Issue 为准，不在这里勾选。最近一次修订：2026-10-28（Claude 排期，JT 授权插入 #176、#182、#185）。

## 规划原则

1. **保留原票，不重写。** 35 张原票（CJ-001～CJ-035）作为父票保留原文，作为总验收。每张父票顶部有“ADR-0007 规划”块，写明里程碑、队列位置、子票和 L2/L3 转记。
2. **按里程碑纵向推进。** 一个里程碑走完一条可演示的链路，而不是按领域横向铺开。
3. **滚动细化。** 只有当前里程碑拆成了子票。下一个里程碑在当前里程碑接近完成时再拆，避免子票提前过期。
4. **证据分级。** 功能票在 L0/L1 关闭；L2（真实服务）框转记 [#32](https://github.com/JTCAO515/G2C/issues/32)，L3（真机与内测）框转记 [#29](https://github.com/JTCAO515/G2C/issues/29)。父票验收框末尾的 `→ #N` 或 `→ L2 #32` 标明了每个框由谁承接。
5. **“I 前置”只约束 L2/L3。** 上游票是否完成，只影响集中验证；功能票达到 L1 即可关闭。

## 里程碑

| 里程碑 | 目标 | 父票 |
|---|---|---|
| M0 范围与关键技术验证 | 收尾：S1 盘点时核验并关闭 | [#2](https://github.com/JTCAO515/G2C/issues/2) CJ-002、[#4](https://github.com/JTCAO515/G2C/issues/4) CJ-004；[#6](https://github.com/JTCAO515/G2C/issues/6) CJ-030（JT 决策） |
| **M1 主链路闭环（模拟器 L1）** | 账号 → 聊天 → 流式回答 → 草稿 → 确认 → 正式行程，在 iOS 17.5 模拟器上以本地真实组合跑通 | #20、#5、#7、#8、#10、#11、#19；流程票 [#151](https://github.com/JTCAO515/G2C/issues/151) |
| M2 记忆与行程能力 | 长记忆、需求、地点/天气、可行性、行程页与编辑 | #9、#12、#17、#14、#13、#16、#18、#21、#22、#25 |
| M3 数据生命周期与反馈 | 记忆沉淀与删除、离线行程、问题反馈、注销与清理 | #23、#26、#24、#15、#27 |
| M4 真实环境与受邀内测 | 集中承接 L2/L3：真实服务、真机、环境重建、效果与成本、内测 | #28、#29、#30、#32、#33 |
| M5 公开首发准备 | 商店资料、隐私、发布候选确认 | #34、#35；#31（仅在决定收费时启用） |

## M1 队列

剩余子票按下面“并行线”分三条线同时推进（2026-10-28 JT 批准）；每条线内按顺序执行。当前插入段的唯一顺序为 **#161 → #176 → #182 → #185 → #163**，之后继续原队列至 #170（JT 2026-10-28 授权）。#176 的方案以[收紧后的验收评论](https://github.com/JTCAO515/G2C/issues/176#issuecomment-6460752372)为准；票面早期“不进入 M1”是历史记录。

| 序 | 父票 | 子票（按顺序） | 转 L2 #32 的框 |
|---|---|---|---|
| 0 | [#151](https://github.com/JTCAO515/G2C/issues/151) S0 关票流程 | Part 2/2：iOS 测试全部进 CI、pr-lint（在 #154 之后、#155 之前做） | — |
| 1 | [#20](https://github.com/JTCAO515/G2C/issues/20) CJ-015 确认草稿保存正式行程 | [#154](https://github.com/JTCAO515/G2C/issues/154) DEBUG 会话与模拟器确认端到端（已关闭，PR #172）→ [#155](https://github.com/JTCAO515/G2C/issues/155) 服务端幂等/冲突/并发/原子性负例 | 无 |
| 2 | [#5](https://github.com/JTCAO515/G2C/issues/5) CJ-005 工程基线 | [#156](https://github.com/JTCAO515/G2C/issues/156) 工程基线核验 | 框 2 |
| 3 | [#7](https://github.com/JTCAO515/G2C/issues/7) CJ-006 四 Tab 外壳 | [#157](https://github.com/JTCAO515/G2C/issues/157) 结构与语言 → [#158](https://github.com/JTCAO515/G2C/issues/158) 无障碍与状态样例 → [#194](https://github.com/JTCAO515/G2C/issues/194) 插件 Tab 滴滴占位（文案需 JT）→ [#159](https://github.com/JTCAO515/G2C/issues/159) 帮助/隐私/支持（文案需 JT） | 无 |
| 4 | [#8](https://github.com/JTCAO515/G2C/issues/8) CJ-007 账号与隔离 | [#160](https://github.com/JTCAO515/G2C/issues/160) API/DB 隔离与资格门禁 → [#161](https://github.com/JTCAO515/G2C/issues/161) App 开发身份登录与切换 | 框 6、8（真实 OTP 与 SDK 行为） |
| 4.1 | M1 插入修复（关联 CJ-035 / #18，不提前启动 M2 整票） | [#176](https://github.com/JTCAO515/G2C/issues/176) 求解器冷启动测量、进程预载与预算回归（#161 之后） | 无 |
| 4.2 | [#8](https://github.com/JTCAO515/G2C/issues/8) CJ-007 账号与隔离（续） | [#182](https://github.com/JTCAO515/G2C/issues/182) 事务级 scope、物理连接复用拒绝与 pooler 激活门禁（#176 之后） | 云端 pooler 实测留 C2，需 JT 资源授权 |
| 4.3 | M1 基线规则补充（关联已关闭 #5，不重开整票） | [#185](https://github.com/JTCAO515/G2C/issues/185) 信任边界规则及三个限定例子的内部防御清理（#182 之后） | 无 |
| 5 | [#10](https://github.com/JTCAO515/G2C/issues/10) CJ-009 聊天与消息 | [#162](https://github.com/JTCAO515/G2C/issues/162) 发送许可方案（**Claude**）→ [#163](https://github.com/JTCAO515/G2C/issues/163) 服务端实现 → [#198](https://github.com/JTCAO515/G2C/issues/198) 本地入口接历史配置 → [#164](https://github.com/JTCAO515/G2C/issues/164) App 发送与历史 | 无 |
| 6 | [#11](https://github.com/JTCAO515/G2C/issues/11) CJ-010 流式与停止 | [#165](https://github.com/JTCAO515/G2C/issues/165) 停止生成接口 → [#166](https://github.com/JTCAO515/G2C/issues/166) 顺序/互斥/恢复 → [#167](https://github.com/JTCAO515/G2C/issues/167) App 流式与停止按钮 | 无（框 1 真实模型部分在子票内注明 → L2） |
| 7 | [#19](https://github.com/JTCAO515/G2C/issues/19) CJ-014 草稿 | [#168](https://github.com/JTCAO515/G2C/issues/168) 约束校验 → [#169](https://github.com/JTCAO515/G2C/issues/169) 来源标注 → [#170](https://github.com/JTCAO515/G2C/issues/170) 失败路径与过期 fence | 框 1（真实工具与模型） |

### 依赖与并行

- **#162 由 Claude 负责**，可以和 Codex 的队列并行进行。Codex 不认领它；轮到 #163 时如果 #162 还没关闭，跳到 #165 继续。
- 完整依赖以各子票正文的“前置子票”行为准；下面列出会导致跳过的几条。
- #176 排在 #161 完成后；#182 依赖 #160，并在 #176 完成后执行。
- #185 在 #182 完成后执行，先写规则，再处理三个限定例子；保留全部边界/安全检查，不作全仓库清理。
- #163 依赖 #162、#182 和 #185；#164 依赖 #163。恢复 #163 时基于最新 main 重放其本地候选并遵循新规则，新迁移按最新 manifest 顺延到已应用 0011 之后，不覆盖 1–11。
- 父票 #8 包含 #160、#161、#182；#161 完成后仍须等待 #182。其余未完成子票等待 #176 时，#8 按既有规则挂起，不占在制名额。
- #159 依赖 #157；#169 依赖 #168。#194（滴滴打车占位，JT 2026-10-28 授权）与 #159 都要等 JT 确认最终中英文案后再做。
- #161 依赖 #157（账号入口在记忆页）和 #160。
- #164 依赖 #198（本地正式入口接历史/游标配置，JT 2026-10-29 授权）。
- #167 依赖 #164（App 能发消息）和 #165（停止接口）。
- #170 依赖 #168 和 #165。
- **跨票转移：** #11 框 7 和 #19 框 6 中“记忆版本”的部分，转入 M2 的 [#17](https://github.com/JTCAO515/G2C/issues/17) CJ-019。M2 拆票时要把它补成 #17 的验收框。
- **跨票转移：** 按 [JT 对 #168 的决定](https://github.com/JTCAO515/G2C/issues/168#issuecomment-6485249974)，#19 框 2 的“结构化日程时间 × NEEDS/FEAS 冲突校验”转入 M2 [#204](https://github.com/JTCAO515/G2C/issues/204)，挂在 #21 每日时间线之前或之内；依赖 TRIP 结构化行程契约新版本，复用 FEAS `ITEM_TIME_*` 与现有重叠检查，不另写约束引擎。M1 #168 整份拒绝对象条目或结构化时间字段；文本时间仅为 `pending`、`evidence=[]` 的描述，服务端不做时间校验或已校验声明。用户可见的草稿校验失败状态由 B 线 #170 承接。

本次插入段冻结求解预算数值、TIMEOUT/UNKNOWN 与既有断言，以及 RLS 隔离语义、运行角色权限上限、已应用迁移 1–11、契约和 CI 门禁。#176 先记录冷/热分阶段耗时，采用启动预载且失败即退出，最后在新 checkout 连续三次完整 PG 11/11；#182 必须覆盖 12 张 M1 表的同物理连接复用 SELECT/UPDATE/INSERT 负例并保留 #181 e2e。若修复需改变这些边界、碰云资源或真实账号，停止并在票中说明，等待 JT 决定。#159 文案、L2 授权、分支保护和生产 key 仍由 JT 决定。

### 并行线（2026-10-28 起，2026-10-29 按实况修订）

每条线一个 Codex 会话、同一时间 1 张父票、最多 1 个开着的 PR（ADR-0007 第 2 条）。线内依赖未满足时按子票级停点跳过或等待，不去碰别的线拥有的文件。已完成：#165、#166（原 B 线）、#168 Part1（PR #201）。

| 线 | 队列 | 本线拥有的文件 | 跨线依赖 |
|---|---|---|---|
| A App | #164 → #167 → #194 → #159（#194、#159 等 JT 确认文案后才做；未确认就跳过） | `ios/Modules/CJMessageClient/**`、`ios/Modules/CJRunClient/**`、`ios/Modules/CJShell/**`、`ios/App/**`、`ios/Modules/CJUsageClient` 测试夹具、`docs/ui.md` | #164 等 B 线 #198 合并；#170 若需要 App 端失败呈现，由 B 线拆子票交本线 |
| B 后端消息与运行 | #198 → #170 → 按“M2 拆分预案”拆 #9 并开始第一张子票 | `backend/run/**`、`backend/message/**`、`backend/needs/**`、`backend/usage/**`、`backend/cj_api/**`、`scripts/dev_auth.py`、`backend/agent/cj_agent/worker.py`、`backend/agent/cj_agent/provider.py` | #170 等 C 线 #168 关闭 |
| C 草稿 | #168 收尾（Part2）→ #169 → 按“M2 拆分预案”拆 #12 并开始第一张子票 | `backend/draft/**`、`backend/feasibility/**`、`backend/agent/cj_agent/draft.py`、`backend/memory/**`、`ios/Modules/CJTripClient/**`、`ios/Modules/CJMemoryClient/**` | #169 若要改 `worker.py` 等 B 线文件，先确认 B 线没有开着的 PR 改同一文件，否则等待 |

M2 拆票提前到各线 M1 队列做完时进行（不再等“M1 剩最后两张父票”），两条线的拆票都要改 `docs/plan/**`，按共享文件规则排队。
共享文件（唯一权威清单，ADR-0007 第 2 条引用此处）同一时间只允许一个开着的 PR 修改：`contracts/**` 与生成代码（#169 会改 `openapi.json`）、`backend/migrations/**`、`scripts/test.py`、`scripts/pg_suites.py`、`docs/plan/**`、`docs/handoff.json` 与生成的 `HANDOFF.md`、`backend/agent/tests/e2e_local.py`。

### 停点与跳过

停点分两级（ADR-0007 第 7 条）：

- **子票级**，跳过这张子票，继续队列：
  - 需要 JT 的文案或产品决策（例如 #159）；
  - owner 为 Claude 且未关闭（#162）；
  - 前置子票未关闭（例如 #162 未关时的 #163、#164，#164 未关时的 #167）；
  - 同一张子票连续 3 轮审查未通过；
  - 需要改别的线拥有的文件，或共享文件正被别的线的 PR 占用（等待或先做别的部分）。
- **仓库级**，停止整个会话：ADR-0007 第 3 条停点清单各项；main 变红且修复与 revert 都无法恢复；需要修改本文件的里程碑或队列结构。

跳过的做法：

1. 在子票评论阻塞原因、需要谁做什么，并写进 handoff 的 `blockers`。
2. 跳过子票所属的父票，如果剩余子票全部被卡住，就算“挂起”，不占在制名额，队列转到下一张父票。
3. 每次开新子票之前，先检查之前跳过的子票是否已经解除；解除的优先做。
4. 父票等全部子票关闭后再关闭。

## M2 拆分预案

M1 剩最后两张父票时，按下面的顺序把 M2 拆成子票。这里只是预案，开工时以代码实况为准。

| 序 | 父票 | 预计子票 |
|---|---|---|
| 1 | #9 CJ-008 用量与运行上限 | 统一计量出口与超限拒绝；并发/重复尝试不绕过限制；App 超限提示 |
| 2 | #12 CJ-011 结构化长记忆 | 保存与读取；跨会话即时使用；App 记忆页 |
| 3 | #17 CJ-019 记忆编辑与启停 | 编辑/启停；旧结果不覆盖（含从 #11、#19 转入的记忆版本 fence） |
| 4 | #14 CJ-013 需求整理与纠正 | 需求修订与固定事项；App 纠正入口 |
| 5 | #13 CJ-012、#16 CJ-034 | 地点/路线与天气/时效：L1 用录制数据，真实接口 → L2 |
| 6 | #18 CJ-035 可行性 | 约束求解有界执行；与草稿校验对接 |
| 7 | #21 CJ-016 行程页 | 每日时间线、地图与地点信息 |
| 8 | #22 CJ-017、#25 CJ-018 | 手动编辑与固定事项保护；助手只改选定行程并说明影响 |

## 修订规则

- 新增或调整子票：直接在 GitHub 上改，并同步本文件的 M1 队列表。
- 里程碑重排、父票合并或拆分、L2/L3 转记规则变化：由 Claude 修订本文件，JT 批准。
