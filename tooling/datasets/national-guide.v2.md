# 全国合成数据 v2 · F #789 / D #788

数据版本 `G2C-national-synthetic.2`、候选 `F789-national-fake.2`、脚本来源
`F-national-public-scripts.2`、交接包 `G2C-teacher-handoff.2`。
行格式继续唯一 `G2C-dataset.1`。旧v1语料、行schema、转换器、G的固定输入与旧
Fake快照均保留；旧包按其冻结代码提交复建，不能用最新代码hash替代历史来源。
本次发布的是**公开合成工程语料版本**，不是正式教师训练集。`national-data-manifest.v2.json`
固定新种子、覆盖、Fake交接快照及来源摘要；正式教师质量/数据放行仍由D/R另验。

## 输入与范围

上海、成都、西安、杭州、广州、桂林，并补重庆、深圳。每城覆盖直接咨询、必要
澄清、改口、取消、工具失败，中英各有两种表达。每城另有中英原RUN取消前禁止
派发控制。共176条、40个旅行家族、48个完整任务ID；同任务的语言/改写使用相同
task/trip/rewrite标识，原F连接家族后拆分，不能将同旅改写散到其他用途。

这些是独立手写合成情境。C的 `eval/lio_national_cases.v1.json` 明确为公开验收
而非最终留出；本轮只读其覆盖/澄清/保留已知信息/日期来源/修改保护要求。
不复制其题句、酒店固定时段、地点替换列表或期望答案，不作为生成输入。
新咨询与讨论均不宣称保存或预订，不调用Trip/Memory写工具。

工具失败使用用户明确给出的 `SYNTH_NATIONAL_V2_*` 假ID，调用原 `place_detail`
结构；该工具在当前B的TOOLS与NATIONAL_TOOLS中逐字相同，无city参数。
原F/C入参、op/RUN/attempt与失败状态校验照旧，不把上海等替换成北京来过检查。
本版不声称已支持全国place_search成功结果、天气/FACT、Lio投影或多执行RUN；
这些真实接口及teacher来源准入继续UNRUN。仅城市行为/原状态合成覆盖通过。

## 生成与交接

```sh
uv sync --locked
uv run --locked python -B -m tooling.datasets.national --write-seeds
uv run --locked python -B -m tooling.datasets.national \
  --batch-id f789-national-v2 --output .local/f789-national-v2
uv run --locked python -B -m unittest tooling.datasets.test_national -v
```

`national-seeds.v2.jsonl` 是Fake脚本夹具，含手写assistant示例及合成故障，不能当成
真实教师的带答案prompt或经D批准训练集。独立 `national-inputs.v2.json` 只含用户
轮次/城市/语言/家族，不携带助手答案、期望状态或质量标签；它也不是B已批准的
真实教师任务白名单。禁止从D验证/受控最终题拼教师任务。

复用原Fake执行/原F严格JSON、原C请求codec、分组与去重入口；未复制一套行标准。
producer profile只为来源版本和source hash传参，legacy默认仍是旧脚本/旧格式。
全国输出不假标为旧F768 prompt。旧核心13文件含义保留，新包另加已hash四个文件：

| 文件 | 边界 |
|---|---|
| national-catalog.v2.json | 城市/行为/任务/旅行/改写/语言索引及公开夹具摘要，不含期望回复或质量分 |
| national-inputs.v2.json | 仅合成用户轮次，NOT authorized for real teacher |
| national-coverage.v2.json | 每城市×语言×行为分母、家族数、共享工具范围，实际质量/发布/训练UNRUN |
| national-reference.v2.json | C公开验收文件hash与coverage-only用途；不复制题/答案 |

handoff包含新版本、所有artifact hash/bytes、原及新增source hash、计划/实际/接受/
拒绝/重复分母和完整家族组表。D本轮已明确旧v1 checker不自动消费全国v2；
新包要由D另冻结manifest/source pin并显式支持，不能伪装成旧13文件、旧candidate
或旧prompt，也不能放宽旧包检查。F不选D的抽检seed、不生成D PASS。

## D规则及分层状态

首个真实批次完整家族100%独立检查，扩批至少ceil20%家族且语言×行为至少一个，
小层不足全检。家族包括所有任务、语言、派生/改写及原attempt链；数量是实际分母，
不能截断/删派生凑20。F假设的20条首批规模不作为自动生成或截取指令。
所有结构/来源/hash/实际工具关联/用途/已知坏例自动100%。接受集中一项硬错或
语义/事实错误、任何未核UNKNOWN都不发布，修后新版本，不能只修抽中行。

工具outcome、RUN终态、answer_state和处理判定分别记录；用户取消后的正常确认
为completed，原RUN取消为cancelled/not_started。failed无结果不改空列表，UNKNOWN
不补完成答案。旧正负控中的received部分原件/partial正文与如实解释no_results继续保留。
同一固定提交/输入/batch的包逐字可重建，已有输出目录拒绝覆盖。

全部新数据明确synthetic/Fake，`quality_status`、发布和训练均UNRUN，真实请求0。
首批¥5用途已批准；仍须B交实时F费用子额、可用宿主/运行pin/原账/窗口及真实输入
和teacher准入后，才能真实小批并交D。源模块合并或本轮全国覆盖PASS均不代这些资格。
