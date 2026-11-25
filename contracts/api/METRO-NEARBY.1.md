# METRO-NEARBY.1 · 地铁站周边

`POST /v1/tools/metro/nearby`：使用现有 App Bearer 和内部测试账号白名单（`CJ_METRO_NEARBY_INTERNAL_SUBJECTS_JSON`，须为 G2C@01–99 的子集）。香港默认关闭：已带 Bearer 但未开通时返回 `403 not_enabled`。消费方用现有的 `X-Request-ID` 关联请求。

- 用途：地铁图站点卡的「周边」（景点、购物、餐饮、咖啡）。
- 授权：授权清单 M4 条目 12⑤（JT 2026-11-25，[#1577](https://github.com/JTCAO515/G2C/pull/1577)）与条目 9（地点名英译）。
- 位置：App 只发城市与车站编号，**不发送任何坐标**。服务端从随包地铁图生成的站点表（`backend/cj_api/metro_stations.v1.json`，GCJ-02）查车站位置，因此本接口在形式上收不到用户位置。
- 方案见 [#1450](https://github.com/JTCAO515/G2C/issues/1450)。

## 请求

```json
{
  "version": "METRO-NEARBY.1",
  "request_id": "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10",
  "city_id": "guangzhou",
  "station_id": "gz012",
  "categories": ["sights", "shopping"],
  "language": "en"
}
```

- `request_id`：小写 UUID，每次查询新生成。同一个 id 不会重复调用供应商，重复时返回 `409 request_already_used`。
- `city_id`：2–20 个小写字母，即随包地图的城市 id（如 `guangzhou`）。
- `station_id`：两个小写字母加三位数字，即随包地图的车站 id（如 `gz012`）。
- `categories`：`sights`、`shopping`、`food`、`coffee` 中 1–4 个，不重复。
- `language`：`zh` 或 `en`。
- 没有 `center`、`radius`、`sort`：服务端固定以车站为中心、半径 800 米、按距离排序。
- 未知字段一律拒绝（400 `invalid_request`）。

## 响应

```json
{
  "version": "METRO-NEARBY.1",
  "source": "Gaode",
  "city_id": "guangzhou",
  "station_id": "gz012",
  "radius_m": 800,
  "items": [
    {
      "id": "B00140XXXX",
      "name_zh": "天河城",
      "name_en": "Teemall",
      "address_zh": "天河路208号",
      "address_en": "208 Tianhe Road",
      "type_code": "060101",
      "lat": 23.1325, "lng": 113.3227, "coordinate_system": "GCJ-02",
      "distance_m": 312,
      "rating": "4.6", "cost_cny": null, "opening_hours": "10:00-22:00",
      "photo_url": "https://store.is.autonavi.com/showpic/..."
    }
  ],
  "omitted_items": 1
}
```

- `items` 的结构与 `NEARBY.1` 相同，另加可选的 `name_en`、`address_en`；最多 25 条，按距离排序。
- `name_en`、`address_en`：只在 `language` 为 `en` 时尽力提供（条目 9 的地点名英译，按地点缓存）；翻译失败时省略，不影响其他字段。
- `omitted_items`：高德返回但缺少必需字段而未列出的条数（大于 0 时才出现）。全部缺字段时返回 `502 supplier_unavailable`。
- 没有结果时 `items` 为空数组。

## 计次与缓存

- 新服务 `amap-metro-nearby.1`（地点类，单独计次）：每人每天 ≤40 次高德调用，所有账号合计 ≤2,000 次，只共用高德合计 ¥500 现金；超出返回 `429 quota_exceeded`。不计入「附近」的每人每天 100 次与合计 3,000 次。
- 每次查询（缓存未命中）调用高德 1 次。
- 按（城市、车站、排序后的类别）缓存 24 小时，所有账号共用；命中不计次、不调用高德。缓存内容只有公开地点信息，不与账号关联。英文名按地点另行缓存。

## 错误

| 状态 | `error` | 含义 |
|---|---|---|
| 400 | `invalid_request` | 请求格式不符 |
| 401 | — | 未登录 |
| 403 | `not_enabled` | 账号不在白名单或服务未开启 |
| 404 | `station_not_found` | 站点表里没有该车站（含高德尚未收录、没有坐标的少数车站） |
| 409 | `request_already_used` | 同一 `request_id` 已用过 |
| 429 | `quota_exceeded` | 每日或合计次数、或高德现金上限用尽 |
| 429 | `rate_limited` | 高德限流 |
| 502 | `supplier_unavailable` | 高德返回异常 |
| 503 | `unavailable` | 记账状态未知，未调用供应商 |
| 504 | `supplier_timeout` | 高德超时 |
