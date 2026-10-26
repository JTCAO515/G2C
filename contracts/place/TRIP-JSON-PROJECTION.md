# PLACE → TRIP JSON 投影候选

候选标识 `CJ-PLACE-TRIP-JSON@0.1.0-rc.1`。本轮 parent
`06ffeae57d874423f5a04efb3bfe43fa9ada050e`，产品模型/解析固定
`5904e37f698ceb822c16e39ae36c87552235cabb`。这是可供原双审/consumer 确认的
**内部值投影候选**，不是新 HTTP wire、地点数据库、运行入口、鉴权/新鲜度 authority，
不宣布 PLACE@1.0 发布。类型唯一来源仍为
[models.py](../../backend/place/cj_place/models.py)，正式 API 仍由 CJ005 维护。
原 TRIP 目前仍应拒绝采用，直至原门禁与 consumer 确认；格式正确不授予用户接受或写权限。

## 范围与精确外形

UTF-8 JSON object，所有列出的字段必填，不省略 null；重复键、未知字段、未知版本和
非 JSON 常量应拒绝，不能补默认值或忽略授权/精度相关字段。外层只有：

```json
{"projection_version":"CJ-PLACE-TRIP-JSON@0.1.0-rc.1","result":{}}
```

`result` 精确包含：`contract_version`、`outcome`、`reason`、`query`、`source`、
`places`、`provider_code`、`provider_count`。值逐字段来自同一个原 producer Result；
places 是原顺序数组，不能按名称合并、重排后猜选中项或将另一 Result 的 Source 拼入。
`contract_version` 原值 `CJ-PLACE-GAODE@0.1.0-rc.1` 不被投影标识替换。
`reason` 保留 producer 固定安全码；provider_code 为原字符串或 null，provider_count 为
原非负整数或 null（拒 bool）。没有 max_age、expires_at、accepted、owner、token 字段。

本候选只承载地点值及其原查询/来源。**只有原 Result.routes 为空时可投影**；非空路线结果
不通过删掉 routes 套入本格式，须原 producer/consumer 另确认受影响范围。该缺口不阻
Search/Detail 地点消费，不在本轮添加路线 DTO/正式 API。RouteQuery 可原样承载在诊断
结果中，但本投影没有路线耗时/距离，不能据此宣称路线可用。

| 值 | 精确字段/编码 |
|---|---|
| Place | `provider` 固定 gaode；`provider_id`、原 `name_zh`；`address_zh`、`coordinate`、`entrance_coordinate`、`exit_coordinate`、`parent_id`、`navigation_id`、`typecode`、`official_name_en`、`official_address_en` 均按原 Observed 投影 |
| Observed | 精确 `{"state":...,"value":...}`；present 时 value 为原值投影；missing/empty_array/empty_string/null/invalid/unknown 时必须 value=null，不能删除字段、改成空数组/字符串或补零。没有“unknown 就是 false”规则 |
| Coordinate | 精确 `raw`、`longitude`、`latitude`、`crs`；raw 保留原字串，longitude/latitude **为 Decimal 的 str 字符串**，crs 固定 GCJ-02。禁止 JSON number、float 中转或 WGS84 重标 |
| Source | 精确 `endpoint`、`query_started_at`、`received_at`、`request_ref`、`binding_digest`、`evidence`、`provider`、`api_version`、`provider_updated_at`；source 可为 null，不能因此造时间/来源。provider=gaode，api_version=v3，provider_updated_at=null |
| outcome | 原枚举 ok/no_results/rate_limited/provider_error/unknown/invalid_response/binding_mismatch/stale/unsupported/unavailable，不改成统一“成功/空” |

ID 与原名的具体格式限制沿 producer，不复制成第二套地点规则。parent_id/navigation_id
不能替代 provider_id；同名分店保持不同 ID。英文官方字段当前 unknown，自译不能升级它们。
Source.evidence 只能是原 synthetic 或 unverified_bytes；没有 verified_provider/用户接受标记。
Python 同型对象或客户端自构 JSON 都不是可信 producer 回执。

### 原 query

query 只增加本格式所需的 `kind` 判别字段，其他字段来自原 Query，不补缺省参数：

- `Search`：kind="Search"、keyword、city、page、page_size。
- `Detail`：kind="Detail"、provider_id。
- `RouteQuery`：kind="RouteQuery"、origin、destination、mode、departure。
  origin/destination 精确为原 Endpoint：provider_id、coordinate、coordinate_role。
  departure 精确 condition、at；at_query_time 的 at=null，specified_time 的 at 用下述时间编码。
  保留原不支持条件，不将 specified_time 改成现在。此处可编码诊断值不代表已通过 prepare。

coordinate_role 仅 poi_center/entrance/exit，不默认中心或入口。Place 三坐标字段分别对应
这些角色。选择哪一个属于原 TRIP 的显式消费意图；地点投影自身没有“已选择/已接受”字段。
如原角色无 present 坐标，endpoint_from_place 会拒绝，不能回退到另一点/另一楼。
坐标 JSON 的数值关联必须满足 `longitude == str(Decimal(raw 经度部分))`、latitude 同理；
同时沿 Coordinate 的原格式/range 校验。保留 trailing zeros/负零及 raw，不舍入到路线
六位要求；Endpoint 要求的精度不够时拒绝。格式有效不证明地点真实存在。

### aware 时间、offset 与 fold

每一个 datetime（Source 两时间、query.departure.at 非 null 时）精确编码成：

```json
{"iso8601":"2026-11-01T01:30:00.000000-04:00","fold":0}
```

iso8601 为原 aware datetime 的 `isoformat(timespec="microseconds")`，必须有显式数值
UTC offset（UTC 为 +00:00），不静默转 UTC 或使用设备时区；fold 是 JSON 整数0或1，拒 bool。
恢复数值语义可用 fromisoformat 再保留 fold；比较 instant 时统一转换 UTC。
相同墙钟 fold0/-04:00 与 fold1/-05:00 相差真实一小时，不能直接按墙钟比较/续期。

该表示保留 wall fields、原 offset、微秒、fold 和 instant，**不承诺恢复原 tzinfo 对象 /
IANA zone 身份或未来 DST 规则**。Source 原类型没有保证提供 IANA 标识，不从 offset
猜目的地/ZoneInfo 名称；目的地日程时间仍沿 NEEDS/TRIP 的既有时区 authority。
原 datetimes/Config/Query 的 binding 仍由 producer 计算；不能用更改后的 JSON 文本重新
发明 binding_digest。Source 的 provider_updated_at 没有值，不能改为 received_at。

## 可信 max_age 的宿主边界

`max_age_seconds` 不从此 JSON 或客户端参数取得。宿主必须在既有受保护边界外部，
保存/取得与原 producer 调用对应的**原可信 Config 与 PreparedRequest**；本投影不新建
配置库、令牌或 dispatch-context 签名。现 `prepare` 的 digest 已绑定原 Config 的全部字段、
query/ref/start；重新关联时仍用这些原对象/值核 Source digest、endpoint、原 query/start/ref。
仅 digest 匹配证明相关性，不认证客户端自报的 Config、Source 或对象来源。
核对时间表示时要对原 offset/墙钟字段及 fold 逐项保持，不能仅用 datetime 的相等运算
证明 fold 未变；UTC instant 比较用于年龄/先后判定，不替代原时间表示的对应检查。

宿主可信记录或接缝缺失时，新鲜度为 UNKNOWN/不可作为新鲜依据，不能从 JSON、版本号、
收到时间、最近保存时间、合成样例的60秒或“已接受 Trip”补默认 TTL。采用时用宿主可信时钟
和原 query_started_at 的 UTC instant，按原可信 max_age 与 chronology/timeout 规则复核。
不能通过客户端给更大的 max_age、重标时间、修改 Source 再算 digest 获得新鲜度。

**尚未冻结/仍 UNKNOWN**：正式宿主可信原配置的持久读取/生命周期及权限接口、产品期限值、
真实 provider/账户结果、TRIP 持久化/缓存/再分发许可与正式编码落点。没有公开原接缝时
不猜签名；原 TRIP 可准备纯值映射，但不能把此候选作为可提交正式内容或永久使用许可。
以上均不授权网络、账号读取、Key、数据库、root/execute 或任何旧 HOLD/DEFERRED 探针。

## 正负样例与验证范围

[trip-projection-examples.json](trip-projection-examples.json) 的 positive 包含两个合成
Search/Detail 值（同名不同 ID、七种 Observed 状态、两种 DST fold）和一个原 RouteQuery /
unavailable 诊断。全部 evidence 保持 synthetic，不是现在/未来的真实地点或接受依据。
所有 positive 的 consumer adoption 都是 DEFERRED。

negative 是**仅用于 fixture 的单字段变更记法**：以 positive[0].projection 为基，按 path
数组替换/添加最后一个键为 value。它不是 Trip patch/API。列出 Decimal number/与 raw
不符、WGS84 重标、缺失值补零、无 offset/错误 fold、证据升级、client TTL 和虚构接受字段。
expected 是未来 consumer 必须拒绝的原因，**不声称当前 TRIP 已实现该拒绝**。

参考纯编码检查：[trip_projection_checks.py](../../backend/place/tests/trip_projection_checks.py)。
其测试内 encoder 只演示从现类型投影，不是 product serializer、public decoder 或 admission。
只核 golden/JSON 往返、Decimal/raw 关联、offset/fold 的 distinct instants、Observed 状态与
负向向量是否准确表达违规；不替代原 consumer 的解码/信任/采用测试或独立门禁。
运行：`PYTHONPATH=backend/place python3.14 -B backend/place/tests/trip_projection_checks.py`。
本轮不运行旧解析器/TLS/敏感探针，不改模型/transport/execute/TRIP/root。

2026-10-26 作者验证：先5项纯编码/向量检查 PASS，再新增并单独执行1项非空 routes
不能静默丢弃检查 PASS；共6项，不是 TRIP consumer/采用测试。仅这两个契约文件、
JSON样例及新独立测试文件构成本候选差额；无新运行接口或持久化权限。
