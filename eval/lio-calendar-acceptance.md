# 无日期验收轨迹 v1 与全国期望 v2

#864，父票 #859；#861/PR879、#862/PR950 已合并。本切片只追加公开合成
recipe/断言及受影响期望，**不是已执行的轨迹或通过报告**。旧冻结输入、失败、
UNKNOWN、旧运行 ID 和版本全部保留，不改生产规则、契约或发布校验。

[六条无日期轨迹](lio_calendar_cases.v1.json)固定中英各三条，每条新对话：

| 每种语言的任务 | 版本与必须核对的结果 |
|---|---|
| 只给成都和三天 | native3 直接保存无日期 v1；日序号1–3，不造日期/人数；两个日期检查均not_checked；不要求补可选日期/人数。 |
| 修改第二天下午并撤销 | 先保存v1；用实际完整名称/时段选唯一未锁项，修改追加v2且其他项不变；原生撤销追加v3恢复v1原字节，保留v1/v2。 |
| 补相对和绝对日期 | 带明确未知酒店位置的原始固定集合保存无日期v1；“明天开始”按该原消息question_day转换为有日期v2；撤销到无日期v3；补2026-12-01生成有日期v4；再撤销为无日期v5。两次转换保留固定项、重做日期检查、表达冲突。 |

第三条在同一完整轨迹中包含两种补日期及各自撤销，因此分母仍为6条完整轨迹，
不是按消息或分支扩大分母。所有 MESSAGE 回复须以一个具体问句结尾；原生撤销
只核原动作回执/历史，不要求其收据包含助手回答。

## 长度检查停点

`docs/lio-voice.md` 在本切片所基于的已接受 main 上不存在，PR894 尚未合并。
#864指定第3.2节，故当前长度断言为 **UNRUN**，不从未合PR或其他章节自行补门槛。
本切片不能勾整项L0完成；长度检查及执行器的剩余交付随该规格合并继续，
不把静态数据/人工说明冒充运行证据，也不因此放宽问题结尾、事实或写入保护。

## 全国16条：原输入不动，新增consumer期望

[lio_national_expectations.v2.json](lio_national_expectations.v2.json)引用原
[16条输入v1](lio_national_cases.v1.json)，原SHA256仍为
`478f772d6b78817c8a88b9d48448f3f05c0bb5c0f31661ade3f6edec5fddce7f`。
它只适用于明确资格下的 **legacy2 / source-window1**：

- 成都首轮只有城市/天数：完整无日期对话预览、零正式保存，不强制追问日期。
  原第二句“从明天开始”及固定集合仍原样发送，是用户主动补充，不是日期必填的证据。
- 人数可选，未知不从“我”或Memory推断；预备的“一人”答复只在确实需要明确
  固定项参加者时使用，不在已完成保存后为凑步骤追加消息/版本。
- 上海仍须问缺失天数、重庆须问城市；Taizhou/Suzhou须核真实行政区歧义，
  不取首条、不借其他城市日期。已给出的城市/天数/日期不重复问。
- 日期、固定项及必需来源齐备后保存一次；按实际完整名称修改和原生撤销各追加一版。
  既有来源、隔离、原账、费用、时序及严重错误门槛全部保留。

**不能把这套两轮/固定酒店/v1→v2→v3流程用于native3或探索4。** native3可能在成都
首轮已保存无日期版本，此后才补日期/固定项就有另一套版本语义；须用独立轨迹和资格。
本文件不授权换消费模式，也不让缺原件结果变成PASS。

## 本轮前置发现与后续执行

r07尚未派发时，只读实际955源`9406fdea`发现legacy2已在
`local_lio_national.py`的undated分支给完整预览，且
`test_lio_national_execution.py::test_missing_party_is_optional_but_city_or_duration_remain_required`
明确人数可选。旧v1要求追问日期、旧r07要求16次人数补答，不能据此判新源产品失败。
C与B已STOP_NEW撤回r07资格，16全UNRUN、0POST；计划/租/原件留存不覆盖。

新增期望合并后，另备新阶段、新原消息/撤销ID，请B按实际源码/镜像、consumer、
collector、原身份/原C子额度及独占窗口重新签租。不得在旧helper到点显示READY时派发。
任一FAIL/UNKNOWN停止新派并保留原动作；错误按实际owner记录，未知写入只读对账。
报告中英分母/逐项结果、首进度/首正文/完成时间及保守/token估算/实付费用；
只有全国完整16条全部PASS后才申请#32六格，六格通过后另排正式66例。

## 可执行的内容与版本断言

`lio_calendar_transitions.judge_transitions`消费每步原始
`TRIP-structured-read.2`和`LIO-trip-history.3`响应，不读模型自报的成功结论。
检查canonical哈希、同一Trip和逐步新版本、实际卡片与canonical内容核同、所有原历史
版本保留、无日期/三天、固定集合、只改实际选中未锁下午项、相对和绝对日期映射，
以及撤销后完整原字节相等。相对日期只接收承载该日期的原消息的native question_day；
缺该证据为UNKNOWN，不读本地/分析时钟。原始回应和冻结recipe不被修补。

本地可执行入口：

```sh
uv run --locked python -B -m eval.lio_calendar_transitions observations.json --output checks.json
```

输入须是自有0600文件，格式`LIO-calendar-observations.1`，字段为`version`、
`case_id`、`reads`以及可选`histories`、`answers`、`question_days`、`selected_item_id`。
`reads`按recipe步骤顺序保存完整原响应；其余三个映射以字符串`0`至`4`为步骤索引。
native undo不设回答文本断言。原证据和结果都不覆盖；输出带输入SHA256，文件为0600。
这只是本地判定器，不会提交HTTP、调用模型或改变真实状态。

`transition_outcome`只表示这些内容断言；即使全部PASS，`task_outcome`仍为UNKNOWN。
真实原件资格/身份/来源、Memory零静默写入、正文日期/人数/预约语义、撤销零模型、
时序/原费用仍列在`remaining_proofs`。长度仍UNRUN，不接收手填PASS或伪造门槛。
未观察步骤为UNKNOWN，整套未跑为UNRUN；有明确内容冲突则FAIL，不能被模型评分盖过。

专项及默认入口：

```sh
uv run --locked python -B -m pytest eval/tests/test_lio_calendar_transitions.py -q
uv run --locked python -B scripts/test.py
```

默认入口新增子检查及真实非零退出传播控制；旧检查和冻结输入保留。
