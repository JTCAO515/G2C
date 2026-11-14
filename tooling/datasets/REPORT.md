# #768 合成接口质检

环境：Python 3.14.7，仓库 uv.lock，全部离线。输入为 `samples.v1.jsonl` 与
`negative.v1.jsonl`，来源均是本轮手写合成对话或确定性本地 PLACE parser。
转换实现和数据摘要见 `manifest.v1.json`；最终精确 head、CI、C/D/R 审查和合并
证据以 #768 的 PR 为准，不用本报告代替独立结论。

| 验收框 | 本地状态 | 证据 / 限制 |
|---|---|---|
| L0 单一 schema、消息/调用/实际结果/动作/来源/版本 | PASS | schema.v1.json + 原 B/C codec；22 条原消息与结果字符串往返不变 |
| L1 完整任务分组、旅行/中英不跨组、重复转换 | PASS | 11 旅行家族、22 样本；train 18 / validation 2 / test 2；传递关联、跨旅行重复、冲突 ID、重排和双次输出摘要检查 |
| L1 五类行为及坏格式/错回执拒绝 | PASS | 直接答/澄清/改口/取消/工具失败；补空结果、结果未知、部分批次已收到但模型不可见；17 负例全部拒绝、来源与原因保留 |
| L0 版本化 manifest 与独立检查 | PASS / UNRUN | manifest 本地重复生成 PASS；独立 C/D/R 的最终结果记录在固定 head PR 评论，本文不自授独立通过 |

命令：`uv run --locked python -B -m unittest tooling.datasets.test_convert -v`，
16/16 PASS。`python3 -B scripts/handoff.py check` PASS，`git diff --check` PASS。
正常转换退出 0，负例转换按设计退出 2、0 接受 / 17 拒绝。JSON 逐项结果见
重建输出的 `quality.json`、`rejected.json` 与 `lineage.json`。

负例包括未知字段、坏 JSON/重复 key、错 call/attempt/RUN/op、失败伪报完成、
实际结果与模型可见结果不符、错误参数/工具摘要、unknown 被写成空串、未校验教师
与真实用户来源。单测另核领域异常不得中断整批、source 原 op 不符、B supplier ID
规范、取消/未知不补答，以及收到前项但后项未知的真实 B 批次形状。

拆分覆盖：逐条任务/旅行/改写标识先连接，再用 exact-content 连接，随后固定 seed
分用途，最后去重。去重控制保留两条来源、仅输出一条；发布小样本身无重复。
本轮未引入语义改写检测模型；生产者错标旅行家族、自由文本事实仍须独立核查。

保留检查：原领域参数/结果 codec、原 ID/版本/查询/回执关联、严格 JSON、任务级
组隔离与未知状态全部在外部数据边界执行。删除检查：无。删除测试：无。
没有更改生产后端、冻结契约、训练器、CI、权限或最终验收题。

以下均不从小样 PASS 推导：B #762 完整采集及多 RUN 执行任务接口 UNKNOWN；
weather/FACT/Lio 成功结果导出 UNKNOWN；正式训练集语义质量 UNKNOWN；真实用户
日志、真实模型/工具调用、GPU、教师批量生成、tokenization/loss mask、训练、
模型质量、真实服务/真机与最终验收 UNRUN。资源费用为 0。

独立审查发现并修复：批次终止后仍执行后项、Python bool/int 相等导致可见结果类型失真、孤立代理字符中断拒绝报告、非 completed RUN 与完成答案混淆。定向回归覆盖原复现；历史旧 head 未批准。默认 CI 未登记该目录为 P2 后续项，当前由独立质检显式实跑，未越权改共享入口。
