# TAXI.1 · 打车信息

`POST /v1/tools/taxi/estimate` 和 `POST /v1/tools/taxi/link`。使用现有 App Bearer 和已批准的内部测试账号名单。香港的供应商验证完成前，路由统一关闭。有 Bearer 格式的请求返回 `403 not_enabled`。客户端用现有 `X-Request-ID` 关联请求。

## 请求

估价和链接均接收以下 JSON。经纬度使用有限 JSON 数字，地名可以省略。链接可另外带单个 `vehicle_category`，值来自估价车种。未知字段拒绝。

```json
{
  "version": "TAXI.1",
  "origin": {"lat": 39.9, "lng": 116.4, "coordinate_system": "WGS-84", "name": "北京西站"},
  "destination": {"lat": 40.05, "lng": 116.3, "coordinate_system": "GCJ-02"}
}
```

坐标系标记仅接受 `WGS-84`、`GCJ-02`。启用前须以供应商核对结果绑定实际坐标转换、地点分辨和允许的跳转目标。覆盖范围之外的判定须基于经核实的供应商标志。

| 操作 | 200 字段 |
| --- | --- |
| 估价 | `version`、`vehicles[].{category,name,currency,price_display}`、`observed_at`（ISO 8601）。供应商给出可核实区间和距离时，可附 `price_min_minor`、`price_max_minor`（CNY 分）和 `distance_m`。可附 `trace_id`。区间和距离缺失时省略。 |
| 链接 | `version`、`url`、`link_type`（`https` 或 `app_scheme`）。链接格式及 iPhone 表现以 [阶段 0](https://github.com/JTCAO515/G2C/issues/1309) 为准。 |

错误示例为 `{"error":"quota_exceeded"}`。非法坐标、身份字段或未知字段返回 `400 invalid_request`。缺少有效登录为 `401 sign_in_required`。非内测账号为 `403 not_enabled`。超过 4 KiB 为 `413 request_too_large`。达到单项每日 50 次为 `429 quota_exceeded`，供应商限流为 `429 rate_limited`。覆盖范围或坐标不可核实可分别返回 `422 out_of_service_area`、`422 coordinate_unverified`，实际分类需阶段 0 的证据。供应商失败为 `502 supplier_unavailable`，超时为 `504 supplier_timeout`，本地依赖不可用为 `503 unavailable`。

Asia/Shanghai 每日分别统计每个账号的估价和链接调用次数。鉴权通过且请求有效后，在供应商分发前持久预留一次，包括结果未知的请求。滴滴只接收工具所需的坐标、地点名称与明确选择的车型。账户、手机号、App 凭据及原始请求均不进入供应商载荷或计数记录。只支持信息型工具。
