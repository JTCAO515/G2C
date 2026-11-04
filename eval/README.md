# M4 本机实验与效果评测

仅合成输入、私有 Unix socket PostgreSQL、签名 HTTP 入口与原 worker。
`runtime.py` 复用仓库 PG/登录支架，不读取 ambient DSN 或真实模型凭据。
业务 SQL 经 `cj_m1_runtime`；initializer 只负责全新库迁移。

```sh
uv run --locked python -B eval/invariants.py --output .local/eval/invariants-001
```

每次输出目录必须不存在，以保留历史 FAIL。`report.json` 逐项记录触发、
预期、实际返回/PG 状态、head、脏状态、环境和耗时。复用现有故障操作时
列出实际执行入口；不是源码文字检查。运行日志放 `.local/` 或 PR artifact，
不提交到仓库。PASS 只证明该本机确定性实验，真实模型效果、设备与云仍 UNRUN。

按切片运行（每次使用新的输出目录）：

```sh
uv run --locked python -B eval/invariants.py --suite isolation --output .local/eval/owner-001
uv run --locked python -B eval/invariants.py --suite commit --output .local/eval/commit-001
uv run --locked python -B eval/invariants.py --suite memory --output .local/eval/memory-001
uv run --locked python -B eval/invariants.py --suite external --output .local/eval/external-001
```

| 子票 / 本机实验数 | 真实触发与判据 |
|---|---|
| #501 / 8 | 外账号 API/SQL/worker、commit 后子进程退出、两 worker 竞争、部分失败、UNKNOWN、在途取消、UTF8 缺段/过期与物理事件损坏、注册后台 owner/ACK/共享限额 |
| #502 / 4 | 同字节消息并发、同确认并发、两不同候选争同正式版本、SQL 前回滚与真实 commit 后丢 ACK |
| #503 / 10 | typed 完整当前性、在途撤回、保留聊天三阶段、共享候选/缓存重建、source2/scoped、前台/后台注销、首次 scope 创建竞态 |
| #504 / 6 | 七类禁止 origin、八类混合 DNS、真实本地 TLS 故障、恶意记忆文本、FACT 注入、后台恶意 tool_calls 与限额 |

各实验入口的说明给出触发和预期；实际状态由返回值、真实 PG 查询或原实现
故障程序的完整 stdout/stderr 记录。`implementation_probe` 运行的是签名 API /
受限 PG / 原 worker 的完整故障程序；保留程序内各断言及真实失败位置，不把
普通模块单测当组合证据。initializer 仅作全新库迁移与明确标注的一次性故障注入。

28 项是本机覆盖清单，不是 28 个现实服务场景或全产品验收。真实模型文本
遵循指令的质量、实际供应商结果/费用、目标网络 → #32；云存储、真实备份和
最新撤回 fence 重放 → #30（本机部署/恢复 owner 为 B #496）；真机、实际
VoiceOver 与离线设备 → #29。全部保持 UNRUN，须在目标票登记回链后才可
按 ADR-0007 转记。App 组合复用实时 #23/#26/#27 已合并的 L1 证据（PR487/488），
不把这些后端实验冒称本轮重新执行了 App 或全设备验证。

历史 FAIL 不覆盖：开发首轮短片段未达既有发布缓冲；外部文本实验首轮把
`Ledger` 当作字典读取。两项均属评测程序错误，修正触发/读取后复跑，原报告
仍单独保留。产品历史 FAIL 及 UNKNOWN 不因上述修正被删除或升级。

## #497 合成评测集与报告

`scenarios.json` revision 2 固定 33 对中英产品场景，11 对为留出集。
原 revision 1 的 30 个 ID、输入和 10 对留出未改；只追加事实、经历和历史
授权边界三个覆盖样本。每次报告绑定文件 SHA256、输入版本与候选 head。
全部是合成资料，未用于模型或提示词调优；FakeProvider 的实现不因留出结果改变。

```sh
uv run --locked python -B -m unittest discover -s eval/tests -v
uv run --locked python -B eval/run.py --output .local/eval/fake-new
```

默认每场景分别运行中文/英文、attempt 1/2，共 132 次完整任务。每个 attempt
使用新私有库；每次任务通过签名 API、受限 PG、原 worker 和实际 FakeProvider。
规划场景会读真实候选，接受/拒绝场景使用真实确认字节并读正式状态；记忆
场景执行真实明确保存/编辑/停用/撤回及下一轮、新聊天、新进程、另一旅行读取。
事实、经历、偏好分别保存。反馈、账号与未开放工具等对话样本检查说明与
不自动执行的边界，不能据此冒称实际执行了这些功能；组合故障覆盖见 #28。

输出 `plan.json`、逐次 `raw/`、全部 `observations.json`、`report.json` 和 `report.md`。
`--only ID ...` 仅用于调试，其他计划格仍为 UNRUN，不缩分母；输出目录存在则拒绝。
执行失败保留 traceback，重复尝试分别存放；不会挑最好一次替换首轮。

`judge.py` 直接比较实际 PG/API 状态、原候选字节和实际 provider 输入，
判定 owner、写入、当前/撤回记忆；已知天数/预算/交通等没有可核验的结构化
观测时为 UNKNOWN，不将未知价格算零或解析文本时间为已验证结构。模型的
自评分不参与这些判定。Fake 回答的语义、事实质量及语言可理解性全部 UNKNOWN，
因此 hard PASS 不会把任务或真实效果升级为 PASS。

报告复用现有 `evaluation/cj028/evaluate.py` 的矩阵、留出、严重错误、失败/重复、
精确 Decimal 费用与 UNKNOWN 口径，不新造第二套成功率/费用算法；另加真实
本地模型 stream 调用量和 API 任务耗时。耗时含场景内提交/worker/最终读取，
首正文与草稿的 **UI 可见延迟** 未测仍 UNKNOWN，不能以 API p95 代替 #32 门槛。
Fake 无真实货币回执，费用保持 UNKNOWN。中英、网络、集合、任务类别和尝试
均可分开核对；JT 门槛已确认，评测质量判定见下节，全项目发布仍有其他前置。

真实 host 复跑后，可按相同格式提供实际观测与独立判据：

```sh
uv run --locked python -B eval/report.py --plan PLAN.json --observations OBSERVATIONS.json --output REPORT.json --markdown REPORT.md
```

计划中的 `networks` 可承载海外行前/中国境内旅行的真实分组与设备/运营商依据；
费用使用原有 `cost.components` 的金额十进制字符串、币种、来源与完整性，缺项
保持 UNKNOWN。CLI 不创建真实观测，也不认证外部提供证据的真实性；计划与
观测由可信执行方冻结/提供，不能由模型改写。模型裁判不认证事实、归属和写入。
`run.py` 的本机配置仍只准 FakeProvider，原 Fake-only 检查保留；不把真实模型
伪装成 Fake 绕过它。真实正式 host 接入归 B / #32；JT 已在 M4 授权
3/4 批准北京端点与指定工具的合成复跑，但必须先消费 B 已合并的真实 adapter，
并沿用其原 attempt/计量/预算证据。#225 法务/文案未定时仍不能发送真实用户内容。

验收分层：新增判定回归单独运行；仓库既有 `scripts/test.py` 和完整
`scripts/pg_suites.py` 及精确 head CI 仍保留。未修改 CI 或测试入口，不声称
既有 CI 自动执行了新增 eval 场景。

## JT 2026-11-04 内测门槛

`gates.py` 固定使用 `docs/scope.md`、#495/PR518 的批准值；观测或模型不能
通过 `approved_thresholds` 改写它们。`quality_acceptance` 按候选、语言、网络
分别输出 `criteria.*.status`、`passed`、值、样本数和分母：完成率 ≥90%，
严重错误0，首字 p95 ≤5秒，完整回答 p95 ≤90秒。样本/留出和全部原尝试不变。
不同候选不能合并或自动挑最好版本；同候选任一语言/网络失败不能由另一格抵消。

完成率沿原口径 P/(P+F+U)，缺测R保留并阻止PASS。延迟使用全计划样本的最近秩
p95；缺时延不能从分母删除，只给已知子集诊断。已知慢样本已足以证明全计划
p95超标时可FAIL，其他缺测为UNKNOWN/UNRUN。没有完整观测不能凭成功子集放行。
外层任务PASS不能覆盖所引用程序明确返回的UNKNOWN/FAIL；判据引用本身UNKNOWN
也不进完成率分子。独立严重错误审查FAIL（包括外层标为missing）作为失败尝试保留。
独立程序明确任务FAIL也不能由另一位裁判的PASS覆盖；UNKNOWN可由有据的独立复核
补充，明确FAIL必须保留。任务从missing变为FAIL时，其原来不可用的时延/费用/
调用量仍不可用，不因结果归类变化而伪造成观测值。

真实 collector 应记录：

- `first_body_seconds`：同一客户端单调时钟从提交到首个用户可见的有效正文，
  排除工具状态/空占位；`full_answer_seconds`：同次任务完整回答及必要候选可读。
  包含任务内等待/重试，不重置计时。缺值为null；不从 `api_task_seconds` 或
  `draft_seconds` 推造。同一单调时钟下完整回答早于首字是输入错误，拒绝放行并保留原值。
  原任务类别/集合的独立统计仍保留。
- `independent_judgment`：独立程序的实际硬检查。新记录带
  `kind=program, independent=true, ref=eval/judge.py`；旧#497记录按原程序引用
  保留兼容。按冻结场景核对全部适用检查名称与actual/expected一致性；只给一项
  PASS或缺owner/写入/撤回断言不能认证硬项。硬FAIL或任何来源已知严重错误会
  先覆盖任务PASS，再计算分组/完成率；嵌套程序错误与原顶层错误都保留，原观测不改。
- `serious_error_review`：`kind=human/program`、`independent=true`、
  `outcome=PASS/FAIL/UNKNOWN` 和非空`ref`。这是完整严重错误审查的依据，
  不能由model声明零错误。已观察的严重错误，即使`resolved=true`，也仍使
  同一候选FAIL；必须以新候选/新尝试重新记录，原失败不删除。
- `model_calls`、`tool_calls`、`memory_calls`：完整任务的实际调用量，未提供
  为null/UNKNOWN，不填零。费用沿原`cost.components`，金额为十进制字符串、
  币种与来源保留；新增`basis=billed/estimated/reserved`，真实账单还需要
  `receipt_ref`。只有完整账单覆盖才是已知实际总额；估算、预留与缺账单分别展示，
  不当成实付；原`groups[].cost`也仅统计有账单依据的实付，不合计估算与预留为
  “已知费用”。原始components仍完整保留。费用完整性不添加JT未批准的单任务费用门槛。
  UNKNOWN币种或missing尝试的账单不能成为旧/新字段的已知实付。

`plan.networks` 冻结每个真实网络组及其环境/证据。真实组须有
`kind=local_real_services/target_network`、`endpoint`、`client_environment`和
`measurement={kind:program/human,independent:true,outcome:PASS,ref:...}`。空值或
UNKNOWN标记不能认证测量。本机ASGI不冒充目标网络；完整候选放行还须计划并测量
`target_network`组，endpoint为`https://api-beta.go2china.space`。该组测量等B在#30
通知就绪后再执行；按scope.md分别保留`travel_phase=overseas_pretrip/china_travel`
两种来源，缺失地域直接列UNRUN，不用单一地域放行整体。缺组/未测不输出候选PASS；
本机或单一网络真实服务范围的四指标可先单独报告，不冒其他网络已测。

Fake/local/synthetic 报告会显示门槛的诊断PASS/FAIL/UNKNOWN，但
`evaluation_release_decision=UNRUN`，不算真实结论。只有`evidence_layer=real`
且全部候选范围内语言/网络的四项门槛均PASS，才输出该范围的评测质量PASS。
原`release_decision`保留全项目其他前置的区别。报告程序不认证外部文件的
真实性；计划、原始观测和审查依据须由可信执行方冻结并供核对，不交给模型改写。

实际执行预算遵守 PR540 后的 M4 条目3/4及JT最新决定：模型与M1合计¥500、¥400停；
指定工具原合计¥200。JT于2026-11-05将工具停止线由¥160提高到¥10,000
（[#495原文登记](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6644812116)），
没有同步扩大原¥200总预算。预估同时检查停止线与总预算，不能用较高停止线授权超过总额。
地点1200/路线600/天气200/事实页240次上限及2026-11-30期限不变。实际派发仍须B唯一
出口已反映当前授权；C的预检通过不能替代该出口或恢复已sealed的Mac producer。

## 已授权真实批次（#530）

第一轮 B PR524 的固定33×中英、11留出报告保留于 `reports/real-m4-001`；
旧FAIL不覆盖，JT已将原60个RUN UNKNOWN归因于PR532修复的工具续接，不用原批给产品质量结论。
当前 PR532/540 后必须先运行 `CJ_ENV=local CJ_M4_SYNTHETIC_ONLY=1 uv run --locked
python -B eval/smoke.py --output .local/eval/round2-smoke`，中英各3例覆盖place+route/weather/fact。
任一原RUN未知/空正文或缺指定工具/后续模型回执即停止新出口，其他计划格UNRUN；报告#523并通知B。
仅六格全PASS且同一候选才运行 `CJ_ENV=local CJ_M4_SYNTHETIC_ONLY=1 uv run --locked
python -B eval/real.py --batch-id round2-full --smoke .local/eval/round2-smoke --output .local/eval/round2-full`。
产品33/11样本、输入和judge/gates不变；前置smoke是独立接入门禁，不计入质量完成率。
开跑前按原137模型/54付费工具占用和6例预估，投影会越新停止线则先在495报告，不发请求。
`authorization_checkpoint.json` 固定本轮开始前250个原意图的ID/种类/输入哈希；开跑先只读原账本，
缺库、截短或原意图变化均退出，不自动新建“零占用”。M1的¥13与所有UNKNOWN继续占用。
冒烟证据必须与该唯一账本逐条一致，原注册模型输入经B实际serializer离线算哈希并与真实出口核对；
指定工具结果须经匹配的native tool_call_id进入后续模型。离线fixture本身不能认证真实PASS。
同一adapter的smoke/full阶段在固定用户数据目录各原子认领一次；输出目录或C提交名变化不产生新派发。
中断/失败只读原结果，完整smoke原证据在独立阶段凭证中锁定哈希。只有B实际adapter修复产生另一候选，
才会有独立阶段身份；所有旧FAIL仍保留，不以换目录重复收费。
目录存在时只读返回；不恢复或重发未知原动作。模型、端点、工具、凭据来源及
唯一累计授权账本沿用 B `RealServices`，没有任意 URL、模型或预算目录选项。
旧 M1 ¥13 及 B 的并行调用不释放；观测只归属本场景原 Meter attempt，
全局账本快照另存，不能把其他线的并行调用算成本线。

签名 MESSAGE-send.2、原 NEEDS 来源、Trip 显式确认与 typed Memory 保存/管理/撤回
经现有 API；角色/owner/正式写入/上下文由原独立 judge 核对。重启案例用新真实
worker 进程消费同一 PG/原消息/授权账本。使用 B 已交 legacy draft，不绕过它与
结构化 draft/tool profile 的组合边界；不能验证的结构化硬字段保持 UNKNOWN。

当前 travel.2 的冻结 v1 SSE 读口不能消费新版上下文，采集用实际 TCP 的
`/v2/run-display` 保护快照，每200ms读取。首正文是客户端首次读到有效回答的
单调时钟上界，排除工具来源链接；完整回答含必要候选实际读回，确认动作不计入。
提交早于RUN建立的503只允许重读原快照，不重新提交消息。当前 Mac 出口不能证明
海外/中国目标网络，后者仍等 B #30 就绪通知，缺测为 UNRUN。

原始HTTP响应、用户可见回答、客户端时间、原注册输入、库状态、预算 intent/回执
保存于输出目录；不写凭据或JWT。无供应商账单时实付 UNKNOWN，保守占用单列。
自动判定只报告可证明的硬项；无独立完整语义/事实复核时，不伪称人工审阅或零严重错误。
模型回答与模型裁判均不能给硬项和严重错误作自证。日志/原始压缩包不入库，报告摘要
与可核对证据链接随 PR 提交，历史失败保留。
报告计算不发出请求，也不代替B原计量出口/预算账本；不得用模型模拟成Fake
或未知费用当零来绕过停止点。

## 香港唯一 producer 的 C 执行准备

Mac账本完成seal/adopt后，旧Mac仅只读；新阶段只能在B正式交付的HK环境执行。
当前准备代码不表示 #30 ready，也不授权提前调用目标域名。B负责部署接线，C仅交
已提交源码与参数；不修改B/deploy/授权文件、不另建或恢复一份可写费用账本。

`hk.py package`只读取干净Git提交，生成可重现的C overlay及来源manifest，不构建镜像，
不读凭据、不请求任何服务。必须给B已审的后端commit，并逐字核对C提交所含业务源码
与该B提交一致；镜像中的既有B文件逐个核hash，不能用任意标签伪造候选或安装假git。

```sh
uv run --locked python -B eval/hk.py package --backend-commit B_FULL_SHA --output .local/c-hk-source
```

B在既有已审operator镜像上使用输出中的`eval/hk.Dockerfile`，固定镜像身份与manifest
SHA，分别记录B后端pin和C runner pin。该overlay只加入已提交的eval运行源码、固定
样本/原250行见证和既有报告计算器；不打包工作区秘密、历史raw、测试或报告日志。
所有原测试仍保留并独立执行；overlay并不是测试验收证据。

最小执行布局：

| 输入/挂载 | 边界 |
|---|---|
| `CJ_C_EVAL_SOURCE_SHA256` | B从C已交制品核对的manifest SHA；不能从未核文件自行填一个值 |
| `/app/c-eval-source.json` | 来源manifest只读，实际B/C文件hash必须匹配；报告记录两个commit |
| `/run/secrets/c-eval.env` | 当前uid所有、0600、常规文件；恰好`CJ_MODEL_API_KEY`和`CJ_AMAP_WEB_KEY`两项，来自现有安全凭据，不入镜像/Config.Env/日志 |
| `/evidence` | 仅C本阶段raw/计划/报告持久写卷；完整阶段仍须原六格全部PASS及canonical凭证 |
| 原HK预算目录及`/control/budget` | B同一个ADOPTED账本和非恢复控制锚/锁，不复制重置；producer仍`hk-beta-47.83.147.176` |

只提供`CJ_ENV=local`、`CJ_DEPLOY_TARGET=hk-beta`、`CJ_M4_SYNTHETIC_ONLY=1`、
原producer、已核试用期限及上述非秘密来源pin。不得提供Supabase/operator/cleanup/
签名私钥/OSS身份或Docker socket。C只用全新私有Unix PG、`search_path=public`、
镜像中显式`CJ_PG_BINDIR=/usr/lib/postgresql/17/bin`（不依赖宿主pg_config）、
原受限业务角色与原worker；B的授权期限守卫传入原`RealServices.from_environment`。
服务凭据只在构造原服务时暂入进程，随即移除；PG子进程不继承，重启worker从同一
0600子集重新构造服务，不沿用旧Mac SDK。缺件/错误权限/源码不符均停下，不走备用出口。

以下仅为B正式ready、费用出口与C精确head门禁全部满足后的命令布局；本节不执行它们：

```sh
python -B /app/eval/hk.py run smoke --output /evidence/new-smoke-stage
python -B /app/eval/hk.py run full --smoke /evidence/new-smoke-stage --output /evidence/new-full-stage
```

仍固定中英各三例四类工具，任一UNKNOWN/FAILED/空正文立即停；同候选六格全PASS才66。
HK私有PG的loopback采样单独标`hk-private-real-exits`，不能冒充海外/中国目标网络；
目标网络仍等B #30正式ready后另测。所有旧FAIL/UNKNOWN/INTENT保持原样。
