# NEARBY.2 · 附近（含「必需品」）

`POST /v1/tools/nearby/search`：与 NEARBY.1 同一路由、同一 App Bearer、同一内部测试名单与开关。`NEARBY.2` 只在 NEARBY.1 的基础上扩充 `categories`，加入「必需品」；请求的其他字段、响应结构、计次与错误都与 NEARBY.1 相同。

- 授权：M4 条目 12①（「必需品」由 JT 2026-11-25 决定：选项原文「不做换汇」「用关键字搜（推荐）」，见 [#1606](https://github.com/JTCAO515/G2C/issues/1606#issuecomment-7155827092) 与授权增补 [#1621](https://github.com/JTCAO515/G2C/pull/1621)）。
- 分类码依据：高德官方 POI 分类编码表 V1.06（lbs.amap.com/api/webservice/download）。

## 与 NEARBY.1 的兼容

- `NEARBY.1` 冻结不改：服务端继续接受 `"version": "NEARBY.1"`，只认 `food`、`coffee`、`sights`、`shopping` 四个类别，行为不变。旧版 App 照旧使用 NEARBY.1。
- `"version": "NEARBY.2"` 的请求可以使用下表全部八个类别。新版 App 统一发 NEARBY.2，包括只请求原有四类的时候。
- 响应的 `version` 与请求一致。NEARBY.2 的响应结构与 NEARBY.1 完全相同，没有新增字段。
- 逆地理接口 `POST /v1/tools/nearby/reverse` 不变，仍为 NEARBY.1。

## 类别

| `categories` 值 | 高德检索方式 | App 显示（固定文案，中文 / English） |
|---|---|---|
| `food` | types `050000` | 美食 / Food |
| `coffee` | types `050500` | 咖啡 / Coffee |
| `sights` | types `110000` | 景点 / Sights |
| `shopping` | types `060000` | 购物 / Shopping |
| `atm` | types `160300`（自动提款机） | 银行 ATM（是否支持外卡请看机身标识） / Bank ATMs (check the machine's sign for foreign cards) |
| `pharmacy` | types `090601`（药房） | 药房 / Pharmacy |
| `toilet` | types `200300`（公共厕所） | 公共厕所 / Public toilets |
| `luggage` | 不用 types，固定关键字 `keywords=行李寄存` | 行李寄存（按名称搜索，结果可能不全） / Luggage storage (found by name; some may be missing) |

- 高德没有「是否支持外卡」的信息：服务端和 App 都不得声称某台 ATM 支持外卡。
- 不提供换汇、银行网点类别。

## 请求

```json
{
  "version": "NEARBY.2",
  "request_id": "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10",
  "center": {"lat": 39.9087, "lng": 116.3975, "coordinate_system": "WGS-84"},
  "categories": ["atm", "pharmacy"],
  "radius_m": 1000,
  "sort": "distance"
}
```

- `categories`：1–4 个，不重复。
- **`luggage` 只能单独请求**：`["luggage"]` 合法；`luggage` 与任何其他类别同时出现时，返回 `400 invalid_request`，不调用供应商、不计次。这样每次查询仍只调用高德 1 次。
- 其余七个类别可以任意组合，组合后合并为一次 types 检索。
- `center`、`radius_m`、`sort`、`request_id` 的规则同 NEARBY.1；未知字段一律拒绝（`400 invalid_request`）。
- `"version": "NEARBY.1"` 的请求里出现 `atm`、`pharmacy`、`toilet`、`luggage` 中任何一个，返回 `400 invalid_request`。

## 响应

与 NEARBY.1 相同：

```json
{
  "version": "NEARBY.2",
  "source": "Gaode",
  "items": [
    {"id": "B000XXXX", "name_zh": "中国银行ATM(王府井支行)", "address_zh": "王府井大街...", "type_code": "160301",
     "lat": 39.9142, "lng": 116.4035, "coordinate_system": "GCJ-02", "distance_m": 120,
     "rating": null, "cost_cny": null, "opening_hours": null, "photo_url": null}
  ],
  "omitted_items": 1
}
```

- `type_code` 原样返回高德的 6 位类别码。`luggage` 的结果是按名称检索到的，各条的 `type_code` 是该地点自己的类别，可能各不相同。App 按**请求的类别**分组展示，不靠 `type_code` 判断类别。
- 没有结果时 `items` 为空数组；缺少必需字段的条数计入 `omitted_items`，规则同 NEARBY.1。

## 计次、额度与缓存

- 与 NEARBY.1 同一份计数（服务 `amap-nearby.1`）：每人每天 ≤100 次、合计 ≤3,000 次周边搜索，只共用高德合计 ¥500。新增类别**不新增额度**。
- 每次查询（缓存未命中）调用高德 1 次周边搜索；输入为 WGS-84 时另有 1 次坐标转换，规则同 NEARBY.1。
- **额度用完**：返回 `429 {"error": "quota_exceeded"}`，不调用供应商。每日额度和合计额度用完都是这个返回。App 显示「今日附近次数已用完」或同义的固定文案，不重试。
- 短时缓存的键包含检索方式：types 或固定关键字。`luggage` 与其他类别的结果不会互相命中。

## 错误

| 状态 | `error` | 含义 |
|---|---|---|
| 400 | `invalid_request` | 请求格式不符；含 `luggage` 与其他类别混用；NEARBY.1 使用了新类别 |
| 401 | `sign_in_required` | 未登录 |
| 403 | `not_enabled` | 账号不在名单或服务未开启 |
| 409 | `request_already_used` | 同一 `request_id` 已用过 |
| 413 | `request_too_large` | 请求体过大 |
| 429 | `quota_exceeded` | 每日或合计次数、或高德现金上限用尽 |
| 429 | `rate_limited` | 高德限流 |
| 502 | `supplier_unavailable` | 高德返回异常 |
| 503 | `unavailable` | 记账状态未知，未调用供应商 |
| 504 | `supplier_timeout` | 高德超时 |

## 正负例

| 请求 | 结果 |
|---|---|
| NEARBY.2，`["atm"]` | 200，高德 types `160300` |
| NEARBY.2，`["pharmacy", "toilet"]` | 200，高德 types `090601\|200300`，只调用 1 次 |
| NEARBY.2，`["luggage"]` | 200，高德 keywords `行李寄存`，不带 types |
| NEARBY.2，`["luggage", "toilet"]` | 400 `invalid_request`，不调用、不计次 |
| NEARBY.2，`["food", "coffee"]` | 200，与 NEARBY.1 相同 |
| NEARBY.1，`["atm"]` | 400 `invalid_request` |
| NEARBY.1，`["food"]` | 200，行为不变 |
| NEARBY.2，`["exchange"]` 或 `["bank"]` | 400 `invalid_request`（不提供） |
| 当日第 101 次（或合计第 3,001 次） | 429 `quota_exceeded`，不调用 |
