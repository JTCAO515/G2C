# #860 无日期行程：structured.3 设计提案

状态：A/B平台/L消费设计已确认；新增契约待本票独审、精确CI及合并，不是运行时能力。
父票 #859；实施 #861，编排 #862，App #863，评测 #864。
JT 2026-11-12 决定优先：城市和天数齐即可规划保存，日期、人数不是保存前置。

## 表示与不变量

新增 `content_version=structured.3`，不改变 structured.1/.2/provenance.1。
根字段拟为 `content_version,title,calendar,days,items,sources,date_checks`。

- `calendar={state:"undated"}` 表示出发日期待定；不得带 start_date。
  `days=[{day_index:1},...,{day_index:N}]`，顺序必须连续且从1开始。
  无日期天不得出现 date、占位日期或由设备时间/今天推断的日历日期。
- `calendar={state:"dated",start_date:"2026-12-01"}` 时，days 每天同时带真实
  `date`，必须严格等于 start_date + day_index − 1；跨月、跨年、闰年按日历计算，
  越界拒绝。不能混合有日期天和无日期天。
- items 保留原全局稳定 id/text/verification/evidence/fixed/source_category/source_refs。
  schedule 两端为 `day_index,time,timezone,utc_offset`；day_index 必须指向 days。
  日期只在 dated 的 days 中表达，不在每个事件重复存一份 date。
  时间沿 structured.2 的分钟/秒精度 Observation；未知不补零、不猜时区。
  无日期时 utc_offset 不冒充已确定瞬时偏移；以 unknown/missing 表达。
- N 是原请求天数，days.length=N；既有内容字节上限、items上限和产品天数准入不放宽，
  不用截断天数或丢失安排来通过校验。日期待定不等于缺失/空行程。
- 未提供总人数不默认成1；原已声明参与者、来源和固定项保留。人数缺失不能作为
  本产品无日期或有日期行程保存的额外前置；参与者相关检查明确未确认。

`date_checks` 是服务端检查结果，拟按 weather/day_opening 两类分别返回
`kind,state,day_indices,item_ids,reason,evidence_refs`。state 为
`not_checked/unknown/clear/conflict`。无日期时两类都是 not_checked、reason=date_not_set，
不能有 clear/已查天气/当天开放的声明。补日期后 clear/conflict 必须有同源实际证据；
无证据则 unknown，不用模型的肯定句代替结果。该投影不授予保存或来源验证权限。

## 补日期、修改和撤销

补日期是同一 trip_id 上的确定性转换。输入来自 B 解析并绑定的原用户消息，携带
expected_version/content_sha256、真实 start_date 和原 source/message 引用；不信任
模型自行声称的日期，也不因单独日期回答创建另一份行程。相对日期仍以承载该日期的
原消息北京时间 question_day 解析；转换器接收明确 ISO 日期，不再次解读自然语言。

在原 owner/身份/来源/HEAD CAS、签名与唯一提交边界下生成新版本：只建立 calendar
和 days 的日期映射，保留 item ID、原句、顺序、时间、地点来源、锁定标志和相对天序。
不得重新调用模型整份改写。先核当前版本，再提交；丢ACK只读核原动作，禁止重放。

补日期后进行依赖日期的检查；把结果绑定到该转换版本。天气/当天开放的未知或闭馆
冲突，不伪造通过、不自动替换景点，返回结构化 conflict/unknown 给 B 说明并提出建议。
新版本显示真实日期和未确认/冲突状态。已有绝对日期的硬固定约束仍以原来源为权威：
若所给出发日使其不一致，拒绝这次矛盾转换并返回冲突，不能写一份移动固定约束的新版本。
该硬冲突与外部闭馆等可提示的冲突分开，不能借新版本绕过旧锁定、来源或发布校验。

无日期修改以 day_index 和实际 item_id/完整名称定位；只替换指定项，保持 calendar=undated、
其余原字节与固定项。无日期绝不按 today 分桶或改用北京默认城市。dated修改保持原行为。
撤销沿用追加版本的历史语义：转换后撤销追加一版，恢复转换前完整无日期内容；历史
各版本、原动作回执与费用保留。撤销不得复活已失效的来源或绕过当前撤回/身份保护。
检查报告也随被恢复内容回到对应的未确认状态，不把某个 dated 版本的报告移给 undated。

## 读取、MESSAGE 与职责

C 在 #860 **一并提交**新的 TRIP 内容契约及 MESSAGE `trip-schema.2`/正反例，
避免两个作者修改同一共享契约。确认见 A #6818480818/#6819064617、B平台 #6818540981、
实际对话消费方 L #6819228034。实施仍分别在 C861、L862、A863。

MESSAGE 新选择器的 day 是互斥两种之一：
`{day_index:2}`（undated，timezone仅当有已知当前来源时可带并校验）或现有
`{date:"2026-12-02",timezone:"Asia/Shanghai"}`（dated）；也可为 null。
二者混用、0/负数/非整数/超出当前行程范围、以旧 expected_version 指向转换后内容均拒绝。
新版本引用允许 structured.3，并继续绑定原 trip_id/version/content_sha256 与原消息；
客户端提交的选择器不是发布授权。不扩大旧 MESSAGE-send.3/trip-reference.1 的允许值。
核心 MESSAGE 不新增send版本；send.3/.4与原canonical封装保持原样。
新增 LIO-message.3/receipt.3/lookup.3，以 /v3/lio/messages 显式接线；其文本/语言/MID/
CID/new_conversation包络沿旧规则。新外层LIO wire的input hash和内层canonical MESSAGE
的input hash不是一层，不得互换。LIO-trip-reference.1包含原conversation/generation/
MID/RUN/sequence/canonical input_sha256/message_version/lio_protocol以及受保护读取的
trip_id/trip_version/content_version/content_sha256/selection。该引用不能作为提交权。

新增 LIO-trip-card.2，字段恰为version/trip_id/trip_version/content_version/content_sha256/
title/calendar/days/date_checks；structured.3天包含day_index、dated时才包含date，遍历全部
天含空休息日。旧内容显式calendar/date_checks=null并按原date分桶，不能冒充undated。
由LIO-timeline.3（/v3/lio/timeline）和LIO-trip-history.3（GET /v3/lio/trip）承载；
history沿用conversation_id/current/history/undo_target/next_before，current/history同卡片类型。
LIO-trip-undo.3/receipt.3走新增 /v3/lio/trip-undos 与 /v3/lio/trip-undo-receipts，
保留原target编码、action_id和原动作查询语义，显式接新undo实现；旧undo.1不扩能力。

TRIP-date-convert.1 是服务端内部输入，不新增客户端直接保存入口：action_id/trip_id/
expected_version/original_hash/start_date/date_source，后者含受保护原reference/quote/question_day。
TRIP-date-convert-receipt.1绑定原action/basis；outcome=converted时committed=true且版本为
basis+1，返回实际新hash/calendar/date_checks/conflicts。硬固定冲突=conflict/committed=false，
提交字段为null；unknown时committed和新状态均null，只能核原动作，不生成重试动作。
软冲突提交时必须把有证据的date_checks conflict与conflicts一致返回，缺证据为unknown。

TRIP 新读版本须显式返回 calendar/days（含连续 day_index）和检查状态，支持
structured.1/.2/.3。旧读版本字节/语义不变；遇到旧协议不能表示的 structured.3，
不得伪装成 dated 或把多天压成一个 date=null。旧客户端仅留在旧版本能力范围，
新客户端同时识别旧版本和新版本；能力在部署接线中明确，不靠失败后静默回退。
旧保存的行程不批量转换；它们继续沿原版本读取、修改与历史恢复。

读端命名 `TRIP-structured-read.2`：新增GET /v2/trip-structured-list和/v6/trip-structured，
分页和owner保护沿旧约束，不改旧读端。
列表 summary 保留 trip_id/version/content_version/title/content_sha256，新增 calendar/day_count；
structured.3 必须给真实 calendar 和正 day_count，旧 .1/.2 两字段为 null，表示 legacy，
**不能**解释成 undated。详情仍保留 trip_id/version/content_sha256/content，content 是
原版本完整内容；哈希必须绑定该内容原规范字节。MESSAGE-send.4 已被 scoped edit 使用，
本票不能占用该版本号。精确schema/例子供L/A复核，不以契约样例冒充运行时验收。

## 存储与迁移结论

当前 Proposal/Trip/历史已保存版本化 canonical UTF-8 内容与哈希，数据库没有把每天
的 date 设成独立不可空列。#861 扩展显式解析/投影/验证/历史支持即可复用同一存储。
因此本设计 **不需要迁移**：不改已应用迁移，不改角色/RLS/权限/密钥或既有签名原字节。
若实施发现确实需要新增存储，另以追加迁移和 ADR-0007 专项门禁提交，不补改历史。

## #861 实施接缝

现有 NEEDS event 只有 date/time/timezone/place，applies_to 只允许 self/party/companion，
没有 day_index。因此“第1天酒店集合”不能伪造 date，也不能写成 applies_to=["day-1"]。
新发布入口需在原 NEEDS 引用之外取得受同一原 MESSAGE/RUN/内容哈希/版本保护的固定项
天序映射；由 L 提供明确来源和原文 quote，C 核其 item_id、天序范围及当前来源，不从描述
重猜相对天数。该接缝不扩展旧 NEEDS 字段、不让模型的任意索引变成来源授权；具体输入
形状为LIO-fixed-day-bindings.1：needs_id/needs_version/needs_content_sha256/reference/bindings，
每项item_id/day_index/end_day_index/quote/source_reference。两端天序均显式给出，普通同日
固定项两值相同；跨日必须有原文依据，不能由时钟大小推测。root和每项reference均绑定
同scope对话/generation的实际canonical MESSAGE/RUN；来源不得指向未来消息。L只从原文
明确第N天/day N编译，C重新核当前原件、NEEDS字节、固定项覆盖、版本/范围和受保护编译
结果。缺失、歧义、陈旧或不一致均unresolved/conflict，不默认第1天、不删原固定项。
该sidecar不是新的NEEDS字段或候选发布权。无来源可证的固定映射应拒绝/返回冲突。

旧 LioSourceWindowPublisher 把已知 arrival.date 作为保存窗口；新无日期入口必须显式
选择新增发布策略，保留旧策略和其缺日期拒绝用例。旧 candidate_days/_card 按 date 分桶，
新投影须按完整 days 索引遍历，包括没有活动的休息日，不能把所有 unknown date 合成一天。
旧 _protect_fixed 只接受 structured.2：新撤销入口须显式支持 .3，恢复完整原内容并再次核
当前来源；不得放宽旧入口或只恢复界面日期。旧 instant 可行性是绝对时刻检查，无日期
入口改用相对天序和墙上时间做可做的检查，并对绝对瞬时、天气、当天开放明确 UNKNOWN/
not_checked，不声称整体可行。已定日期分支仍执行原日期/时区/固定项保护。

## #860 验证与交付门槛

新增 JSON Schema + 语义检查正反例：无日期和已定日期、混用拒绝、天序不连续/重复/0、
日期映射不一致/越界、未知时间/时区、跨天项引用、额外字段、非法检查状态或伪造来源。
JSON Schema 只证形状；连续性、日历算术、引用和来源/锁定的语义检查必须单独验证，
不能把 FormatChecker 成功当作真实天气、开放或发布通过。

旧契约文件哈希不变、旧示例及旧有日期行程测试仍通过。#860 只交设计/新契约/例子，
不提前接生产写入；#861 才交领域实现及 PG，#862/#863 才接编排和 App。
A、B 在 #860 明确可消费后提交 PR；独立红线审查逐条写追加必查项（未触及项写 N/A
及理由），精确 head CI 全绿，锁 head 合并。外部模型/部署/资源不是本票的替代证据。
