# TAXI.1 · 打车信息

`POST /v1/tools/taxi/estimate` 和 `POST /v1/tools/taxi/link`。使用现有 App Bearer 和已批准的内部测试账号名单。香港的供应商验证完成前，路由统一关闭。有 Bearer 格式的请求返回 `403 not_enabled`。客户端用现有 `X-Request-ID` 关联请求。

## 请求

估价和链接均接收以下 JSON。经纬度使用有限 JSON 数字，地名可以省略。链接可另外带单个 `vehicle_category`，值来自估价车种。当前授权下该字段不发送给滴滴，客户端不得把返回链接展示为已选择车型。未知字段拒绝。

```json
{
  "version": "TAXI.1",
  "origin": {"lat": 39.9, "lng": 116.4, "coordinate_system": "WGS-84", "name": "北京西站"},
  "destination": {"lat": 40.05, "lng": 116.3, "coordinate_system": "GCJ-02"}
}
```

坐标系标记仅接受 `WGS-84`、`GCJ-02`。发布版本使用本地大陆地图单元先检查两端，再将标记为 `WGS-84` 的点转换为 `GCJ-02`。出境或不在服务范围内的点返回 `422 out_of_service_area`，在调用滴滴前完成。估价缺少一端地名时，用滴滴逆地理补中文 `display_name` 或 `formatted_address`，无法核实返回 `422 coordinate_unverified`。供应商坐标为字符串。 [京沪同点验证](https://github.com/JTCAO515/G2C/issues/1309#issuecomment-7090786405)

| 操作 | 200 字段 |
| --- | --- |
| 估价 | `version`、`vehicles[].{category,name,currency,price_display}`、`observed_at`（ISO 8601）。`category` 和 `price_display` 分别保留滴滴 `productCategory` 与 `priceText`。客户端可按车型代码本地化名称。供应商给出可核实区间和距离时，可附 `price_min_minor`、`price_max_minor`（CNY 分）和 `distance_m`。可附 `trace_id`。区间和距离缺失时省略。 |
| 链接 | `version`、`url`、`link_type=https`。已验证的供应商 `appLink` 使用 `https://v.didi.cn/XvYQEWe`，只接收与本轮起终点一致的四个坐标查询参数。真机落地以 [阶段 0](https://github.com/JTCAO515/G2C/issues/1309) 为准。 |

错误示例为 `{"error":"quota_exceeded"}`。非法坐标、身份字段或未知字段返回 `400 invalid_request`。缺少有效登录为 `401 sign_in_required`。非内测账号为 `403 not_enabled`。超过 4 KiB 为 `413 request_too_large`。达到单项每日 50 次为 `429 quota_exceeded`，供应商限流为 `429 rate_limited`。滴滴 `-32001` 触发一次退避重试，仍限流则返回 `429 rate_limited`。`-32002` 记录固定告警并返回 `502 supplier_unavailable`。`-32010` 返回 `400 invalid_request`。`-32021` 只重新估价一次，链接可用同一请求参数继续一次。`-32050` 返回 `502 supplier_unavailable`。超时为 `504 supplier_timeout`，本地依赖不可用为 `503 unavailable`。

Asia/Shanghai 每日分别统计每个账号的估价和链接调用次数。鉴权通过且请求有效后，在供应商分发前持久预留一次，包括结果未知的请求。滴滴只接收工具所需的坐标与地点名称。账户、手机号、App 凭据及原始请求均不进入供应商载荷或计数记录。只支持信息型工具。

本地服务范围数据来自 [Natural Earth v5.1.2 的 1:10m CHN map unit](https://github.com/nvkelso/natural-earth-vector/releases/tag/v5.1.2)。转换公式来源及许可见 [coordtransform](https://github.com/wandergis/coordtransform)。
