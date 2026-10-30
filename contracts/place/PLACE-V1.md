# PLACE@1.0 — frozen

Owner B / #263（父 #13）。JT 2026-10-30 授权本线自行冻结新版本；本版为领域数据
合同，正式 producer 是 `cj_place.contract_v1`。不修改旧 CJ-PLACE-GAODE@0.1.0-rc.1、
旧 TRIP JSON 投影、BASE/RUN/USAGE。数据格式不是 AUTH、freshness 或执行许可。

## 查询

原 UTF8 bytes 恰为 `{version:"PLACE-query.1",query:{...}}`。重复键、未知字段/版本、
非 JSON 常量、过深/超出 1MiB 读边界拒绝；不接受 owner、scope、provider URL、key、
attempt、period、budget、source、TTL 或允许执行字段。实际 host 可以设置更小限制。

| kind | 精确字段 |
|---|---|
| Search | kind、keyword、city、page、page_size；沿旧 Search 规则：单关键词，无批量竖线，page_size 1–25，page×size≤200，真整数 |
| Detail | kind、provider_id；精确 ID，不模糊找替身 |
| RouteQuery | kind、origin、destination、mode、departure；walking/driving |

endpoint 恰为 provider_id、coordinate、coordinate_role（poi_center/entrance/exit）。
Coordinate 恰为 raw、longitude/latitude 的 Decimal str、crs=GCJ-02；二数必须与 raw
关联。坐标最多12位原小数，路线 endpoint 最多6位，拒绝而不舍入/换建筑/填零。
departure 恰为 condition、at；at_query_time 的 at=null，specified_time 必须带时区。
当前 profile 不支持指定时间查询，保留原条件并返回 unsupported，不改为“现在”。

## 结果

恰为 version=PLACE-result.1、query、outcome、reason、source、places、routes、
provider_code、provider_count。query 是完整原条件；places/routes 保留顺序，不按名称
或坐标自动合并。只有 ok 可有可用条目，成功空结果用 no_results；失败不造空成功。

Place：provider=gaode、provider_id、name_zh，及 address_zh/coordinate/
entrance_coordinate/exit_coordinate/parent_id/navigation_id/typecode/
official_name_en/official_address_en 的 Observed。同名分店/入口 ID 分开，parent/navigation
不代替原 ID。当前 parser 的未知官方英文保持 unknown，不把机器说明写成官方字段。

Observed 恰为 state、value；state=present 才有非 null 值，其余 missing/empty_array/
empty_string/null/invalid/unknown 必须 value=null。真实原值 0,0 与缺失不同，不能填零。
Route 恰为 query、distance、duration、time_semantics、future_guaranteed；query 与原
RouteQuery 相同；数量为 Observed `{raw,value:<Decimal str>,unit:m或s}`。
time_semantics=provider_estimate_at_query_time，future_guaranteed=false，不承诺未来路况。

## 来源与失败

source 可 null；有值恰为 endpoint、provider、api_version、adapter_profile、request_ref、
binding_digest、query_started_at、received_at、provider_updated_at、evidence_kind、recording_ref。
固定 v3/高德/旧 adapter profile；endpoint 只有 credential-free 固定 origin/path。
时间为 `{iso8601:<带数值offset的微秒字符串>,fold:0或1}`，保留 offset/fold，比较真实瞬间。
provider_updated_at 未提供则 null，不用收到时间冒充；反序不作为 ok 的新鲜结果。

evidence_kind 为 synthetic/recorded_replay/live_provider/unverified_bytes；录制回放必须有
非空 recording_ref，其余为 null。该 label/hash 不证明采集或授权；可信 host 按实际来源
设置。旧 Source.evidence=synthetic 不能被新 encoder 升级为其他级别。真实采集、外部
provider 或费用均须另获批准，本版本不授予；本次六个 golden 及全部负例均标“合成”。
无缓存/第二地点库；采集、许可、留存与缓存适用性由实际来源方案决定。

outcome 保留 ok/no_results/rate_limited/provider_error/unknown/invalid_response/
binding_mismatch/stale/unsupported/unavailable。错误 reason 只为固定安全码，不回显
供应商正文、异常或凭据；超时/ACK未知不证明免费/未派发，禁止自动换 attempt 重试。
AUTH/归属/取消/预算错误由原域处理，不变成 no_results。

## 消费与兼容

`encode_query/decode_query`、`encode_result/decode_result` 是显式新版本 codec；
`publish_response` 只复用唯一旧 parser 再投影，**没有派发入口**。旧 execute 继续关闭，
实际 canonical MESSAGE/RUN→唯一 Meter→PLACE producer 接入由 #265 证明；新 data codec
和合成回调都不代替该业务验收。原 USAGE unknown/period/attempt/限额和 TripProposal 确认保留。

旧 producer/投影继续仅在其候选范围使用；新 decoder 拒绝旧版本，不自动升级消费者。
只有所有实际消费者固定新版并验证回读/回退后才讨论旧路径退出，本票不删除旧实现。
A #21/#266 消费新结果/来源及失败，B #264/#265 解析/host，C #18 可消费固定字段；
UI、工具运行、真实接口分别验收，不以本 L0 数据合同宣布完成。

正例：[v1-examples.json](v1-examples.json)，由真实产品 codec 输出旧唯一 parser 的六个
合成结果（含路线）。负例见 backend/place/tests/test_contract_v1.py：实际 decoder 拒绝
坐标/身份/来源/时间/缺失/计数和权限伪造，不是只检查 fixture 描述。无网络、key 或费用。
