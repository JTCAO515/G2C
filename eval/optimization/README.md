# 对话行为评分接口：Lio v2

当前 Lio 开发评分使用 `G2C-dialogue-score.2`、`G2C-dialogue-cases.2` 和
`G2C-dialogue-task-contract.2`。版本/文件摘要及替代关系见 `release-index.json`，
消费者还必须冻结经 R 审查的仓库提交。v1 原数据、样例、评分器、历史报告和
开发12/验证8的分母保留，已被 v2 取代，不能把 v1 M1 签名控制当作 Lio v2 采集。

依据 [JT Lio 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6736601057)
及 [R 语义核对](https://github.com/JTCAO515/G2C/issues/761#issuecomment-6789992233)，
本轮只升级公开题集和离线判据。完整 B 可信采集仍等 #762 第二部分合并后的精确实现。
`REPORT-v2.md` 记录合成控制证据，不能证明真实产品质量。

## v2 运行与输出

```sh
mkdir -p .local/optimization
uv run --locked python -B -m eval.optimization.examples_v2 --control good > .local/optimization/v2-observations.json
uv run --locked python -B -m eval.optimization --observations .local/optimization/v2-observations.json > .local/optimization/v2-report.json
uv run --locked python -B -m unittest eval.optimization.test_score
```

验证组在生成和评分两条命令上均加 `--split validation`；坏控制改为 `--control bad`。
Python 入口为 `from eval.optimization.score_v2 import dataset, score`。
批次结构和四态逐项报告沿用下方 v1 定义，但 `version`/`dataset_version`/`dataset_sha256`
必须来自 v2。CLI 严格依 `batch.version` 路由，拒绝未知版本、版本混搭和摘要不符，
不自动回退。原 v1 批次仍走原评分函数，完整报告字节保持可重复。

每格输出完整 `checks`、`hard_status`、失败或缺证原因与原件引用，并按语言给分母。
`FAIL` 优先于 `UNKNOWN`，没开始的格为 `UNRUN`。CLI 成功只表示生成了报告。
固定好坏控制的字段是有意合成的观察，不能复制进真实 runner 作为证明。

## v2 任务与原动作

10个完整任务、中英20格及 split/family 分配不变；family ID 是保留的谱系标识，
历史名称不是当前目的地。三个已保存行程题使用不同日期、固定项和景点，避免同一
旅行跨组；中英改写及衍生任务始终随完整旅行分组。公开 validation 不是隔离最终题。

| 任务 | v2 执行和确定性要求 |
|---|---|
| `dev-local-edit` | 12月1–2日北京酒店见面行程，经原 Lio 明确保存为v1，再对话修改同一Trip为v2；完整业务diff仅改变第二天下午，固定项不变，原历史内容不变。 |
| `val-undo` | 12月15–16日北京车站见面行程保存v1、修改v2，读取当前真实 `undo_target`，同身份执行原生撤销，内容恢复v1并追加v3；原v1/v2都保留。 |
| `val-confirm-save` | 2027年1月5–6日北京讨论，前两轮即使参数齐全也零写入；第三轮明确要求保存才生成v1。保留原文/source、同MESSAGE/RUN回执和实际内容。 |
| `dev-required-date` | 仅把旧杭州写入控制改为受支持的北京/王府井，仍缺开始日期，只澄清 `start_date`，不得代选或保存。 |
| `dev-tool-failure` | 仅把旧桂林天气控制改北京；按原问题日（Asia/Shanghai）+1绑定目标日，参数/身份准入后，对同一原weather attempt注入确定失败；一次派发，不重试。不能称为真实高德故障证据。 |
| 其余五题 | 保留原题面与规则。西安“先聊聊”的改口是讨论，需实际模型输入/上下文证明保留原条件并更新天数；不能套用北京写入范围拒绝或把用户原话当已实现证据。 |

只有三个 mutation 任务使用 `variants.steps`：`message` 带原文；
`lio_undo_current_trip` 是原生操作，不是对话消息。其余七题保留 `variants.turns`
及 B/C 每类原执行recipe。取消和新会话等说明不得直接伪造为MESSAGE/RUN回执。
按钮撤销不证明自然语言撤销理解；评分不要求新增助手回复。该格的 `reply.claimed_effects`
根据实际完整可见面独立标注，没有助手执行声明时可为已核实的空数组。
未知ACK须查询同一原action/attempt/target，不能换ID重发。

每个独立任务通过允许的原接口开新会话、沿原身份和writer建立前置；setup全部
MESSAGE/RUN、provider、工具和费用均计入原attempt、共享Meter及现有限额。
`formal_trip_count` 从全部该任务原动作及受保护owner差异中发现新增/触及的Trip，
包括错误目标，不能只数预期目标或把整个Demo账号原有Trip当本次写入。
不删除旧数据、不用管理SQL/bootstrap、新角色或扩展profile预置；原安全setup不存在则
保留完整分母并记 `UNRUN`。跨owner题须用现有允许的异owner原件，否则同样未跑。

删除后召回沿原 MEMORY.2 的合法既有槽/文本（如 `quiet.entrance`、`diet.spicy`），
显式保存两个偏好、原STOP-USE及受保护fence、新会话实际provider输入和正文。
不复制本机retained槽或任意哨兵；括号内“新对话”不证明真实会话已切换。

## v2 状态证据字段

信任边界仍在 runner：核原身份/会话/attempt/操作、原始字节和独立原件引用后，
才归一化成评分输入。评分器只消费观测，不签发回执，不执行写入，也不以语言打分替代状态。

| 字段 | 原件和归一化要求 |
|---|---|
| `before_formal_version`、`formal_trip_version` | 末轮操作前后的受保护正式Trip快照。新保存为0→1；修改为1→2；原生撤销为2→3。公开卡片没有版本号，不能从UI猜值。 |
| `before_trip_id`、`formal_trip_id`、`receipt_trip_id`、`receipt_version` | 同一正式对象和该次原提交回执；修改/撤销不得另建Trip。 |
| `request_message_id`/`committed_message_id`、`request_run_id`/`committed_run_id` | 修改/保存的原请求与实际commit source，逐一相同；不能用setup或另一轮回执。 |
| `request_action_id`/`receipt_action_id`、`undo_target_version` | 撤销实际原action及回执、当前原undo_target对应目标v1。保留opaque target原件；不为按钮编造MESSAGE/RUN。 |
| `operation_content_sha256`、`formal_content_sha256` | 原操作实际提交的完整内容字节与正式读回内容摘要，不能由期望题面生成。 |
| `history_before`/`history_after` | 原受保护历史中版本字符串→完整内容SHA-256，核完整版本集合、旧版本不可变及最新版本字节；撤销还核v3内容等于旧v1。 |
| `write_commits`、`discussion_turns_observed`、`discussion_write_commits` | 末轮实际提交数；保存题另逐轮核前两个讨论轮次及其零提交。不能仅因最后有一个Trip就断言前面没偷存。 |
| `applied_patch`、`locked_items_changed` | 对完整前后业务内容计算实际diff，再投影规范路径（排除版本/时间等元数据）；不得只投影目标路径而漏掉其他改动。固定项必须不变。英文地名保留原英文标签。 |
| `unrelated_trip_mutations` | 受保护owner差异和所有原动作证明无无关Trip变更，不能过滤错误目标。 |
| `weather_request_day`/`weather_query_day`、`weather_region` | 原问题服务器日期、已准入的实际规范化query日和区域；缺原日期为UNKNOWN，日期错或区域非beijing为FAIL。 |

执行声明沿用取消、停止使用记忆和工具效果，Lio新增 `trip_updated`/`trip_undone`，
`trip_saved` 改核原Lio提交，不再接受旧M1 `confirmed_commits`/草稿恢复证明。
错误保存、错误版本、越权、删除后召回和编造执行均为硬失败；缺同次证据为UNKNOWN。
行为标注仍是辅助。无新增依赖或AgentEvals。

## 下游冻结与受控集

E #764 的 v1 预登记应追加经 R 核对的 v2 版本附件，固定新代码提交和数据摘要后才能用，
不得静默换pin或把旧六个缺writer格当新v2结果。B #762 第二部分交已合SHA、
call/propose/query接口、C0/三个原文本槽、模型/提示词/工具pin及E/F原Meter子限额后，
D才接完整可信采集；setup不足或任一原件缺失明确保留UNRUN/UNKNOWN。

旧 `final-manifest.v1.json` 的封存/拒读证据保留，密文不解密、不覆盖。
它和 `comparison-plan.v1.json` 属于v1，**不能用于当前Lio v2比较**。
语义匹配的受控v2最终集需未来单独授权、D/R编制和独审；本轮为UNRUN，
不在仓库、Issue或CI中生成明文，也不重跑旧拒读。#765比较本轮未运行。

---

# v1 历史接口与证据（已被 v2 取代）

以下保留 D 线 [#761](https://github.com/JTCAO515/G2C/issues/761) 的历史用法。当时 E 固定
`G2C-dialogue-score.1`、`G2C-dialogue-cases.1`、数据文件 SHA-256 和仓库提交。
评分接口只读取观测并返回报告。模型、工具、计量及请求执行由调用方沿 B 的现有出口取得。

## 运行

在固定 G2C checkout 根目录运行：

```sh
mkdir -p .local/optimization
uv run --locked python -B -m eval.optimization.examples --control good > .local/optimization/observations.json
uv run --locked python -B -m eval.optimization --observations .local/optimization/observations.json > .local/optimization/report.json
uv run --locked python -B -m unittest eval.optimization.test_score
```

切换 `--control bad` 得到已知坏样例。验证组在两条命令上显式使用
`--split validation`。`examples.v1.json` 中的中英文本和标注均为合成控制。
CLI 退出 0 表示已生成报告。错误版本、重复/计划外尝试或无效输入退出 2。
E 按报告状态决定是否计入优化。

Python 调用入口为 `from eval.optimization.score import dataset, score`。
`dataset()` 返回公开任务文档和数据 SHA-256。先按任务选择 development，
再按任务语言运行完整会话。传入 `score('development', batch)`。
批次结构：

```json
{
  "version": "G2C-dialogue-score.1",
  "dataset_version": "G2C-dialogue-cases.1",
  "dataset_sha256": "<dataset() 返回的摘要>",
  "run": {
    "candidate_id": "<冻结候选>",
    "adapter_version": "<执行适配器>",
    "model_version": "<模型>",
    "prompt_version": "<提示词>",
    "tools_version": "<工具>"
  },
  "observations": [{
    "task_id": "dev-airport",
    "language": "en",
    "attempt_id": "example/airport/en/1",
    "reply": {
      "attempt_id": "example/airport/en/1",
      "ref": "<可追溯的独立标注>",
      "values": {"mode": "answer", "addresses_request": true, "claimed_effects": []}
    }
  }]
}
```

示例省略 state，因此这格为 UNKNOWN。完整 state 与 reply 输入见运行示例生成的
JSON。每个候选批次一格最多一次，用原任务尝试及原件引用。保留首轮和各次复跑
报告，分开传入，不能择优回填。报告按总计和语言分组输出计划分母、四态、硬失败数。
`rows[].checks[]` 含要求、观测、证据引用与失败或缺证原因。未开始为 UNRUN，
已尝试但缺少关联证据为 UNKNOWN，已知 FAIL 优先。语言分数不参与状态判定。
输出中的 PASS 只表示该格满足此版本判据，产品放行仍走 #32/#702 原评测口径。

## 采集边界

`cases.v1.json` 固定每个任务的预置条件、完整用户轮次、检查和双语变体。
每个证据段都有相同的任务级 `attempt_id`、可定位原件的 `ref`、以及 `values`。
可信 runner 在填表前核同 owner、会话、原动作/原 RUN 和相关轮次。一次任务可以
引用多个原件，ref 指向该次任务的证据清单。缺测用缺字段或 null。0、false 和
空数组只用于已观察完相应范围、可证明为零或没有事件的情况。

| 段 | 证据来源和归一化 |
|---|---|
| `state` 基础 | 原 C 判据读受限角色、其他 owner 的 MESSAGE 读写和正式 Trip 数。每任务从隔离预置状态开始，`memory_item_count` 记录任务过程中新增的未确认条目，排除预置数据。跨账号任务另测目标 Trip 的越权读取、变更与正文私有哨兵。 |
| `state` 写入和撤回 | 原确认提交回执及实际持久状态。新增保存读取确认次数、正式版本、确认的原候选字节摘要与实际持久内容摘要。局部修改及撤回比较完整草稿再投影到变更路径，包含锁定项。取消读取原 RUN 终态、晚到可见发布及取消后派发。工具失败读原工具 attempt 状态和派发数。 |
| `state` 删除后召回 | 原 stop-use 提交与 fence、条目资格、后续完整 provider 输入和最终正文。检测被删除项哨兵并保留另一条有效偏好作正控；这一场景覆盖停止使用和后续召回，物理清理仍沿现有生命周期验收。 |
| `state.verified_effects` | 末轮回复所引用的同一操作、对象和版本中，有独立回执或状态证明的效果。必须排除之前尝试的回执和错目标回执。仅在完整核对后填空数组。 |
| `reply` | 从实际末轮可见内容独立标注行为。澄清标注实际索取的字段，按字段名升序。记录全部执行声明，包括否定与假设语境的区分。回执词、候选自评或模型的 PASS 字段均不可作为状态证明。 |

执行声明使用 `trip_saved`、`draft_undone`、`run_cancelled`、
`memory_withdrawn`、`tool_succeeded`。其它实际执行声明及错对象、错轮次、
错版本声明标为 `unmatched_execution_claim`，无法出现在已验证效果中。对前述五种可验证效果，评分器还逐项核对同次状态。
失败回执不能支撑成功声明，只有效果标签、缺少状态为 UNKNOWN。
自由文本含义未核时保留 UNKNOWN，评分器没有关键词成功判据。

报告复用 `eval/judge.py` 的角色、跨 owner、写入计数和正式版本判据，
以及 `evaluation/cj028/evaluate.py` 的严格 JSON 读取和分母表示。
本切片没有新增依赖或使用 AgentEvals。语言辅助评估如需新增，应另行核实官方
接口与许可证并锁定版本。

## 数据用途和交接

- development 用于开发和 E 的反馈循环。validation 用于冻结候选后的内部核对，
  内容也公开，只能证明公开验证。每次运行以整个任务为单位保留前后轮次与中英改写。
  `trip_family` 分组在加载时检查，同一旅行及其派生任务必须沿用原 family ID。
- 最终题及答案不在本仓库、Git 历史、普通 Issue、共享 worktree 或 CI artifact。
  JT 在 #495 的2026-11-11决定指定仓库外加密和JT独占解密秘密，D/E/B开发会话
  按同一密文实测无法解密。封存、分母与拒读状态以本轮公开元数据和PR证据为准。
  受控侧去重完整旅行家族和翻译改写，记录整体摘要、分母与用途，公开只交元数据。
  口令由JT在本机隐藏窗口设置；R于后续获准比较时取得解密权限。
- B [#762](https://github.com/JTCAO515/G2C/issues/762) 交可关联原动作的可信观测。
  E [#763](https://github.com/JTCAO515/G2C/issues/763) 固定上述版本与摘要。
  R [#772](https://github.com/JTCAO515/G2C/issues/772) 独立核对规则和已知好坏样例。
  真实服务回归由 #32/#702 承接。候选比较和晋级等后续 Goal。

## 签名本机评分证据

`G2C-signed-score-probe.1` 使用 C 的原签名 harness、独立 Unix-socket PG、原 worker
和 FakeProvider，实际读取原动作回执、正式内容、withdraw fence、后续模型输入和
可见正文。每个控制分别运行中文和英文，保存同一份观测后用两个独立评分 CLI
进程评分并比较完整输出字节。评分器和公开题集保持原固定版本。

```sh
CJ_ENV=local CJ_PG_BINDIR=/path/to/postgresql17/bin \
  uv run --locked python -B -m eval.optimization.signed_probe --output .local/signed-score-new
```

五类控制分别为正确保存、签名提交错候选、无提交却声明已保存、撤回后保留另一偏好、
故意错误 FakeProvider 在可见回答中召回已撤回的哨兵。后两类均实际提交 stop-use，
后续完整 provider 输入仍需保留有效项并排除被删项。负例是本机故意错误控制，
用于证明硬失败优先，不据此宣称现役产品有同一失败。
每批计划分母仍为验证集8格，仅采集对应任务的2格，其余6格UNRUN。
自由文本仅对这里固定的已知控制独立标注，真实 B 对话仍须按原件独立审阅。
输出目录拒绝覆盖，原失败/修复记录保留，运行日志和原始观测放忽略目录。

## 最终题封存

JT 在 #495 的2026-11-11决定授权 D/R 编制最终题，密文放仓库外，JT独占解密秘密。
编题规则与覆盖由 D/R 核对，D 唯一编制密文；编题作者的曝光如实登记。
封存后的拒读只证明当时的解密访问控制。它不能证明作者从未接触编题规则或内容。
受控文件包含完整任务和中英变体，只用于 #765 后续独立验收，不能用于教师、优化或训练。

`custody.py` 固定本机 age v1.3.2。使用 JT 在本机隐藏窗口设置的专用强口令，
口令、题集明文及 age 往返校验结果仅经匿名管道和短生命周期内存，命令不打印它们。
流程不把口令放 argv、环境变量、文件或日志。作者仍能看到编制程序和公共规则，
流程不承诺擦除操作系统内存/交换区或所有会话记录。最终题的实际文本与答案不输出到
命令记录、仓库、Issue、共享 worktree 或CI。只持久保存仓库外密文及公开hash、分母、用途。

先用公开控制运行加密、篡改拒绝和缺口令拒读回归，再封存。写入前以JT当次口令
在内存解密并核同payload，完整密文一次性写出；取消、口令不符或校验失败均拒绝生成。
JT需自行保管口令，#765获准执行时只交给R。D/E/B各自对同一密文实测不带秘密的解密，
探针先匹配已成功封存的固定manifest摘要，再由age-inspect验证非空scrypt密文格式，
只把无口令且无控制终端的确定拒绝记为PASS。坏件/错摘要/非密文均拒绝。报告退出码、
解密输出字节数、密文摘要和状态；自填session标签不充当主体证明，需对应会话原执行记录。
错口令测试不能代替三会话实测。

```sh
uv run --locked python -B -m unittest eval.optimization.test_custody
uv run --locked python -B -m eval.optimization.custody deny-probe \
  --ciphertext /external/path/final.age --manifest eval/optimization/final-manifest.v1.json --session D
```

封存由受控侧把题集仅在内存传给 `seal(payload, external_path)`。公开接口只返回
整体明文hash、密文hash、任务/家族/语言/类别分母与用途。`seal`拒绝Git worktree内
的输出位置和覆盖已有密文；最终加载器不进入E的公开开发评分入口。
只读回归需要已有 age v1.3.2，沿官方 CLI 的 passphrase 模式，不新增生产Python依赖。
官方接口见 [age v1.3.2 手册](https://github.com/FiloSottile/age/blob/v1.3.2/doc/age.1)，
许可证为 [BSD 三条款](https://raw.githubusercontent.com/FiloSottile/age/v1.3.2/LICENSE)。

#765 的三组配置、当前依赖、全量分母、既定指标、改善定义、停止/恢复和晋级条件
在 `comparison-plan.v1.json` 预登记。未知的候选/模型/适配器字段须在获准执行前冻结；
当前登记版本不授权实际比较。

受控任务的known_fields分别记录task_clock和travel字段。缺日期控制的travel.start_date必须为null。
封存边界按原评分器的每类behavior/state字段与类型校验，并核对comparison-plan的版本、分母及类目配额。
#765由D拥有运行软件，由JT专门授权的R会话持钥执行，题目与逐题原结果留在受控侧。
