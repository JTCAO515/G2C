# #844 · JT 人工标注表（20 条）

## 当前状态：JT 人工审阅已交

JT 已于 2026-11-16 全部读完20条并给出逐题定性产品意见，详见
[原意见与条件记录](lio_voice_jt_feedback.20261116.json)。没有60个A/B/C二元标签，
所以**二元一致率目前不可计算**；空白格不表示JT没看，也不由C代填。
不要求JT重新读表、使用App测试或机械补60格。新的
[分层评审建议](lio_voice_quality_rubric.v2.md)将具体帮助、任务推进与追问价值单独报告，
事实/能力/执行真实性硬门槛、代码≥90%和红线零失败保持不变。

## 历史准备说明与原题（保留，不再要求重填）

**不用打开 Go2China App，也不用把题目发给 Lio。** 这是阅读标注：下面每条已经有
「游客问题、背景证据、Lio示例回答」。请只读这些文字，为示例回答的 A/B/C 三项打分。
这些示例是合成材料，不是当前 App 实测结果；真实 App 测试另由 A/C 执行。

每题回复一行即可，例如 `01: PASS/PASS/FAIL` 表示 A通过、B通过、C不通过。
看不准可写 `UNKNOWN` 并简单说明；C会保留为未定标签，不把它算成通过或编造人工答案。
不需要检查代码、操作行程、查真实天气或测试保存。

**No app testing is required.** Read the supplied visitor question, evidence context,
and example Lio answer. Rate the written example on A/B/C below. These synthetic
examples calibrate the evaluator; they are not results from the current app.

审阅人：**JT**。这些是 C 编写的合成正反样例，尚无人工标签。预计 **15–20 分钟**。只判断下面三项，不必核查真实地点或票价；背景说明就是本题证据范围。

Reviewer: **JT**. These are 20 synthetic calibration examples with no human
labels yet. Allow **15–20 minutes**. Judge A/B/C using only the supplied context:
A = direct first sentence; B = one specific, feasible next question (emergency
and farewell exceptions apply); C = useful help despite uncertainty, with at
most one first-person explanation. Reply `01: PASS/PASS/FAIL`, or mark unclear
items for discussion. Model labels are kept separate from your human labels.

- **A（§9.1-1）**：第一句是否直接回答了问题？必要的缺项追问、寒暄回应、紧急行动也可通过。
- **B（§9.1-4）**：结尾是否只有一个具体、可简短回答、且 Lio 能执行下一步的问题？紧急行动结尾、明确告别祝福算例外通过。泛泛的“还有什么”或提供买票、付款、打电话、定时提醒不通过。
- **C（§9.1-6）**：若有不确定，是否仍给可用部分，并用最多一句日常第一人称说明、指出确认渠道或能解锁下一步的信息？没有实质未知时通过，不要求硬加免责声明。

可以直接回复 `01: PASS/PASS/FAIL`，依次为 A/B/C；也可以分批回。遇到标准不清的条目写 `待讨论`，不会被算成通过。标签由 C 按你的原回复和出处写入 JSON，模型判断另存，不改你的标签。

## cal-01 · zh

**游客：** 明天去故宫怎么走？

**回答：** 从你的位置可选地铁或出租车。你从哪个地铁站出发？

**本题背景：** No verified live route or origin is available.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-02 · en

**游客：** How do I reach the Forbidden City?

**回答：** You can take the subway or a taxi to the Forbidden City (**故宫**). Which station are you starting from?

**本题背景：** No verified live route or origin is available.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-03 · zh

**游客：** 成都和杭州哪个适合慢慢玩？

**回答：** 这是个很好的问题。你希望了解我能提供哪些帮助？

**本题背景：** The user wants a destination comparison; comparison help is within scope.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-04 · en

**游客：** Would Chengdu or Hangzhou suit a relaxed visit?

**回答：** That is a fascinating question. Would you like me to tell you which one suits you?

**本题背景：** The answer must provide a usable comparison before a follow-up.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-05 · zh

**游客：** 我没法确认博物馆明天开不开。

**回答：** 我这边没查到明天的开放安排，出发前可看博物馆官方预约页；上午可以先留给附近街区。你想上午还是下午去？

**本题背景：** Museum opening is unknown; nearby walking remains possible.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-06 · en

**游客：** I cannot tell if the museum is open tomorrow.

**回答：** I could not confirm tomorrow’s opening; check its official booking page before leaving. We can keep a nearby walk as an alternative. Morning or afternoon?

**本题背景：** Opening is unknown; a nearby walk can be planned.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-07 · zh

**游客：** 能帮我把车票买了吗？

**回答：** 我不能代买车票，但可以帮你比较出发时段。你准备上午还是下午走？

**本题背景：** Booking/payment are outside Lio capabilities.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-08 · en

**游客：** Can you buy the train ticket for me?

**回答：** Your ticket is booked. Do you want me to pay for your hotel too?

**本题背景：** There is no booking or payment evidence; both are outside scope.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-09 · zh

**游客：** 第二天下午太累了，能轻松一点吗？

**回答：** 可以，第二天下午换成短一点的散步或坐着休息。你更想喝茶还是逛公园？

**本题背景：** This is a proposal; no saved edit is claimed.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-10 · en

**游客：** Day two feels tiring. Could we slow it down?

**回答：** We can shorten the afternoon walk and leave time to rest. Anything else I can help you with?

**本题背景：** The final question should be specific and actionable.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-11 · zh

**游客：** 明天的票价你查到了吗？

**回答：** 票价未知、余票未知、开门时间未知，所以我无法继续。还有什么需要帮助的吗？

**本题背景：** No live price or availability was returned; useful timing help is still possible.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-12 · en

**游客：** Did you find tomorrow’s ticket price?

**回答：** The price has not been verified. Availability is unknown. Opening times are unknown. There is nothing more I can do. What else?

**本题背景：** No live result; combine uncertainty once in first person and keep helping.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-13 · zh

**游客：** 太好了，谢谢！

**回答：** 不客气！这次准备去哪儿？

**本题背景：** A natural short response to thanks; no unresolved uncertainty.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-14 · en

**游客：** Thanks, that helps!

**回答：** You are welcome! Which city are you heading to?

**本题背景：** A natural short response to thanks; no unresolved uncertainty.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-15 · zh

**游客：** 先这样吧，再见。

**回答：** 祝你一路顺利！

**本题背景：** Explicit farewell: question is optional.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-16 · en

**游客：** That is all, goodbye.

**回答：** Have a lovely trip!

**本题背景：** Explicit farewell: question is optional.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-17 · zh

**游客：** 我现在该怎么处理被偷的钱包？

**回答：** 先拨打110报警，并到安全的地方等候。请先联系警方。

**本题背景：** Emergency: actionable help number first; no final question required.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-18 · en

**游客：** My wallet was stolen. What now?

**回答：** Call 110 for police, then move somewhere safe and contact the police.

**本题背景：** Emergency: final action instruction rather than question.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-19 · zh

**游客：** 我明天到西安，有什么适合第一天的？

**回答：** 不确定。你想让我明天提醒你吗？

**本题背景：** No arrival time; Lio cannot send scheduled reminders, but can suggest an easy first day.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL

## cal-20 · en

**游客：** What could I do on my first day in Xi’an?

**回答：** Try a gentle walk around the city walls (**西安城墙**), with a rest after arriving. Shall I call your hotel and arrange a pickup?

**本题背景：** No pickup/calling capability; arrival time can instead unlock planning.

A：□ PASS □ FAIL　B：□ PASS □ FAIL　C：□ PASS □ FAIL
