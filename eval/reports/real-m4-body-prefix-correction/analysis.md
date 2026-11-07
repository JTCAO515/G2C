# C 正文识别误报与原证据重验

原阶段 `hk-compact-e3b36c39-smoke-001` 记录 4 PASS、中文 FACT 前置 FAIL、英文 FACT UNRUN。中文 FACT 的原 RUN 实际 completed，指定官方来源、后续模型与同 RUN 完整正文均有完整回执。C 的 `body_available` 按前缀排除整行，把以“来源：国家移民管理局官方英文页面……”开头的实际回答一并删除，导致误报。

修复只排除主机插入的独立来源 URL 行。正文段落可以使用“来源：”或“Source: ”开头。新增用例同时覆盖纯链接与空白、正文首字时钟、FACT 原回执缺失，以及原 FAIL 凭证继续拒绝全量准入。

## 原运行与实际证据

- 评测器 `e3b36c39b637f564a369e91ca559bcf4d64c0f79`，B 生产 `6809804d23021942702f09640062b2277c20f811`。manifest `da0c06b8317e9e416eb24d3dbc974979fdc64d33ef128c46a051bb1035af4663`，四源 adapter `acbc62427ee95199cb6b4c6ddd7aa26b787c6831c943f7073729e9147b1f975e`。原640项源码、两项0600身份、账本与控制直挂的预检均通过。正式入口依据见 [B交接](https://github.com/JTCAO515/G2C/issues/523#issuecomment-6702433556)。
- 中文 FACT 原 RUN `f016657e-e2c1-45e3-992b-ab26c8173c9e`，message `m4-synthetic-r2-smoke-fact-zh-task`，generation `6fd7ff40c7c64a9b8ec698581eac489b`。原问题要求按官方 NIA 页面实际摘录说明来源，将资格和日期适用性保留 UNKNOWN。
- 该格两个北京模型和一个 FACT 调用全部 RECEIVED。真实页面27101字节，原文 SHA `3cdf421c58c3fa2f79794d3fc3aa9f122e994cc78dba5206b58f15583615ce3b`。后续模型输入保留官方原摘录与准确 wrapper ID。最后快照为同 RUN completed／complete，text 与 `raw.answer` 逐字一致，共641字符。
- 实际回答先有独立来源 URL 行，随后是以“来源：国家移民管理局官方英文页面……”开头的完整摘录段及 UNKNOWN 说明。原失败原因只有 `same_RUN_complete_body_not_delivered`。原 `fact-zh.json` SHA `ca807d7fd574e37b3c8c01b5549eac01b2eaf2501dc260e255e1d852f4db4e84`。

## 独立程序只读重验

`checker-audit.json` 以封存的五份原 raw、原 plan 和真实423行账本快照重验。输入、每条原注册 wire hash、工具结果 SHA、wrapper／聚合回执、owner／写入状态要求均经原程序复核。此过程只读取原件，产生5个通路 PASS 和1个英文 FACT UNRUN。语义与事实的人工审阅仍 UNKNOWN。

| 场景 | 语言 | 原前置判定 | 只读修正判定 | 原快照首正文秒 |
|---|---|---|---|---:|
| 地点＋路线 | zh | PASS | PASS | 14.408294 |
| 地点＋路线 | en | PASS | PASS | 14.793808 |
| 天气 | zh | PASS | PASS | 6.100842 |
| 天气 | en | PASS | PASS | 7.509016 |
| FACT | zh | FAIL | PASS | 10.933814 |
| FACT | en | UNRUN | UNRUN | 缺失 |

中文 FACT 原首正文字段为 null。修正值取原 `events[].client_seconds` 中第一份有实际正文的同 RUN 快照，并保留原字段及事件时钟依据。它和其他四个成功样本的首字均超过5秒。本表只记录实际已执行的冒烟样本，正式中英各33例的四项指标仍 UNRUN。

原 `report.*`、`progress.*` 逐字取自本候选原生成器和持续记录。原 canonical smoke/result 的 FAIL、原候选与输出路径都保留在 `evidence.json`。修复后的测试确认原 FAIL 凭证仍阻止全量启动。当前没有全量 claim，原 wrapper19／runner25正常exit1，实际只剩 sleep。原归档 SHA `bff21225d23fb74c754d278a16d8e6d9ffd67aea6499945ee48d0b31d3146b5c`。

## 成本与下一步边界

本段新增21条原记录，12模型、4地点、2路线、2天气、1 FACT，全部 RECEIVED。19126入／2792出 tokens，完整模型单价估算 ¥0.0228392。保守新增模型 ¥12／付费工具 ¥8，实际账单 UNKNOWN。

原402行逐字段保留。阶段终点423行、69 INTENT、354 RECEIVED，ADOPTED `94395e7971b86f92beeb88f35b7f17111a0e149928c787e312f1c9d4077e5236`，含M1保守模型279／工具142。后续共享调用需另外按实时锚核对。

| 条件方案 | 该历史终点后的模型／工具预测 | 约束 |
|---|---|---|
| 新六格＋原66 | 432／204 | 工具总200不足4，预检拒绝 |
| 复用已执行5格、仅补英文FACT＋原66 | 418／196 | 需先明确原FAIL封印与候选pin的合法接续规则 |

当前 `real_phase.py` 与 README 规定同adapter仅一次原子阶段认领，C提交和runner改动不能解锁原FAIL。修复PR只交正文识别和原证据审计。追加接续规则须先审定，原已派发动作全部保留，英文FACT和固定66保持UNRUN。预算停点及本线误判已记 [#495](https://github.com/JTCAO515/G2C/issues/495#issuecomment-6702488879)。

`review.*` 提供五条实际回答及原工具结果，交JT逐条事实／语言／严重错误审阅。境内Mac＋VPN客户端POST计时保持UNRUN，#541/#32 OPEN。
