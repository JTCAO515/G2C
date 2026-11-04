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
均可分开核对；无已批准质量阈值，报告没有放行权。

真实 host 复跑后，可按相同格式提供实际观测与独立判据：

```sh
uv run --locked python -B eval/report.py --plan PLAN.json --observations OBSERVATIONS.json --output REPORT.json --markdown REPORT.md
```

计划中的 `networks` 可承载海外行前/中国境内旅行的真实分组与设备/运营商依据；
费用使用原有 `cost.components` 的金额十进制字符串、币种、来源与完整性，缺项
保持 UNKNOWN。CLI 不创建真实观测，也不认证外部提供证据的真实性；计划与
观测由可信执行方冻结/提供，不能由模型改写。模型裁判不认证事实、归属和写入。
本机正式配置仍只准 FakeProvider，评测类保持原 Fake-only 检查；不把真实模型
伪装成 Fake 绕过它。真实调用与正式 host 接入归 B / #32，质量/预算/地域仍等
#495/#225；C 未调用真实模型、工具、云资源或任何付费服务。

验收分层：新增判定回归单独运行；仓库既有 `scripts/test.py` 和完整
`scripts/pg_suites.py` 及精确 head CI 仍保留。未修改 CI 或测试入口，不声称
既有 CI 自动执行了新增 eval 场景。
