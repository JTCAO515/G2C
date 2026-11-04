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
本机正式配置仍只准 FakeProvider，评测类保持原 Fake-only 检查；不把真实模型
伪装成 Fake 绕过它。真实调用与正式 host 接入归 B / #32；JT 已在 M4 授权
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

真实 collector 应记录：

- `first_body_seconds`：同一客户端单调时钟从提交到首个用户可见的有效正文，
  排除工具状态/空占位；`full_answer_seconds`：同次任务完整回答及必要候选可读。
  包含任务内等待/重试，不重置计时。缺值为null；不从 `api_task_seconds` 或
  `draft_seconds` 推造。原任务类别/集合的独立统计仍保留。
- `independent_judgment`：独立程序的实际硬检查。新记录带
  `kind=program, independent=true, ref=eval/judge.py`；旧#497记录按原程序引用
  保留兼容。模型自评或缺少检查不能认证硬项，FAIL标签不能被PASS标签覆盖。
- `serious_error_review`：`kind=human/program`、`independent=true`、
  `outcome=PASS/FAIL/UNKNOWN` 和非空`ref`。这是完整严重错误审查的依据，
  不能由model声明零错误。已观察的严重错误，即使`resolved=true`，也仍使
  同一候选FAIL；必须以新候选/新尝试重新记录，原失败不删除。
- `model_calls`、`tool_calls`、`memory_calls`：完整任务的实际调用量，未提供
  为null/UNKNOWN，不填零。费用沿原`cost.components`，金额为十进制字符串、
  币种与来源保留；新增`basis=billed/estimated/reserved`，真实账单还需要
  `receipt_ref`。只有完整账单覆盖才是已知实际总额；估算、预留与缺账单分别展示，
  不当成实付。费用完整性是报告字段，不添加JT未批准的单任务费用门槛。

`plan.networks` 冻结每个真实网络组及其环境/证据；本机ASGI不冒充目标网络，
测试后端 `api-beta.go2china.space` 的测量等B在#30通知就绪后再执行。

Fake/local/synthetic 报告会显示门槛的诊断PASS/FAIL/UNKNOWN，但
`evaluation_release_decision=UNRUN`，不算真实结论。只有`evidence_layer=real`
且全部候选范围内语言/网络的四项门槛均PASS，才输出该范围的评测质量PASS。
原`release_decision`保留全项目其他前置的区别。报告程序不认证外部文件的
真实性；计划、原始观测和审查依据须由可信执行方冻结并供核对，不交给模型改写。

实际执行预算仍遵守 M4 条目3/4：模型与M1合计¥300、¥240停；指定工具合计
¥100、¥80停及地点600/路线300/天气100/事实页120次上限，至2026-11-30。
报告计算不发出请求，也不代替B原计量出口/预算账本；不得用模型模拟成Fake
或未知费用当零来绕过停止点。
