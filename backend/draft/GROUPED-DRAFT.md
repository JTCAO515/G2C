# #896 多天草稿分组格式

JT build30 的原失败保留：原草稿流 finish_reason=length，2444 chars、done=false、
usage=false；原 vendor partial/wire 未留，不能捏造 token 数。当前 serializer 对原输入
在 AuthorizationBudget.begin 前截停探针得到 max_tokens=1024，不是原 vendor wire。
该同 CID 原输入还带旧窗口的锁定 Trip；不能把它当成允许跨窗覆盖的保存正例。

## 新内部模型版本

仅新增 draft 模型响应格式，不改已保存 Trip 或旧冻结版本。显式 opt-in 类：

- `cj_draft.grouped_plan.LioGroupedPlanPublisher`：与旧 LioSourceWindowPublisher 相同构造参数；
  首版 TRIP-lio-first-plan.2、重规划 TRIP-lio-replan-delta.4，日期为 ISO 字符串。
- `LioGroupedCalendarPublisher`：与 LioCalendarPublisher 相同构造参数；
  首版 TRIP-lio-day-plan.2、重规划 TRIP-lio-day-delta.2，日期位置改为正整数天序。

首版恰为 version/title/days；重规划恰为 version/days。例：

```json
{"version":"TRIP-lio-first-plan.2","title":"北京四天","days":[["2026-11-17",[["a","故宫","09:00","11:00",["self"]],["b","景山公园","14:00","16:00",["self"]]]]]}
```

每一天只写一次日期/天序。每行恰为 id、完整地点名、起止本地时间、显式 subjects；
不输出自然语言解释、重复字段名和 Observation。时区从当前真实 NEEDS 的已知
destination_timezone 展开，缺失时拒绝，不默认北京/上海时区；参与者仍由模型显式声明，
不从 party_size 推断，不据此把意图变成已证实的参与/预订。

服务器仅展开格式，随后仍用原 schema/source/时间/固定项/选区、实际来源租约、
签名与唯一 act。重规划原条目、标题、来源、顺序及锁定项保留；模型不能回传它们的 ID。
非法、重复、额外字段、坏时间和截断 JSON 都整份拒绝，不修补、不截取部分保存。
日期/天序范围仍按原来源/窗口检查；请求的每个时段仍须完整，不靠少排天数或缩短名称省预算。

## L 部署接线

C PR 仅新增 draft 文件，旧 lio_plan.py、旧提示词、provider/worker、输出上限与 C0
派生均未改变；本类尚未从当前正式入口启用。L 在自己的 factory 显式换类，保持原 signer/
original_needs/check_lio_original。新文件与**实际新提示词**须由 E/B 在对应新配置的
source/policy manifest、qualification、collector 中捕获，不把旧 C0 的 initial/replan 哈希
冒充新策略，也不跨 purpose 把未合 C 源混入其他在途 PR。

先交付/部署已有批准候选不受此准备阻塞；C 合并后交 L 排入合法部署。4–5天中英
首版/同窗重规划的合成回归只证明 C 的展开与保护；真实供应商是否按预算完整返回，
仍须实际新部署和新阶段全国16验证。旧失败/INTENT、原账与费用未知保持。

JT31 的另一条原件为新 CID、current_trip=null、原 NEEDS fixed_items=[]、已知三人，
before 字段已由 B 按 complete=True 验证合法；日志仅指向重建后的 candidate 校验失败。
原供应商回复未留，具体候选字段仍 UNKNOWN。本模块对“合法空数组 + 显式 party”补正例，
对非法 subjects 继续拒绝；这不是证明原31已修，也不以 before 空数组解释 candidate 错误。
