# F 教师管线 Part 1：Fake 到独立质检交接

F [#789](https://github.com/JTCAO515/G2C/issues/789)，配对 D
[#788](https://github.com/JTCAO515/G2C/issues/788)，父专题 #767。
本轮只实现 `tooling/datasets/**` 的 Fake 路径。真实模型/工具调用、教师数据发布与
训练均 UNRUN；不创建账户、密钥、GPU、云资源或第二份预算账本。

唯一行格式仍为原 `G2C-dataset.1`，`schema.v1.json`、`convert.py`、原样本和
原 manifest 全部不改，G 的固定输入继续有效。新 `G2C-teacher-handoff.1` 仅封装
批次文件、原件引用、版本/hash、分母和质检交接状态，不是另一套训练行 schema，
更不是 B #762 的实现或 HTTP 标准。

## 实际输入和真实前置

- Fake 输入是 #768 已公开合成脚本；FakeTeacher 只返回 assistant 提议，脚本中的
  tool 消息不进入生成轨迹。来源明确记 synthetic_fixture，模型版本为 FakeTeacher.1。
  这些脚本、坏回复和公开 test 都不是最终题，也不是供真实教师照抄的正确答案。
- FakeTools 只执行控制脚本绑定的本地 Search 收到结果夹具，以及明确的失败/取消/
  UNKNOWN 控制。实际 supplier bytes 经原 C `prepare` / `parse_response` / `encode_result`
  产生结果；不复制脚本的工具结果或旧回执。没有通用真实工具代理或默认成功结果。
- B #762 尚未交可信适配器、全任务/多执行 RUN、原件/可见投影、原身份、原计量和
  取消/UNKNOWN核对。weather/FACT/Lio成功结果仍按 #768 支持矩阵拒绝；不猜接口。
- 本版 v1 仍拒 teacher / real_user 来源。后续真实准入须在 B 实际接口上追加已审
  入口/版本及消费通知，不能把教师产物改成 synthetic，或替换 Fake 回调接付费 API。
- 新用途预算申请在 [#495](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6783714210)，
  明细见 [teacher-budget.md](teacher-budget.md)。批准、剩余额度、全轨迹计数和原账本
  子限额仍须核定，Fake 计数测试不能证明 B 的真实预算控制已经实现。

## 闭环与边界

```text
Fake任务/家族/中英脚本（F固定身份）
  -> FakeTeacher原始assistant字节（不接受教师供工具结果/用户消息/回执）
  -> 原消息schema + 原工具参数/查询校验（全部提议通过后才执行）
  -> 独立本地FakeTools实际结果 + 原call/attempt/RUN/op校验
  -> 全批工具核同后才追加模型可见投影
  -> 原F任务家族分组/用途拆分 + 去重/来源lineage
  -> 17个原坏样本 + 2个精确已知坏回复拦截回归
  -> 固定hash的handoff.json交D；quality/release/training均UNRUN
```

生成期间的模型来源状态来自 Fake 客户端控制，而非 assistant JSON。未知模型回执
即使带有完整工具提议也不派发；无效部分正文仍保留 UNKNOWN 并停止。已收前项结果、
后项未知时，前项留在实际执行证据里，不补模型可见结果。错回执不修成正确 ID，
整批停派并保留原件；尚未开始的任务为 UNRUN。已知模型失败保留 FAIL，不改 UNKNOWN。
取消在派发前保留 not_started，无工具请求。没有自动重试、换 ID、补样或 resume。

Fake请求上限为每完整轨迹模型/工具分别8次、全批分别400次，包含前序对话和工具轮；
到限停止，不把半个任务截成完成答案。它们只检验本地 Fake 驱动器，不改变任何 B
原配额或货币 hold。真实开工必须由 B 在原出口/账本证明所批子限额与全轨迹计数。

`teacher-known-bad.v1.json` 的两句伪保存是当前无写工具控制场景的**精确已知坏例**，
不是关键词裁判或通用语义判定器。其他措辞、事实、澄清质量等仍需 C/D 独立核查；
不因没有命中这两句就称正确。已知坏控未被拒绝时，整个 Fake 工作流 FAIL。

## 运行与复现

在仓库根目录执行，输出必须为不存在的新目录。运行产物及原始 Fake 过程记录
留在 `.local` 或任务临时目录，不把运行日志/秘密/真实用户数据提交 Git。

```sh
uv sync --locked
uv run --locked python -B -m unittest discover -s tooling/datasets -t . -p 'test_*.py'
uv run --locked python -B -m tooling.datasets.teacher \
  --mode fake --batch-id f789-smoke-v1 --output .local/f789-smoke
uv run --locked python -B -m tooling.datasets.teacher \
  --mode fake --control bad-receipt --output .local/f789-bad-receipt
uv run --locked python -B -m tooling.datasets.teacher \
  --mode fake --control unknown --output .local/f789-unknown
uv run --locked python -B -m tooling.datasets.teacher \
  --mode real --output .local/f789-real-unrun
```

smoke 退出0表示 Fake闭环完成：21任务、31个Fake模型调用、6个Fake工具请求；
17条格式合格候选，去重1条后保留16条，4条坏生成隔离，全部来源保留。
接受集8个家族，固定示例batch-id下 train12 / validation2 / public-test2。
独立控制为17个原负例及2个新已知伪保存回复，不能混入生成分母或算真实调用。
processing PASS 是处理/拦截正确，不是原 RUN 已成功、更不是教师数据质量通过；
失败/取消原状态仍留在行内，缺完整答案轨迹仅作控制，不能直接作完整SFT。

错回执和 UNKNOWN 控制退出2，保留 UNKNOWN/后续UNRUN，不能给 D 发布训练版。
`--mode real` 退出2/REAL_ADAPTER_NOT_DELIVERED，不构造驱动器、不创建输出目录、不调用。
它不读取或自行判定 JT 审批，不能用 CLI 布尔值把预算申请变授权。
同提交、同batch-id与同Fake输入的产物逐字一致；已有目录拒绝覆盖。

## 交 D 的固定包

`handoff.json` 含 schema/tools/原F固定源码/新Fake代码/control registry hash、代码提交、
批次 ID、artifact hash/大小、原F组表/用途及计划/实际/接受/拒绝/重复分母。
`mode=fake`、`quality_status=UNRUN`、`semantic_quality=UNKNOWN`、
`release_eligibility=fake_only_not_released`、`training_status=UNRUN` 始终明确。

| 文件 | 含义 |
|---|---|
| candidates.jsonl、train/validation/test.jsonl | 经原F边界接受的合成行；去重前候选与拆分后行分开，绝非正式教师发布 |
| planned-cases.json | 全部计划身份/家族/语言/行为和公开Fake夹具摘要；与实际任务分母分开 |
| raw-candidates.jsonl、models.jsonl、tools.jsonl | 过程原件，仅本地Fake；坏JSON保留base64原字节，实际工具原件与可见投影分离 |
| tasks.json | 全部计划任务及完整家族/语言/行为、原状态、拒绝/停止原因和实际请求数；未派发不抹零当成功 |
| lineage.json、rejected.json、known-bad.json | 每来源及去重/拒绝原因、所有坏控结果，不择优回填 |
| report.json | Fake处理/准入及独立质检/发布/训练的不同状态，失败与UNKNOWN保留 |

出处引用为 `文件名#原记录ID`，如 tools.jsonl#op-...、tasks.json#sample_id。
D冻结handoff及所有文件摘要后，独立选择完整连通家族：真实首批10家族/20轨迹人工
100%；扩批至少ceil(20%×家族数)，且每语言×行为至少1家族，小层不足全检，
选中家族的全部任务/双语/改写/原attempt链一起检查。D的seed与清单由D冻结，F不代选。
全量结构/来源/实际工具回执/用途/去重/坏控100%；接受集一项硬错、语义/事实错误或
未核UNKNOWN都不放行，修后新版本，不只修被抽中行、不换样。具体结论只由 #788
及 C/R 独立证据发布，F不生成D的PASS。

## 固定真实数据版本的条件

真实分期仍UNRUN：JT明确批准 #495 模型/数量/金额/期限，B #762 实际接口、身份、
原attempt恢复/原计量子限额和白名单任务集/版本就绪，才跑小批。初批D全检及R复核
通过后，才能在同份批准的剩余总额/原更低配额内扩大，或发布hash一致的数据版本。
未核的跨RUN、结果投影和来源不补造；不导入真实用户日志或最终题，不执行写工具。
任何数据/过滤/规则修订均重发固定版并完整交D，既有版本与分组不能混用。
正式训练仍是G后续Goal，不由本管线或Fake PASS启动。

G #785 已登记原 test_convert。当前共享入口仍只运行该模块，新增 test_teacher 尚未
进入默认调用；已通知 G 用目录 discover 覆盖旧/新套件。本PR不写共享 scripts/test.py，
新教师专项由本地及独立审查显式运行；默认 CI 绿不冒充已经执行新专项。
