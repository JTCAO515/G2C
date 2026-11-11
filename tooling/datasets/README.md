# 工具对话数据接口 v1

F [#768](https://github.com/JTCAO515/G2C/issues/768)，父专题
[#767](https://github.com/JTCAO515/G2C/issues/767)。唯一记录 schema 是
`schema.v1.json`（`G2C-dataset.1`）；语义和关联检查在 `convert.py` 的同一读入边界。
本轮只接收公开合成控制，既不执行工具/模型，也不导入真实用户日志、教师数据或最终题。
新增 Python 依赖为零，使用仓库 `uv.lock` 中的 jsonschema 4.26.0 和已有领域 codec。

## 固定输入与支持范围

基线 main `8fcf94055f367c8e55b8fa5d9b19c1f358058a1f`。
工具定义直接读取 `cj_api.real_services.TOOLS`，按其原 JSON schema 校验，再复用
`canonical_tool` 和 PLACE/FACT query codec。manifest 固定工具定义摘要及源码摘要，
不复制一套手写参数标准。导出的 `tools.json` 是该定义的快照。

| 接口 | 本轮支持 | 未交部分 |
|---|---|---|
| B STREAM@1/@2 原生消息 | 原 supplier ID、arguments 字符串、tool_call_id 和 content 原样保留；全批完成后追加可见结果 | 历史 wrapper `m4_tool_turn*` 不自动转换；模型 Meter 流完整性不从消息推断 |
| 五个 native 工具的请求 | 原 schema/领域查询校验、每 RUN 最多 8 次、重复原查询拒绝 | 不授予调用权限 |
| 非 Lio PLACE 实际结果 | 原 `PLACE-result.1` codec、原查询、op 引用、可见投影关联 | 实际原件可信性在本轮仅由确定性合成生成器建立 |
| weather/FACT 成功结果 | 明确拒绝 `result_codec_not_delivered` | 待 B/C 交可固定的 live result 导出/验证接口 |
| Lio 精简结果 | 明确拒绝完整 PLACE codec 以外的结果 | 待 B 交实际原件和模型可见投影的关联出口 |
| 动作状态 | 同一执行 RUN 的 received/failed/unknown/cancelled/not_started；保留原 attempt/run/op | #762 完整导出尚未交；多执行 RUN 的一个任务、正式写入/确认/撤销回执尚未接入 |

任务可含多轮用户澄清/改口以及执行前讨论，不能拆成独立单轮行。v1 的工具执行
必须属于该行 `run` 所指的同一 RUN，任务级 `attempt_id` 是合成采集身份。
多 RUN 执行任务须等 B 的明确关联接口，不能用最后一次 RUN 冒充整个任务。
当前接口是 F 的离线封装，不是新增生产协议，也不替代 C/B 原契约。

## 记录含义

- `sample_id` 唯一样本；`task_id` 完整任务；`trip_family` 同一旅行及派生任务；
  `rewrite_family` 翻译/改写家族。这些身份由数据生产者保留，转换器不从语言猜旅行。
  所有中英改写必须沿用家族身份；缺身份拒绝。无法识别错误标注的语义改写仍待独立质检。
- `source` 保存合成来源 ID 与修订；`versions` 固定 B 轨迹版本与工具摘要。
  合成数据没有模型/提示词/适配器版本时显式 null（未知），不伪造真实版本。
- `messages` 是 B 模型实际可见消息；不把 `executions`、回执、PASS 字段放进模型回答。
  `run` 记录最后执行状态、answer_state（none/partial/complete）及其证据引用，`executions` 记录实际工具动作和原件。
- received 只表示收到结果，不等于查询成功：`no_results`、`rate_limited` 等仍由
  原结果 outcome 表达。`result.state=unknown,value=null` 表示没有确定原结果；
  failed 必须保留错误码，不能用空结果代替。原 PLACE 的 unknown、missing、
  empty_array 与 present 值按 codec 原样保留，不将 null、[]、0 或 false 相互替换。
- 每个工具动作关联原 supplier call、任务 attempt、RUN、B 原 op
  `op-sha256(run_id + NUL + tool.round.index)`，证据字段必须一致。
  批次前项 received、后项 unknown 时，前项实际结果可存在执行证据里，但 B 消息里
  还没有任何该批工具结果。非 completed RUN 不得标注 complete 答案；原流已发布的部分正文可显式标 partial，不能补成完成回答或重放动作。
- 用户说“取消”后助手正常确认的 RUN 为 completed；真正 RUN cancelled 控制保留
  原工具提议和 not_started 证据，不添加取消之后的完成回答。

这些检查只证明结构、关联与固定 codec；模型说“已保存”不能成为保存证据。
本轮没有写工具，任何写工具名拒绝。自由文本的事实、声明含义由 C/D 独立核对，
结构接受不等于语义正确，更不等于正式训练放行。

## 转换与复现

在仓库根目录运行，输出选择一个不存在的新目录：

```sh
uv sync --locked
uv run --locked python -B -m unittest tooling.datasets.test_convert -v
uv run --locked python -B -m tooling.datasets.samples
uv run --locked python -B -m tooling.datasets \
  --input tooling/datasets/samples.v1.jsonl --output .local/dataset-v1
uv run --locked python -B -m tooling.datasets \
  --input tooling/datasets/negative.v1.jsonl --output .local/dataset-negative-v1
```

正例退出 0；负例退出 2 并写拒绝原因，不能拿“已写报告”当作全批通过。
空行、重复 JSON key、NaN、未知字段、错版本、错原件关联均拒绝。
已有输出目录拒绝覆盖。输入不改写；输出是规范化 JSONL，内部原消息字符串不变。
重建小样使用固定时间、确定性本地 PLACE parser 和合成 Response，不进行网络请求。

转换先连接 `trip_family`、`task_id`、`rewrite_family` 以及完全重复内容形成连通组，
然后以版本化 seed（默认 `G2C-dataset.1`）和组摘要哈希分配 80/10/10 用途。
这是确定性比例，不保证小语料精确配额。新增或合并家族可能改变组摘要和用途，
因此续版必须整体重发 manifest，不能将不同版本的拆分文件混用。
最后按样本 ID 排序去重，重复 supplier ID 拼写归一用于内容比较，原消息不改。
不声称执行语义去重；相同内容但不同实际原件仍可保留。冲突的 sample_id 全部拒绝，
不能按输入顺序择优。`lineage.json` 保存包括去重行在内的来源、原行 hash、保留样本、
组、用途与原因；`rejected.json` 保存拒绝原因与输入引用，不保存原用户正文。

输出 `train.jsonl`、`validation.jsonl`、`test.jsonl`、`tools.json`、
`lineage.json`、`rejected.json`、`quality.json` 和 `manifest.json`。
manifest 含输入/产物/schema/工具/转换源码 hash、Git revision、seed、组表与版本。
同一提交同一输入重跑产物逐字一致；输入重排后拆分/语料不变，原行定位有意变化。
发布的 `manifest.v1.json` 与 `quality.v1.json` 是小样参考结果；按源码 hash 核其
对应实现，Git revision 指生成时已经提交的实现，不是自引用的 manifest 提交。

## 交给 G 的消费约定

G [#773](https://github.com/JTCAO515/G2C/issues/773) 可以用这些公开合成数据验证
模板和 tokenization，不能由 `release_eligibility=synthetic_interface_only` 启动正式训练。
消费时固定 manifest/输入/schema/tools 的 hash；只使用同一 manifest 对应用途。
test 是公开工程控制，绝不是最终验收题，不能作为学生晋级证据。

后续模板只从 `messages` 取模型可见内容，system/user/tool 及实际执行结果不能作为
模型生成目标。`executions`、source、run、回执及质检判定是旁证，不是 assistant 文本。
工具请求 token 和 assistant 回答的监督 mask 必须由 G 对实际模型模板逐 token 验证。
failed/unknown/cancelled 等没有完成答案的轨迹只作为控制/拒绝样本；G 未明确并验证
模板如何处理前，不得当作普通完整 SFT 对话。具体训练格式和 loss mask 属 G，F 不另造训练器。

## 后续教师生成建议

先让 B #762 交原身份/原 Meter/工具出口的完整采集，包含原件与可见投影、取消与未知、
模型/提示词/工具/适配器版本、正式写入的确认/对象/版本/原回执；C 冻结领域解释，
D #761 固定判据。再由 Claude 拆教师生成及独立质检 Goal，明确资源与授权。
沿 B 出口少量生成，工具结果取实际执行而非教师编造；未知不得换 ID 重试。
每批先过版本、严格解码、关联、已知坏例、家族拆分和去重，再做 C 语义核对、
D 独立抽检和 R 复核；失败/未知隔离，发布固定数据版本后才交 G。
教师自己的评分、成功声明或生成完成都不是正确性证据。v1 明确拒绝 teacher 来源，
以后接入必须新增已审校验/准入，不能仅改来源标签使其通过。真实用户数据仍无默认授权。

默认 `uv run --locked python -B scripts/test.py` 已登记本目录套件并传播非零退出码；CI 的 Python 日志会显示 `tooling/datasets` 及各测试结果。原 #768 的固定 head 单跑证据保持原范围，新增默认入口证据见 #785；合成结构检查不代表正式数据或模型质量通过。
