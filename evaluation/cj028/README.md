# CJ-028 离线结果校验与统计

本目录仅为既有评测数据管道准备：标准库 Python CLI，读取调用方明确提供的两个 JSON 文件，不执行 Agent，不访问网络、provider、API、DB、凭据或环境配置。不安装 Promptfoo、裁判或第二运行 Harness。Python 3.9+；没有第三方依赖。

来源：[官方 Issue #32](https://github.com/JTCAO515/G2C/issues/32)、固定基线 `5d8ba113109565a3a133ca11f6be6c964e9be561` 的 `docs/scope.md` 测量定义。Issue 硬 AC 的**独立产品场景至少 1/3 留出**优先；scope 的 6/30 与 30+10 均为未批准提案，本实现不冻结最终场景数、城市、网络或阈值，不修改 scope。原 H/I（CJ-025/027）与真实测量仍未验证。

## 运行

在仓库根目录：

```sh
python3 evaluation/cj028/evaluate.py \
  --scenarios evaluation/cj028/fixtures/synthetic-plan.json \
  --observations evaluation/cj028/fixtures/synthetic-observations.json
python3 -m unittest discover -s evaluation/cj028/tests -v
```

JSON 报告写 stdout；需要保存时由调用方重定向到明确选择的文件。退出码 `0` 只表示输入校验及汇总完成，**不表示产品通过**；退出码 `2` 为读取/校验失败，报告错误、输入路径/哈希、已解析的原始记录，`release_decision=UNKNOWN`。语法错误的原文件仍由路径/哈希定位，不尝试修复/丢弃记录。重复 JSON 对象字段和非有限数字拒绝。

Fixtures 只有 **3 个 synthetic 场景（2 调优、1 留出）及 1 个 synthetic 观测**，全是假造的管道测试数据，无真实旅行事实、模型、费用、时间或网络观察，不是最终场景集或真实测量。`a` 重复 40 次只为 synthetic 候选 SHA。测试里宣告的外部判据也仅为 synthetic 字段测试。

## 输入契约（本目录离线格式 v1）

这不是已批准的正式 API/业务契约。JSON 示例见两个 fixture。文件不得含凭据或不应进入评测报告的个人数据；报告保留输入原文，不自动脱敏或在线读取证据。

场景清单为一个对象：

| 字段 | 内容 |
|---|---|
| `schema_version` | 严格整数 `1`；拒绝 `true` 与 `1.0` |
| `sample_set_id`, `sample_set_version`, `provenance` | 明示样本标识、版本及来源；不据字符串认证真实性 |
| `evidence_layer` | `synthetic` / `local` / `real`，一个输入批次一个证据层；不同层应单独运行 |
| `approved_thresholds` | 外部批准记录或 `null`，原样保留；本轮无阈值执行/批准引擎，不内置 90% / 5s / 90s |
| `attempts` | 此批次事先计划的正整数尝试序号，如 `[1,2]`；不是消息数或工具子调用数 |
| `candidates` | 唯一 `id`、完整 `commit` SHA、`config_version`、`model_version`、`source_as_of`；配置版本须绑定适用 App/API/prompt/契约等版本的外部记录 |
| `networks` | 唯一 `id`、`description`；真实测量时外部说明地区/运营商/设备/OS/弱网设置与来源。synthetic 不得写成真实网络测量 |
| `scenarios` | 下表；按独立场景 ID 统计，不把中英翻译算成两个场景 |

每个场景：

| 字段 | 内容 |
|---|---|
| `id`, `input_version`, `task_kind` | 唯一场景 ID、输入版本及任务类别；普通回答/规划等类别分别汇总延迟 |
| `product` | 布尔值，是否属于产品场景（故障等额外场景不能稀释 1/3 门槛） |
| `split` | `tuning` / `holdout`；两个集合分开汇总 |
| `used_for_tuning`, `history_ref` | 已明示的调优使用历史及依据；留出若已用于调优即拒绝。无法从文件外自动探知历史 |
| `inputs` | 必须恰有非空 `zh`、`en`；验证结构成对，语义等价由外部审阅负责 |
| `expectation_ref`, `pairing_ref` | 外部业务断言/双语配对审阅依据；CLI 不裁判旅行事实、归属或写入状态 |

观测文件为数组；每个记录代表一次完整任务 attempt（包含其内部所有重试/工具/记忆整理），不是一个子调用：

| 字段 | 内容 |
|---|---|
| `candidate_id`, `scenario_id`, `language`, `network_id`, `attempt` | 唯一 attempt 键；必须属于计划，`language=zh/en`；重复键拒绝，不选最好结果 |
| `purpose` | `tuning` / `evaluation` / `holdout`；留出场景的 tuning 观测拒绝 |
| `status` | `success` / `failure` / `timeout` / `unknown` / `missing`，原始执行标签 |
| `attempt_source`, `observed_at`, `source_as_of` | 每次尝试的来源、观测时点、来源时点（未获得须明确写 UNKNOWN，不假装已测） |
| `raw_evidence_ref` | 可核对的原始证据位置；CLI 不解引用，不检查远端证据真实性 |
| `judgment` | 可选，含 `kind=human/program/model`、`independent` 布尔值、`outcome=PASS/FAIL/UNKNOWN`、`ref`。外部独立判据必须覆盖该场景全部必需业务断言/硬不变量，不是 HTTP 成功或模型自评 |
| `serious_errors` | 可选列表；每项外部 `kind=human/program`、`ref`、`description`、`resolved` 布尔值。判定与解决情况均由外部依据声明；不自动推断严重事实错误 |
| `first_body_seconds`, `draft_seconds` | 可选非负有限秒数或 `null`；同次运行单调时钟口径由来源提供；超时/未完成时间不造值 |
| `cost` | 可选对象，`complete` 布尔值和 `components` 数组；每项 `name`, `amount`（十进制字符串或 `null`）, `currency`, `source`。须包括整任务所有模型/工具/重试/记忆整理与适用后台分摊；完整零费用也需有依据的显式 `"0"` 项 |

候选版本通过 `candidate_id` 绑定；如记录额外含 `commit/config_version/model_version`，必须与候选定义一致。额外输入字段（例如 `tool_observations`、设备、人工分歧、分摊规则、timeout 原因）原样保留。工具响应/限额/授权真实证据仍需外部采集；CLI 不产生这些证据。

## 汇总语义与限制

计划矩阵为 `候选 × 场景 × zh/en × 网络 × 计划 attempts`。缺记录生成显式 `UNRUN` 槽位。增加候选/网络/尝试前须由样本计划明确其适用矩阵；不能用本工具后验删除失败/不可执行场景。不同候选不混算，中英独立，网络/证据层/任务类别/调优与留出独立。新修复版本另有候选 ID；重复使用记录列在 `repeated_uses`，跨候选也可见，但**无法发现未提供的历史或判断曾看过结果是否影响调优**。

- `success` 标签单独只得 `UNKNOWN`。只有提供原始证据引用、独立人工/程序 PASS 判据且执行 success，才计该证据层的记录 PASS。模型判据不认证事实/状态，也不认证产品成功。声明不是证据真实性验证：真实放行前仍须独立核对原文、来源、持久化状态与判据充分性。
- `failure` 保留为 FAIL；外部独立 FAIL 或未解决严重错误也计 FAIL。`timeout/unknown` 保留 UNKNOWN（外部独立 FAIL 则 FAIL），因为本轮未批准超时判定界限。`missing` 与缺记录为 UNRUN。不适用项本轮不排除；若未来需要须带事前依据另行扩展，不能默默删分母。
- 每格计划数 N、P/F/U/R 满足 `N=P+F+U+R`；已启动 `A=P+F+U`。通过率 `P/A`、失败率 `F/A`、未知率 `U/A`、保守未通过率 `(F+U)/A`、覆盖率 `A/N` 均附分子分母；零分母为 `null`。独立场景数和 attempt 数分别报告。重试不会增加独立场景数。
- 严重错误按候选/语言/网络/集合各自列出，且全局保留原记录；未解决项列为放行阻断，不能由均分或另一语言抵消。
- 延迟对所有有值的样本取最近秩 p50/p95、max，同时给实际 n、计划 n、未知/缺失数，状态与全部 attempt 同格保留。超时/未知不从质量分母删除；此条件分位数不能用来声称整组达标。
- 金额字符串的离线输入范围：最多 256 个字符、Decimal 系数最多 100 位、表示指数 -100..100、调整指数不超过 100，且有限非负；这些仅是解析/资源边界，不是已批准的费用预算或计费精度。超范围整批返回结构化 FAIL/UNKNOWN、exit 2，原记录保留，不截断、不钳位、不改成零。已接受金额按对齐位数与项数设置独立 Decimal context，精确求和、不按分币舍入；Decimal 异常也返回结构化错误。
- 费用按币种给**已知小计**；不做汇率转换、不把未知当零。完整性须显式 `complete=true` 且所有 component 金额已知；缺观测/缺 cost/未知 component 均计未知 attempt，报告样本分母，原始每任务 component 保留供核对。外部漏报费用无法自动发现。
- `release_decision` 永远只有 `UNRUN/UNKNOWN`：全未运行是 UNRUN，有执行记录则 UNKNOWN。批准阈值字段原样保留也不授予本离线管道放行权；H/I、真实模型/工具/目标网络、权限/限额/可用范围、人工事实/状态核对、最终批准样本/阈值及费用仍未完成。本轮不关 Issue，不 push/merge，不代替 Review/Testing。

## 本轮实际验证（2026-10-23）

- Python 3.9.6：上述 unittest 命令 **20/20 synthetic tests PASS**，原始输出见 `evidence/synthetic-tests.txt`。
- CLI 按 fixture 文件实际执行，stdout 原样保存为 `evidence/synthetic-cli-report.json`：3 个独立 synthetic 产品场景、1 个留出（1/3）、6 个计划双语 attempt、1 个观测、5 个 UNRUN，`validation=PASS`、`release_decision=UNKNOWN`。
- `git diff --cached --check` 为本地差异检查。独立 Review、独立 Testing、CI、真实模型/API/DB/设备/目标网络、产品 H/I 和发布全部 **UNRUN**；最终样本与阈值批准 **UNKNOWN/pending**。


### 原 P3 输入健壮性定向返修

返修基线 `2c0dffb37a9c5ee4c91560dbaff58534884343f1`。原 `evidence/synthetic-tests.txt`（作者 20 PASS）与原 CLI 报告保持不变；独立 Testing 的 20+4 及原复现日志仍在 `cj-testing/CJ-028-offline-evaluation/`，本返修未改其记录或自称重跑独立检查。

- `tests/test_input_boundaries.py` 在修前实际复现 schema `true/1.0` 被接受、`1e1000000` exit 1/空 stdout/traceback，以及默认 28 位精度静默舍入。见 `evidence/input-boundaries-before.txt`（3 tests，4 assertions FAIL；仅去除行尾空格，错误内容完整保留）。
- 根因是只比较版本值、只验证 Decimal 有限性、依赖默认求和 context；分别修为严格整数版本、有界金额输入及独立精确求和 context/DecimalException 结构化兜底。
- 初始三项修后输出见 `evidence/input-boundaries-after.txt`；完整受影响回归见 `evidence/input-boundaries-full-regression.txt`：Python 3.9.6，原 20 + 新增 6 = **26/26 synthetic tests PASS**。新增覆盖金额范围端点/越界、长有效位精确和、外部低精度 context、失败/未知费用原样保留、Decimal 异常兜底。
- 真实费用、用户阈值、目标网络、原 H/I 仍未验；新 head 的独立双门待外部差额复验，无 push/merge/关票。
