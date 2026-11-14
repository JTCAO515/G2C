# M4 固定66真实评测

**质量 FAIL，不放行。** 首有效正文 p95 为中文17.469427秒、英文18.497360秒，均超过5秒。固定33对、11留出共66例已全部执行。中文33/33原RUN完整，英文31/33完整，两条原RUN UNKNOWN 保留。

## 范围与前置

- 正式阶段 `hk-body-correction-full-001`，C `9215f745b54872f1f2b5673074056068b18d1403`，B `6809804d23021942702f09640062b2277c20f811`，manifest `63471bcccfb82f7a7a5e1f01719a95b93e184da470e246b225675032e2e91bab`，adapter `acbc62427ee95199cb6b4c6ddd7aa26b787c6831c943f7073729e9147b1f975e`。原私有PG、签名 API 与原 worker，真实北京 DashScope 和已授权工具。正式环境为香港私有PG，目标客户端网络另记。
- JT 批准单次接续原 e3 正文误报。原 FAIL 封印原样保留，五份原实证只读复用。仅补原未启动英文 FACT，新 RUN `c5c66710-b586-40ee-96a8-03d3970ff3ec` PASS，原两个模型和一个 FACT 均 RECEIVED。六格通过当前 canonical 接续检查后启动原66。 [JT批准](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6702591531) · [PR619](https://github.com/JTCAO515/G2C/pull/619)
- 原样本 SHA 在 `formal-audit.json` 和机器报告中固定，每条原问题 SHA 按语言复核，正式每格一次。22个留出格均原RUN完整；全部独立任务与事实/语义仍需人工证据。原 wrapper195／runner201，完整批耗时590.412秒，exit1。终态只剩sleep，无评测Python／PG，无预算停机。

## 中英正式门槛

| 语言 | 原 RUN 完整 | 独立任务 PASS／FAIL／UNKNOWN／UNRUN | 完成率≥90%门槛 | 严重错误0门槛 | 首正文 p95≤5秒 | 完整正文 p95≤90秒 |
|---|---:|---|---|---|---|---|
| 中文 | 33/33，100% | 0／0／33／0 | FAIL，已证明任务通过0/33 | UNKNOWN | FAIL，17.469427秒，n=33 | PASS，17.469427秒，n=33 |
| 英文 | 31/33，93.94% | 0／2／31／0 | FAIL，已证明任务通过0/33 | UNKNOWN | FAIL，18.497360秒，n=31 | UNKNOWN，已知子集18.497360秒，n=31 |

原RUN完整率记录实际交付。任务门槛使用已证明任务通过数，人工事实/语言尚未判定，所有完整回答保留 UNKNOWN。程序已确认严重错误0，人工已审0/66，中英各4格硬证据 UNKNOWN。严重错误门槛保持 UNKNOWN。

中文19条、英文16条已知首正文超过5秒，两个语言首正文门槛均实测失败。英文两条 UNKNOWN 没有完整回答时钟。完整正文已知子集 p95 不能代替全样本门槛。`machine-assessment.*` 使用 JT 批准的 `JT-2026-11-06-M4-NETWORK` 元数据对原 plan/观察只读重算，`formal-audit.json` 保留原 plan/报告 SHA。

## 两条原失败

| 英文场景 | 原 RUN／模型 attempt | 原故障 | 原时钟 |
|---|---|---|---|
| slow-pace | `b23b19ca-9aa7-4dc9-a3e7-3d801a785acf`／`38bb082019fb483ebf1fc6f2ddbd66d6` INTENT | `model.tool_turn.1`，HTTP200，`incomplete_finish/length`，参数1721字符，197字符部分可见 | 25.341595秒仅终态 |
| memory-explicit-experience | `ea872612-b078-49d3-98e5-bbe665c79de3`／`66ccebbd9e8f42ec853c4e5f3b69c7fb` INTENT | `model.tool_turn.0`，HTTP200/done/usage/stop，`native_json_invalid`，参数171字符，正文0 | 2.675072秒仅终态 |

预期为原模型回执完成并交付同RUN完整正文。上述分别是长度触顶与非法 JSON 两类实际故障。原值、两条意图的 tokens 与实付保持 UNKNOWN。 [已交 B](https://github.com/JTCAO515/G2C/issues/523#issuecomment-6703077790)

## 用量与费用

| 范围 | 保守占用 | 公开单价 token 估算 | 实付 |
|---|---|---|---|
| 新补英文FACT | 模型¥2、付费工具¥0，2模型和1FACT均RECEIVED | 2115入/525出，¥0.0031095 | UNKNOWN |
| 正式中文33 | 模型¥53、工具¥8；模型53R、地点4/路线3/天气1R | 75398入/9910出，¥0.0870754 | UNKNOWN |
| 正式英文33 | 模型¥56、工具¥18；模型54R/2I、地点13/路线1/天气4R | 已知86436入/11464出，小计¥0.1001016，另2意图UNKNOWN | UNKNOWN |
| 正式66合计 | 模型¥109、工具¥26，共135原记录，107模型R/2I及26工具R | 已知161834入/21374出，共183208 tokens，小计¥0.187177，整段估价UNKNOWN | UNKNOWN |

正式66从 ADOPTED429／69I／360R `27188245…` 开始，原429行逐字段保留，结束564／71I／493R `119d38b6380a7050147dabc1e6578603ea0a5d4f26d2e7fd1c9d54cf4a987fe9`。原135条均归属各例，无孤立新增记录。终点含M1保守模型¥392／付费工具¥168。原五格用量保留于e3历史报告，费用不重复归入本次新阶段。全部原 attempt ID、输入SHA及回执/INTENT见 `cost-attempts.json`。

原接续归档 SHA `fac1cfd20f9277c011f9471917e06d39882634619caab0bae5a90a82d1cda24a`。原正式归档 SHA `7fbdb19ff33eab9329af400e8de3b2854545d6a483f937e11835f7720e40b4ff`。原HTTP、进程日志和压缩包保留于私有归档，`evidence.json` 保存文件摘要。`review.*` 提供逐例问题、原回答、实际工具结果和待核项，交JT独立审阅。

## 目标客户端网络

境内 Mac＋VPN 实际提交同一组中英 FACT，各唯一 POST。中文首有效/完整221.729209秒，英文219.434408秒，两个样本均超过5秒及90秒。计时从客户端原提交开始，含实际读取间隔。详见 `target-network.md` 与 `target-network.json`。这组样本与固定66分列；机器报告中的固定66目标网络列不承接这两个样本的分母。整体放行结论为 FAIL，#541/#32 保持 OPEN。

本轮自426行锚起的 C 新用量为补英文FACT、正式66和目标组共144条记录：115模型（113R／2I）、26付费工具R、3 FACT R。保守新增模型¥115／工具¥26。已知170959入／23004出 tokens，合计公开单价小计¥0.198878；两条原模型INTENT导致整段估价 UNKNOWN，实付 UNKNOWN。终锚570／71I／499R、ADOPTED `1ea19dfa75abcfa7cbc884bb263f4d0ebfea879f8df4a9fb3a9e245bc24011e6`，含M1保守396／168。各原阶段、全部原 UNKNOWN 和账本身份均保留。
