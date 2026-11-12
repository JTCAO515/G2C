# #861 日历运行时接线（L #862 / A #863）

这是显式新入口，不在旧 LioSourceWindowPublisher 上删除 arrival.date 门禁。
旧 structured.1/.2、MESSAGE-send 和旧 undo 仍走原实现。无数据库迁移。

## L 的已授权宿主

`cj_draft.lio_calendar.LioCalendarPublisher(original, confirmation, original_needs,
check_lio_original, calendar_reader, date_reader)` 复用真实 MESSAGE、NEEDS、原签名器、
Trip CAS 和唯一 `_act_in_tx`。`check_lio_original` 仍必须校验原始 Lio admission，
不能以 DTO、input hash 相等或一个客户端 true 代替。

`calendar_reader.capture(binding, message_lease, needs_capture)` 返回不可变
`CalendarBasis(day_count, start_date, fixed_bindings_bytes)`。天数、日期和固定项映射来自
受保护原编译结果；没有日期就是 null，不读时钟补日期。fixed_bindings 是冻结的
LIO-fixed-day-bindings.1 原规范字节。C 核完整 NEEDS 身份/版本/hash、原消息、每个固定项覆盖。

`calendar_reader.hold(binding,basis,message_lease)` 是实际来源 context manager，
在当前 MESSAGE 后、NEEDS 前取得其余来源锁，退出时反序释放。held 对象提供：

- `check()`、`day_count`、`start_date`：当前身份、来源和受保护编译结果仍有效。
- `original(reference) -> (Stored, lio_protocol)`：真实保存的 canonical MESSAGE 原字节及
  实际外层协议；不能重编码原消息或拿外层 hash 代替。C 另核 receipt/CID/gen/MID/RUN/序号。
- `fixed_day_indices(item_id,reference,quote) -> (start_index,end_index)`：原文明确天序，
  不是模型猜测。所有历史原件也必须由实际来源 lease 保护，不在持有 NEEDS 后再申请 MESSAGE。
- 补日期时 `question_day(reference)` 返回原消息北京时间的 date；
  `compiled_date(reference,quote,question_day)` 返回原编译 ISO date 对象。C 不再次解释自然语言。
- 修改时 `selected_item_ids(reference,request_bytes)` 返回原编译实际条目 ID 元组；
  必须结合原请求、原 Trip 版本、名称或天序/时间段处理歧义，不扩展选区。

`date_reader.read(binding,capture,document)` 只读取已采集、同来源/实际版本绑定的
weather/day_opening 结果（冻结的 date_checks 形状）。不能在 C 发布锁里外呼。
无证据为 unknown；有来源的闭馆冲突保留安排并保存冲突，硬固定日期矛盾不保存。
无日期规划不调用它，直接保留 not_checked/date_not_set。

## 写入与原动作恢复

规划沿 `publish_for_message`，无日期新计划用 TRIP-lio-day-plan.1，追加建议用
TRIP-lio-day-delta.1。模型只能给新条目的 day_index/local time 和显式参与者列表；
服务端装配原固定项，保留全部已有条目/来源。缺人数不造默认人数。

补日期走 `convert_for_message(...,raw,capture,before_publish=...)`，raw 为冻结
TRIP-date-convert.1。相同 Trip 生成新版本，内容、锁定和来源不变。回执只能由
受保护的 `OperationContext.calendar_conversion_receipt(original_request)` 查询；
未知结果 committed=null，保留原动作，不创建新 ID 重试。

修改沿 `publish_edit_for_message`，request_bytes 保留原 TRIP-scoped-request.1 的
单 item 选区语法；edit_bytes 是新增**内部** TRIP-calendar-edit.1（无客户端 HTTP 写入口）：
字段沿 ManualEdit 的 request_id/trip_id/expected_version/original_hash/title/changes/order。
仅 title=null、order=null、一个 text change；替换值必须出现在原消息中，且选区须由
上面的真实编译来源证明。不能改固定/未知保护条目、时间段、日历或其他条目。
修改投影复用原 scoped_trip.check 的精确 selected_ids、same_snapshot 和 limits/output
检查；未选中的当前 NEEDS 修订不因保存的 Trip 较旧而被还原。
已有 dated 旧格式仍用旧 publisher。新的 structured.3 dated 修改会重查日期依赖结果。

最终回调必须执行原 `check_trip()`，且保留原身份/来源/预算 deadline 顺序。
规划/修改读取分别用新增受保护 `calendar_plan_receipt(binding)` /
`calendar_edit_receipt(binding)`；旧 lio_plan/edit_receipt 不放宽 basis 版本。

撤销用新增 `CalendarUndo.parse(TRIP-lio-undo.2 原字节)` 和受保护
`OperationContext.undo_calendar`，查询复用原 `lio_undo_receipt` 原动作账本。
宿主需安装实际 CurrentNeedsSource/NeedsEdits，签名器和 calendar=True 消费能力。
撤销先持有被恢复与当前版本的实际历史 MESSAGE 来源，再持有当前 NEEDS。
恢复完整上一版字节并追加版本，锁定项/当前源/owner 校验不放宽；旧 Undo.parse 拒绝 .2。

## 读端及证据范围

`local_calendar_read.create_local_calendar_read_app` 提供显式只读
TRIP-structured-read.2。structured.3 详情保留原 canonical hash，列表保留全部天数；
旧 .1/.2 的 calendar/day_count=null。旧端点遇到 .3 拒绝，绝不把无日期合成一个 null 日期桶。

`trip_calendar` 私有 PG 组使用真实受限角色、签名提交和 MESSAGE/NEEDS 租约，
L 编译器和日期供应商是明确的合成 port。它证明 C 领域组合，不能证明 LIO3 公网接线、
真实地点质量、真实天气或 App 体验；这些由 #862/#863/#864 和 L2 #32 另验。
