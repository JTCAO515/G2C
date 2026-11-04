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
| M0 范围与关键技术验证 | 2026-11-04 关闭；剩余真实调用与真机部分随 #2、#4、#6 移入 M4 | — |
| **M1 主链路闭环（模拟器 L1）** | 账号 → 聊天 → 流式回答 → 草稿 → 确认 → 正式行程，在 iOS 17.5 模拟器上以本地真实组合跑通 | #20、#5、#7、#8、#10、#11、#19；流程票 [#151](https://github.com/JTCAO515/G2C/issues/151) |
| M2 记忆与行程能力 | 长记忆、需求、地点/天气、可行性、行程页与编辑 | #9、#12、#17、#14、#13、#16、#18、#21、#22、#25 |
| M3 数据生命周期与反馈 | 记忆沉淀与删除、离线行程、问题反馈、注销与清理（2026-11-04 关闭，26 张票） | #23、#26、#24、#15、#27 |
| M4 真实环境与受邀内测 | 集中承接 L2/L3：真实服务、真机、环境重建、效果与成本、内测；高德地图接入 | #495（JT 决策）、#2、#4、#6、#225、#28、#29、#30、#32、#33、#398 |
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
- #170 的 App 草稿结果呈现由 A 线 [#212](https://github.com/JTCAO515/G2C/issues/212) 承接（父票 #19），依赖 #164 和 B 线版本化草稿结果切片；后端与原生证据分别回写。
- **跨票转移：** #11 框 7 和 #19 框 6 中“记忆版本”的部分，转入 M2 的 [#17](https://github.com/JTCAO515/G2C/issues/17) CJ-019 的明确 fence 验收框；[#227](https://github.com/JTCAO515/G2C/issues/227) 复用其版本/撤回语义做消费验收，不另写约束引擎，也不以调用方 Context、版本或 hash 相等充当发布许可。
- **跨票转移：** 按 [JT 对 #168 的决定](https://github.com/JTCAO515/G2C/issues/168#issuecomment-6485249974)，#19 框 2 的“结构化日程时间 × NEEDS/FEAS 冲突校验”转入 M2 [#204](https://github.com/JTCAO515/G2C/issues/204)，挂在 #21 每日时间线之前或之内；依赖 TRIP 结构化行程契约新版本，复用 FEAS `ITEM_TIME_*` 与现有重叠检查，不另写约束引擎。M1 #168 整份拒绝对象条目或结构化时间字段；文本时间仅为 `pending`、`evidence=[]` 的描述，服务端不做时间校验或已校验声明。用户可见的草稿校验失败状态由 B 线 #170 承接。

本次插入段冻结求解预算数值、TIMEOUT/UNKNOWN 与既有断言，以及 RLS 隔离语义、运行角色权限上限、已应用迁移 1–11、契约和 CI 门禁。#176 先记录冷/热分阶段耗时，采用启动预载且失败即退出，最后在新 checkout 连续三次完整 PG 11/11；#182 必须覆盖 12 张 M1 表的同物理连接复用 SELECT/UPDATE/INSERT 负例并保留 #181 e2e。若修复需改变这些边界、碰云资源或真实账号，停止并在票中说明，等待 JT 决定。#159 文案、L2 授权、分支保护和生产 key 仍由 JT 决定。

### 并行线（2026-10-28 起；M2 修订：JT 批准，2026-10-30）

每条线一个 Codex 会话、同一时间 1 张父票、最多 1 个开着的 PR（ADR-0007 第 2 条）。线内依赖未满足时按子票级停点跳过或等待。M1 已交付记录保留在 Issue 与本线 handoff；#194、#159 仍等 JT 确认文案。

| 线 | 队列 | 本线拥有的文件 | 跨线依赖 |
|---|---|---|---|
| A App | M2全部L0/L1已收口，#21/PR387、#332/PR392 CLOSED；milestone3 CLOSED（47 closed/0 open）；#194/#159跳过 | 整个 `ios/**`、`docs/ui.md`；唯一A，不恢复OldA | 本轮最终一次handoff；MapKit无Key/费用/第三方依赖，实际物理点位→#32/#29 UNRUN、不计PASS；#398高德替换/企业许可/iOS平台Key及SDK隐私停点属M3，JT另开新线程。B/C本轮交付从#21通知6567906580取，不依旧快照重开队列。 |
| B 后端消息与运行 | 本轮[#354](https://github.com/JTCAO515/G2C/issues/354)/[#360](https://github.com/JTCAO515/G2C/issues/360)/[#378](https://github.com/JTCAO515/G2C/issues/378)均CLOSED（PR359/379/380/382）；goal结束仅B交接，C实际B接口缺口优先响应360/343；315按JT保持OPEN不投入 | `backend/run/**`、`backend/message/**`、`backend/needs/**`、`backend/usage/**`、`backend/cj_api/**`、`backend/place/**`、`backend/fact/**`、`scripts/dev_auth.py`；下列 B 线协调文件 | source1 needs-structured.1与source2 needs-current-trip.1独立正式入口；publisher@2/M29同cursor结果与新读版本供C336/A337。C381/M30生产交付由C负责，A App/真实资源按各owner验，不由B probe/后端验收代称全M2完成；业务锁已释放 |
| C M2后端记忆、草稿与可行性 | M2本线已派后端均交：366/374/336及25后端完成；保持原M2 goal，继续处理真实C-owner联调缺口，当前唯一剩余21地图按JT暂缓UNRUN | backend/trip/**、backend/draft/**、backend/feasibility/**、backend/agent/cj_agent/draft.py、backend/memory/**、backend/memory_management/**、backend/memory_jobs/**、backend/memory_withdrawal/**、backend/manual_edit/**；只做后端 | B354/360/378及A337/373/286/22/25均已交闭；C381同RUN cursor结果/受保护读取与M30已合并。实时M2仅21地图综合余项，JT决定授权调整、A实施；无独立C项时保留实际停点，不重复测试/handoff或求同一地图授权，不将M2标complete。 |

- 未列出的目录由 JT 指定归属；本线只改拥有且获准的文件。A 同时只推进一张父票（#244 属 #9，#228 属 #12）；当前票剩余框全部被前置卡住时，先记停点再换另一张。
- **共享文件按文件加锁**：每个共享文件同一时间只能有一个开着的 PR 修改，不同共享文件可以同时被不同 PR 修改。`contracts/**` 与生成代码算一组；`docs/handoff.json` 与生成的 `HANDOFF.md` 算一组，组内共用锁。
- 共享文件唯一权威清单（ADR-0007 第 2 条引用此处）：`contracts/**` 与生成代码、`backend/migrations/**`、`scripts/test.py`、`scripts/pg_suites.py`、`docs/plan/**`、`docs/handoff.json` 与生成的 `HANDOFF.md`、`backend/agent/tests/e2e_local.py`。除上述两组外按具体文件加锁，目录模式不构成整目录锁。
- **B 线协调文件**：`backend/agent/cj_agent/worker.py`、`backend/agent/cj_agent/provider.py`、`backend/cj_api/local_app.py`、`scripts/run_worker.py`。其他线确需修改时，先确认没有开着的 PR 修改同一文件，并在本线票和 B 线当前票上声明改动范围；占用规则同共享文件，按文件加锁。声明不替代本轮具体写入授权。
- 开 PR 前运行 `gh pr list`，对每个开着的 PR 运行 `gh pr diff --name-only`，逐文件核对占用；被占用就等待或先做不触碰该文件的部分。M2 拆子票同步 `docs/plan/**` 时同样适用。

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

按上面的并行线规则，各线 M1 队列完成后滚动拆分 M2；已有子票按顺序执行，其余仍为预案，开工时以代码实况为准。

| 序 | 父票 | 预计子票 |
|---|---|---|
| 1 | #9 CJ-008 用量与运行上限 | [#242](https://github.com/JTCAO515/G2C/issues/242) 统一计量出口与超限拒绝 → [#243](https://github.com/JTCAO515/G2C/issues/243) 并发/重复与工具后台限额；[#244](https://github.com/JTCAO515/G2C/issues/244) App超限/未知用量/原结果恢复（A线，依赖#242，复用#167） |
| 2 | #12 CJ-011 结构化长记忆 | [#226](https://github.com/JTCAO515/G2C/issues/226) 保存/受保护读取；B [#273](https://github.com/JTCAO515/G2C/issues/273) 旅行上下文身份、MESSAGE新引用/lease供 C [#227](https://github.com/JTCAO515/G2C/issues/227) 框2和 A [#228](https://github.com/JTCAO515/G2C/issues/228) 框4消费；#228框1–3可先于#227。新增版本/追加本地迁移与最小列权限按JT常设授权，敏感资源例外交JT；B桥接票不代闭#227/#228或父#12 |
| 3 | #17 CJ-019 记忆编辑与启停 | [#269](https://github.com/JTCAO515/G2C/issues/269) 后端编辑/逐条启停 → [#270](https://github.com/JTCAO515/G2C/issues/270) 旧结果覆盖与版本/撤回fence；[#271](https://github.com/JTCAO515/G2C/issues/271) App编辑/启停交A。#270回补#227框4；新增版本、追加本地迁移/最小列权限按JT2026-10-30常设授权执行，仅既有门禁/冻结版本/外部资源等例外停JT |
| 4 | #14 CJ-013 需求整理与纠正 | [#303](https://github.com/JTCAO515/G2C/issues/303) 正式契约先于#16；[#305](https://github.com/JTCAO515/G2C/issues/305) B本地提取预览/显式纠正/版本持久与当前性；[#320](https://github.com/JTCAO515/G2C/issues/320) A原生查看/纠正与原动作恢复，排期由A/JT决定 |
| 5 | #13 CJ-012、#16 CJ-034 | #13子票[#263](https://github.com/JTCAO515/G2C/issues/263) PLACE合同、[#264](https://github.com/JTCAO515/G2C/issues/264) 解析/来源、[#265](https://github.com/JTCAO515/G2C/issues/265) 正式工具；A[#266](https://github.com/JTCAO515/G2C/issues/266) App引用。#16 B[#306](https://github.com/JTCAO515/G2C/issues/306) 合成FACT正式工具、A[#321](https://github.com/JTCAO515/G2C/issues/321) App来源/时效。真实接口与采集→L2 #32须资源授权，合成不称录制；按JT顺序在#303之后、#305之前实施#306 |
| 6 | #18 CJ-035 可行性 | [#280](https://github.com/JTCAO515/G2C/issues/280) FEASIBILITY@1.0核心/有界求解复用；[#281](https://github.com/JTCAO515/G2C/issues/281) B正式PLACE/NEEDS producer与来源/当前性组合。原六框保留，未冻结字段只阻相应子票，不以candidate冒称正式合同 |
| 7 | #21 CJ-016 行程页 | 每日时间线、地图与地点信息 |
| 8 | #22 CJ-017、#25 CJ-018 | #22拆[#285](https://github.com/JTCAO515/G2C/issues/285) C后端正式手动保存/固定状态/共享可行性保护、[#286](https://github.com/JTCAO515/G2C/issues/286) A App编辑/diff/确认与恢复；原五框保留。Trip typed/time/lock与受保护manual ingress由C负责；NEEDS未冻结仅阻相应来源/发布组合。#204由C在draft/feasibility/trip接共享校验；C优先补充子票[#361](https://github.com/JTCAO515/G2C/issues/361)已由PR362关闭：受保护legacy同Trip来源绑定初始化，旧INITIALIZE拒绝保留，App消费归A；#25后续助手限定修改单独执行 |

#9 父票六框映射：框1/5由#242承接；框2/6由#243承接；框3的入口注册/拒绝由#242、实际工具循环由#243承接；后台部分经JT 2026-10-31批准转M3 #23，仍UNRUN；框4及App日志/缓存由#244承接。真实身份、模型/工具费用、真实结算与晚到回执登记L2 #32，设备部分按适用范围留L3 #29；本地合成回调不替代实际生产者。三张票已建立原生sub-issue，#243/#244原生依赖#242。新契约、迁移语义、别线写权和外部资源仍适用既有停点，拆票本身不授予这些权限。 2026-10-31核实#242/#243/#244均关闭，M2父#9六框已按L1/转记回填关闭；不表示后台、真实费用或全M2/发布通过。

### C线 #227 分段与 #17 拆分（JT 2026-10-30）

- #227第一部分只交lease/capture/实际worker与证据完整的框1/3；框2“另一旅行”与框4完整生命周期组合仍保留，不以跨conversation或过滤fixture替代。#227不因Part1关闭。
- #227框2等待B提供并冻结旅行上下文身份/MESSAGE/lease（JT已插入B的#13之前，具体子票/版本以B本线交付为准）；typed迁移具体DDL须再批。框4依赖#269/#270正式生产者，后者完成后回补。
- #12对C线剩余工作全部被前置卡住时挂起，不占本线父票名额，转#17；不要求整张#227或#12关闭后才起工#269。C只推进后端两票，#271由A按其本线排期认领，C不改ios或A既有队列。
- #269负责新编辑来源/历史、逐条启停、item/source CAS及原动作回执；#270负责复用同一scope epoch/条目/来源当前性，拒绝旧回答/草稿/整理结果，并承接#11/#19转入的Memory fence。候选撤回read model不冒充权威writer，未就绪部分登记子票停点。
- #17七框映射：框1由#269/#271、框2由#269/#270、框3由#270、框4由#269（原CJ018/CJ025组合边界保留）、框5由#270、框6由#269/#270/#271、框7由#270并回补#227。全部对应L0/L1子票完成后才关#17；真实后台生产者/App/外部服务证据各归其owner。
- 新编辑协议/来源历史、运行角色权限和正式管理API启用先提交[设计](../../backend/memory_management/EDIT-ENABLE-DESIGN.md)等JT批准；不改冻结pause/resume wire，不执行未批准的新迁移，不借本线目录写权绕过B/共享文件规则。

## 修订规则

- 新增或调整子票：直接在 GitHub 上改，并同步本文件的 M1 队列表。
- 里程碑重排、父票合并或拆分、L2/L3 转记规则变化：由 Claude 修订本文件，JT 批准。

### B线旅行上下文插队（JT 2026-10-30）

- [历史2026-10-30，见下方2026-10-31更新] #243框3的实际工具/后台生产者依赖保持在#13/#16/#23对应功能票，不制造回调验收；按子票级停点挂起后先取#273。这里只记录依赖/队列结构，进度以Issue为准。
- #273归B且挂父#12，先与C的3b1c0df typed设计对齐身份、MESSAGE新引用、lease/键和锁序。方向及新增版本/追加本地迁移/最小列权限按JT2026-10-30常设授权；具体设计和证据记对应Issue，敏感资源例外仍停JT。
- #273不修改MESSAGE-send.1、MEMORY旧语义、已应用迁移或C/ios文件；交付后在#227/#228通知真实冻结版本/键及head。随后回#13→#303（NEEDS契约先行）→#306（#16合成）→#305（#14后端）；App与后台生产者按各自owner子票验收，不代闭父票。

### B线本轮交付及M3归位（JT 2026-10-31）

- #330已由PR342锁head85acf4ec合并e88f9a5a，精确CI41166636674全绿并完成独立红线审查/逐字一致main整合复用；send.3/trip-reference.1及原结果版本供A #21/#25消费，旧send.1/send.2/已应用迁移未改。仅讨论型profile：升级scope拒新send.2，既有MEMORY无适配拒升级；不把travel_context冒充Trip，不以该协议授予#25写入/确认权。
- #315本轮调查与安全诊断随342交付；100次实际Unicode CLI未复现，原历史FAIL/实际失败计数/rootUNKNOWN保留，315保持OPEN。89个原断言条件不变；受控报告1→0仅验证诊断，不当产品复现或已修复。
- JT已批准把#243框3后台部分完整转记M3 #23并保留UNRUN；PLACE/FACT工具证据保留，#243和#9已关闭。真实结算/外部服务/费用仍→L2 #32，设备适用部分→L3 #29；不制造后台验收或新增B自主队列。

### B线 #343追加producer交付（JT本轮新goal，2026-10-31）

- 旧交接“不再开业务PR/无JT指令不接队列”不适用于本轮明确指派343。336/337/343/344已补入M2，均为25子票。343四框经契约PR349/e107eda/96808a4b和运行PR350/74fa0bc2/1e3af625完成，精确CI/独立红线通过，每次合并均已通知四个消费票，不等回执/main CI。
- 新修改意图、Trip/version/hash/day或item、实际独立travel namespace/NEEDS与原message/run关联；Memory/publisher显式新ABI/实际依赖。publication按RUN→M→TRAVEL→MEMORY/NEEDS→Trip UPDATE，用同cursor写C唯一Proposal与RUNeffect，不另写版本/范围/资格引擎。C336/344生产模块、A337与真实服务仍另验；C344捕获短source检查和并发P2记录保留。
- 327已按支持history.2实际原bytes/hash/text/ref/分页/owner/auth/损坏拒绝证据关闭，旧v1拒typed与原13PASS1FAIL保留。315按JT不再投入，等下次真实失败；本轮不自主扩展其他业务，C真实接口缺口按343优先响应。

### B线入口与结果恢复本轮交付（JT 2026-11-01）

- #354由PR359锁head490ecaf合ae417da6：显式needs-structured.1复用C source-input.1，未patch正式run_once/实际CLI＋签名API/受限PG/Fake/Meter→原确认/structured2/NEEDS basis；默认legacy保持，C来源INITIALIZE另见361/362。精确CI全绿，已通知286/21/22/373/C。
- #360（parent25）L0 PR379锁19332a15合35fb4b3f，先冻结publisher@2/configCJ-MESSAGE-EDIT-RESULT@1/profile message-edit-result.1、两类非可接受结果/独立effect、新status/history/display及正负例并立即通知336/337；L1 PR380锁37b95f0f合c138fced交M29与同cursor结果/原ID恢复，精确CI全绿/PG33、一次独立P1返修后APPROVE。B桥接真实C函数/lease不冒称C生产；C381/M30及336随后由C交付。原FAIL与schema关联P2保留，无新权限或第二版本引擎。
- #378（parent22）PR382锁2bb54fed合2d0a1011：独立needs-current-trip.1/C source-input.2正式run_once+CLI，实际registered输入Trip/proposed_fields、手动文本/独立fixed后的原Trip v3→不同新Trip v1、原bytes/receipt/status/history及NEEDS/selection/owner/cancel/UNKNOWN均PASS。六类CI全绿；含C M30实际合并树复验PASS，通知22/286/373/21/C，不等main CI/回执。B业务/共享锁释放，最后B-only handoff与本节合一文档PR。

### M2 最终退出与下一线程边界（JT 2026-11-02）

- M2 milestone3 已关闭（47 closed/0 open）。最后 #332 由 [PR392](https://github.com/JTCAO515/G2C/pull/392) 关闭；#21 由 [PR387](https://github.com/JTCAO515/G2C/pull/387) 按 L0/L1 关闭。原验收与历史 FAIL 保留，真实物理点位验证明确在 #32/#29 既有地图行承接 UNRUN，不计 PASS。上表 B/C 为保留的 owner 历史快照，实时 Issue 和本段优先；本轮 B/C 已交付，统一依据 [C 通知6567906580](https://github.com/JTCAO515/G2C/issues/21#issuecomment-6567906580)，不再要求各写 handoff。
- 正式地点链需显式 `LocalPlaceDraftTools` 与 `PlaceDraftConfiguration(publisher=PlaceDraftAdapter(...))`，`run_once` 默认不开启。App 仅消费正式 Trip place source，原 provider ID/坐标/hash 不变；MapKit 不做坐标转换。
- #398 是 M3 高德替换，不阻 M2：企业技术服务许可/档位/费用、绑定 Bundle ID 的 iOS Key（非后端 Web Key）、第三方 SDK 与创建前隐私同意仍由 JT 处理；MapKit 保留到替换验收通过。MapKit 查看区域发送 Apple 已在 #34/#225 通知，隐私/合规评估不计 PASS。M3 由 JT 另开新线程，本线程不实施、不恢复旧监控。
- #315/#329 保持 OPEN/UNKNOWN；不重复碰绿、不自动重试、不放宽 guard。#186 OPEN 归其 owner，#356 已由 PR357 关闭；#395/#397 非 M2，本轮不处理或等待。当前迁移最高 0030_trip_scoped_result；冻结版本与已应用迁移保持。#194/#159 跳过，真实资源/账号/费用/云/生产/真机继续按既有授权停点与 #32/#29。

### M3 并行线（JT 2026-11-02）

本节替代上方并行线表中的 M2 队列，文件归属和锁规则不变。三条线均为新会话，M2 旧线不续用。

| 线 | 队列 | 新增拥有的文件 | 跨线依赖 |
|---|---|---|---|
| A App | #24 离线行程 → #15 App 原生证据 → #23 历史整理开关和候选确认气泡 → #26、#27 App 入口与设备清理 | 无新增 | 消费 #402 的 `CLEANUP@1.0`、C 的 Memory 新版本、B 的 `FEEDBACK@1.0` |
| B 后端基座 | #402 设计和钩子协议 → #403 → #402 清理角色迁移 → #15 → #27 余项及 B 域钩子 | `backend/feedback/**`、`backend/cleanup/**`、`backend/storage-registry.json` | C 新存储依赖 #402 协议，C #23 依赖 #403 |
| C 记忆 | #23（按 PG 队列、增量沉淀、会话结束摘要、检索入上下文、后台 Meter 拆子票）→ #26 及 C 域钩子 | 无新增 | 依赖 #402、#403 |

- #398 已于 2026-11-04 移到 M4：高德官方 SDK 无 Apple Silicon 模拟器可运行包，需真机测试授权，或高德提供带 arm64 模拟器的 XCFramework。iOS Key 已就绪（Bundle ID `space.go2china.app`），M3 授权条目 1 未使用。
- `backend/storage-registry.json` 同一时间只允许一个开着的 PR 修改；C、A 需要登记时按文件锁处理，C 可在自己的 PR 内登记，不改他人条目。
- 迁移按 `backend/migrations/**` 文件锁串行，下一号 0031。
- JT 的本地清理 DELETE 批准只覆盖 #26/#27 清理路径，范围见两票评论。其他 M3 票不能使用该角色。
- `backend/strict_json/**` 是叶子包，修改时先查文件锁。
- JT 2026-11-02 决定：M3 走 PG 受控路线，不接 ReMe、Mem0、向量或 embedding；离线可读期限为最后成功同步起 14 天；历史整理默认关闭，用户按会话启用（详见 [scope](../scope.md)）。留存期限已定：记忆、聊天、行程、反馈保留到用户删除或注销；运行日志和诊断数据 90 天；备份 30 天滚动。#402 映射数据分类，90 天清理由 #27 落地，备份验证归 #30。

#### M3 A App 子票映射（进度以实时 Issue 为准）

| 父票 | A App 切片 | 正式消费依赖与恢复入口 |
|---|---|---|
| #24 | [#408](https://github.com/JTCAO515/G2C/issues/408) 明确14天策略与注入时钟；余下正式源/时钟锚/App只读接线保留父票 | #402/#27 设备失效/重连清理原调用桥；`CLEANUP@1.0` 域ABI不替代App接口 |
| #15 | 回答与记忆已有入口核查；正式提交及原生证据仍归父票 | B `FEEDBACK@1.0` 固定版本及原动作查询 |
| #23 | 按会话历史整理默认关闭、候选编辑确认气泡由A消费 | C正式授权启停/候选API；B #403 MESSAGE-SOURCE 候选不是C App API |
| #26 | 整条删除、停止使用/清理进度分开显示由A消费 | C删除到原清理操作可信关联，B清理进度版本 |
| #27 | [#418](https://github.com/JTCAO515/G2C/issues/418) 三类设备物理原语；[#415](https://github.com/JTCAO515/G2C/issues/415) 双语入口/范围/原生AX；全设备钩子与原注销接线仍在父票 | B原注销确认、撤权后受限进度HTTP、设备桥；其余已提供缓存一起纳入 |

以上不新增队列或文件归属；不把局部原语、布局fixture或接口ABI当作正式App组合。当前可恢复字段与逐项缺口看各父票及A handoff；接口到达后沿24→15→23→26→27推进，#27由最后交付线关闭，M3里程碑不在本线关闭。

### M4 并行线（2026-11-04）

本节替代 M3 并行线的队列，文件归属和锁规则不变。三条线均为新会话。

| 线 | 队列 | 新增拥有的文件 | 依赖 |
|---|---|---|---|
| A App | #398 Part1 PR525已合；→ #498 本机矩阵PR506及设备准备已交；→ #4、#29 真机/VO，当前整队列挂起 | 无新增 | M4条目1/2已到，等JT连接通知后恢复指定真机；测试域名等B在#30通知ready，其他设备/TestFlight另批 |
| B 后端与平台 | #2 真实 Qwen（M1 条目 1）→ #496 部署制品与本机恢复演练 → #30 云环境 → #32 真实接入 | 新增部署目录、备份恢复脚本 | 云、域名、预算等 #495 |
| C 质量 | #28 不变量（本机 L1）→ #497 评测集与判定程序 → #32 真实复跑 | `eval/**`（JT 本轮明确归C） | 真实复跑等 #2、#495、#225 及B正式真实入口 |

- C 子票结构：#28 → #501 身份/执行恢复、#502 原回执/正式提交并发、#503 记忆撤回/注销在途、#504 文本/网络边界；每张3–4框。#497 属 #32，负责合成中英/固定留出/独立判定/报告。真实模型与费用转#32、真实存储备份转#30、设备转#29；进度仍以实时Issue为准。
- #495 汇总全部 JT 决策和资源；各线遇到对应停点在 #495 写一行，跳到本线下一项，不结束 goal。
- #33 受邀内测最后执行，前置是 #29、#32 通过、#225 定案、#495 的分发与准入完成。
- M1 授权条目 1（DashScope）、2（Supabase 测试项目）有效至 2026-11-30，只用合成数据。
- 高德 SDK 只进本机构建配置，CI 的 arm64 模拟器构建不能因此失败。

- A（本轮恢复Goal唯一blocked交接，2026-11-04）：PR525锁c4cf3ca0合a00c7b07，独立APPROVE与精确head11检查SUCCESS；无Key/无签名SDK设备编译、四个选定原生方法及同步B最新main的API/受限PG/Fake中英地图补验通过，原PLACE驱动PARTIAL_PASS不提升。M4条目1/2已生效；真机、SDK运行、中英标注和VoiceOver按JT指令等连接通知，#398/#498/#4/#29保持OPEN；不是缺Apple账号/指定设备授权。#30未通知测试域名就绪；使用记录由文档owner更新，本轮Key未读/0地图/0其他服务/0元。历史FAIL/P2和PR506原矩阵保留，暂缓期间不接触设备或重复跑矩阵。

- A（2026-11-04，PR506）：Production正式ID/隔离/签名占位/模板与本机20范围、34原生测试已交，精确head11 checks PASS；#4补iOS18原型运行记录。历史FAIL保留。#398/#498/#4/#29均OPEN，余项仅等#495资源/批准；不以矩阵分切片、编译或AX冒真机、连续真实账号E2E或VoiceOver。高德0地图/0其他业务/0元，Key仅进忽略本地候选；使用记录待授权文档owner同步。
