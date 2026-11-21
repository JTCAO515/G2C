# HOTEL.1 · 酒店跳转

`POST /v1/tools/hotel/link` 使用现有 App Bearer 和内部测试账号白名单。香港默认关闭。有 Bearer 格式的请求返回 `403 not_enabled`。消费方用现有 `X-Request-ID` 关联请求。

## 请求

```json
{
  "version": "HOTEL.1",
  "city": "北京",
  "check_in": "2026-12-03",
  "check_out": "2026-12-05",
  "guests": 2,
  "language": "zh"
}
```

`city` 可换为 `location`（`{lat,lng,radius_m}`，WGS-84，半径单位米）。两种地点只能提供一种。日期为 `YYYY-MM-DD`，退房日须晚于入住日。人数为正整数，语言为 `zh` 或 `en`。拒绝身份、联系方式和未知字段。

## 响应

```json
{
  "version": "HOTEL.1",
  "url": "https://hotel.example.invalid/v1/tools/hotel/out/fixture_handle_aaaaaaaaaaaa",
  "applied_filters": ["location"],
  "unapplied_filters": ["check_in", "check_out", "guests", "language", "accepts_foreign_guests"]
}
```

响应中的链接是服务端交接链接。示例域名仅为客户端夹具。真实 Trip.com 跳转、归因及可用参数由 [阶段 0](https://github.com/JTCAO515/G2C/issues/1309) 核实。响应只宣告供应商实际应用的筛选条件。确认支持「接待外宾」后才默认应用。App 按 #225 披露推广链接，预订和支付在 App 外完成。

HTTP 400 为 `invalid_request`，401 为 `sign_in_required`，403 为 `not_enabled`，413 为 `request_too_large`，502 为 `supplier_unavailable`，503 为 `unavailable`，504 为 `supplier_timeout`。失败响应例如 `{"error":"not_enabled"}`。每次授权且有效的调用在分发前增加该账号本日的持久计数。酒店搜索取决于公司联盟账号的免费权限。
