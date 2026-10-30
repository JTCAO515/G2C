# TRIP structured.1 / manual.1 — frozen

Owner C（JT2026-10-30转移backend/trip）。新增版本，不修改旧TRIP/provenance.1、
Proposal digest、Action、confirmation或receipt。实施与来源/发布设计见
[设计稿](../../backend/trip/STRUCTURED-VERSION-DESIGN.md)。本地显式 opt-in；App #286归A。

## 结构化内容

`content_version=structured.1`，恰为 content_version/title/items/sources。
UTF8 canonical JSON（排序key、紧凑分隔、不转义Unicode、禁止非有限值）；至多1,000,000 bytes。
title为1–120 Unicode码点非空字符串；items为1–60项，全局id唯一，不按日期重编号。
每项恰为id/text/verification/evidence/schedule/fixed/source_category/source_refs。
text非空至多500码点；id沿原Trip ASCII 1–128字符语法。

schedule恰为start/end；两端恰为date/time/timezone/utc_offset四个Observation：
known恰为state/value；missing/unknown只有state；uncertain为state/note（1–500码点）。
明确日期严格ISO YYYY-MM-DD；时间HH:MM:SS；时区为明确IANA数据库名称，拒绝localtime/
Factory；偏移为明确±HH:MM、小时0–23分钟0–59。未知不补零，不解析text，不用设备时区。
fixed为同一Observation，known的value必须bool；unknown不等于false。

verification/evidence沿原pending/verified及证据规则；结构合法不证明事实已核验。
sources保留原provenance.1 source-record形状和其原快照规则，最多40项；每item最多1个
source_ref，引用必须存在、类别与原text匹配，无悬空source。此处仅是兼容的原记录校验，
不把旧source快照改称PLACE@1.0/NEEDS@1.0，也不授予采集/当前性许可。
source_category为unknown/user_provided/queried/estimated；手动明确原文可用user_provided、
空refs，由持久manual basis保存真实原输入。来源关联不升级verified；queried/estimated及
有message引用的声明必须pending、空evidence。新正式NEEDS来源由独立basis/lease接入，
不从客户端的sources推断owner或发布许可，当前运行组合仍依赖B #305。

旧host默认structured=False：读/发布/接受新版本明确拒绝，不剥字段或返回旧字符串。
新host显式structured=True；旧版本继续原行为。旧记录不自动转换或默认解锁。

## 明确手动编辑与一次保存确认

`TRIP-manual-edit.1` 输入为canonical UTF8，恰为：
version/request_id/trip_id/expected_version/original_hash/title/changes/order。
request_id/trip_id为原Trip id语法；expected_version为正整数；original_hash为原content精确
SHA256。title=null表示未选中，否则明确新title。changes为至多60项，恰为item_id/field/value；
field仅text/schedule/fixed，不可重复同item/field。order=null或完整、不重复的原ID排列。
未选中项逐字保留，固定或保护unknown项不能改文/时间/位置；明确lock/unlock必须单独选择，同项
不能夹带内容变更。改变文字清除该项旧事实证据/来源引用，保留原记录与其他项；新原文是
用户声明。改变时间清除继承事实证据。来源记录的删除仅指新候选内不再引用的副本，
不物理删除旧Trip/来源/历史。

prepare在原保护operation内读实际Trip、核原version/hash、共享FEAS检查；CONFLICT整份
拒绝，没有Proposal/Trip/receipt新增；UNKNOWN显式保留。scope锁内通过原_publish_in_tx
发布原Proposal并持久原输入/before/after/diff。request_id异bytes409，同bytes查询原候选，
不自动换新版本或延长expiry。手动无NEEDS不造空Snapshot、预算、同伴或整体可行结论。

`TRIP-manual-save.1` 输入恰为version/action_id/proposal_id/candidate_hash，canonical UTF8
至多32768 bytes；用户对该diff明确点击保存是此原动作，客户端不传viewed/confirmed/owner。
服务端从原basis与真实当前Trip核候选，用原ConfirmationSigner签发精确Action，调用唯一
_act_in_tx；原Trip版本/内容、proposal终态、唯一receipt、manual-intent在同一事务提交。
最后DB时钟/confirmation expiry保持。same action_id/bytes读原receipt；异bytes409。
回执只能证明原提交，不能证明当前版本。ACK未知不重发、不换ID，先查原动作。

新表是local runtime only追加迁移0022：same-scope FK/FORCE RLS、原runtime最小SELECT/
INSERT；无UPDATE/DELETE/TRUNCATE、新role/BYPASSRLS/SECURITY DEFINER。非空down拒绝。

## 本地独立host与结果

`cj_trip.local_manual_app.create_local_manual_app(conninfo_path,auth_dir,confirmation_signer,...)`
要求CJ_ENV=local、显式原ConfirmationSigner与输出上限；复用原canonical AUTH、scope映射
和Trip operation，同步私有投影/编码留在其生命周期内。根factory不自动启用新版本。

| 方法/路径 | 输入/结果 |
|---|---|
| POST /v1/trip-manual-preparations | octet-stream edit.1 → preparation |
| GET /v1/trip-manual-preparations?request_id=... | 原prepare只读查询 → preparation或null |
| POST /v1/trip-manual-saves | octet-stream save.1 → receipt |
| GET /v1/trip-manual-receipts?action_id=... | 原Trip动作receipt或null，不能由缺失推断可重试 |
| GET /v3/trip-structured?trip_id=... | trip={trip_id,version,content}或null；仅structured内容 |

结果顶层 `version=TRIP-manual-result.1`、request_id和对应preparation/receipt/trip。
preparation为proposal_id/trip_id/expected_version/basis=manual-unbound.1/expires_at/
candidate_hash/status/content/diff/feasibility。diff含精确before/after、原request_id/trip_id/
expected_version。receipt沿原action_id/kind/proposal_id/candidate_hash/trip_id/committed_version。
错误用原BASE；409冲突，写入结果不确定503+reconcile_original，不暴露异常或私有数据。
无请求/额外/重复query、重复/额外body字段、超界/编码错误均拒绝；缺token401，实际AUTH
未知/不可用继续fail-closed，不从caller body推断身份。

## FEASIBILITY-TRIP@1.0

`cj_feasibility.trip_time.evaluate(original_canonical_bytes)`复用同一显式instant/半开区间
implementation，输出status/checks/content_sha256/version。唯一显式instant才比较顺序；
DST歧义/不存在或偏移不匹配保持ITEM_TIME_UNKNOWN。可显式offset消歧，不能补缺少时区。
倒序CONFLICT；整体仍UNKNOWN；没有真正NEEDS参与人/独占来源时，几何重叠仅UNKNOWN，
不假造占用冲突。checks保留原ITEM_TIME_ORDER/REVERSED/UNKNOWN和中英解释/字段证据。

本版本不是完整NEEDS绑定的RUN发布权限：完整Snapshot/Revision及当前来源、真实writer
fence组合仍等B #305，然后在C #204/#281接入；不以hash/DTO/数据codec代替lease。
真实模型/provider/云/费用/真机都未授权。本契约不改OpenAPI旧schema或旧生成代码；
新客户端按这些显式端点/版本接入，A端实现与验收另计。

可执行正负例：`backend/trip/tests/test_structured.py`、`test_structured_manual.py`、
`test_structured_storage.py` 和 `manual_pg.py`；`backend/feasibility/tests/test_trip_time.py`
覆盖显式跨日/DST/fold/偏移/倒序/相接边界。Fixture只证明语法/本地组合，不提供授权。
