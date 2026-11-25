# HOTEL.2 · 酒店搜索

`POST /v1/tools/hotel/search` 使用现有 App Bearer 和内部测试账号白名单（`HOTEL_INTERNAL_SUBJECTS`，须为 G2C@01–99 的子集）。香港默认关闭：已带 Bearer 但未开通时返回 `403 not_enabled`。消费方用现有的 `X-Request-ID` 关联请求。`HOTEL.1` 的 `/v1/tools/hotel/link` 保持关闭。范围与额度见授权清单 M4 条目 12③ 和条目 9（[#1523](https://github.com/JTCAO515/G2C/pull/1523)），方案见 [#1508](https://github.com/JTCAO515/G2C/issues/1508)。

## 请求

```json
{
  "version": "HOTEL.2",
  "request_id": "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10",
  "city": "北京",
  "near": {"query": "王府井"},
  "check_in": "2026-12-03",
  "check_out": "2026-12-05",
  "guests": 2,
  "price_cny": {"min": 300, "max": 600},
  "language": "en"
}
```

- `request_id`：小写 UUID，每次搜索新生成。同一个 id 不会重复调用供应商，重复时返回 `409 request_already_used`。
- `city`：1–100 个可见字符，中英文城市名都可以，常用城市的英文名会换成中文名。
- `near`：可选，区域或地标文字，1–100 个可见字符。
- `check_in`、`check_out`：日期格式 `YYYY-MM-DD`，住 1–30 晚。
- `guests`：1–10。
- `price_cny`：可选。`min`、`max` 是 0–100000 的整数，至少给一个，且 `min ≤ max`。
- `language`：`zh` 或 `en`。
- 未知字段、身份信息和联系方式一律拒绝（400 `invalid_request`）。

## 响应

```json
{
  "version": "HOTEL.2",
  "source": "Gaode",
  "affiliate_links": false,
  "applied_filters": ["near"],
  "unapplied_filters": ["check_in", "check_out", "guests", "price"],
  "items": [
    {
      "id": "B0FFXXXXXX",
      "name_zh": "北京王府井希尔顿酒店",
      "name_en": "Hilton Beijing Wangfujing",
      "address_zh": "王府井东街8号",
      "address_en": "8 Wangfujing East Street",
      "lat": 39.9139, "lng": 116.4127, "coordinate_system": "GCJ-02",
      "rating": "4.7",
      "price_cny": {"min": 980, "max": 980}, "price_kind": "reference",
      "metro": {"name_zh": "王府井站", "distance_m": 367},
      "foreign_guests": "unknown",
      "booking_url": "https://<香港本站>/v1/tools/hotel/out/<handle>"
    }
  ],
  "omitted_items": 1
}
```

- `affiliate_links`：`booking_url` 跳转的 Trip.com 链接是否带联盟标识。只有为 `true` 时，App 才显示推广披露（文案按 #225，由 JT 确认）。第一步不带联盟 ID，所以为 `false`。
- `applied_filters` 与 `unapplied_filters` 合起来正好是 `{near, check_in, check_out, guests, price}`，两者不重叠。App 会把未生效的条件告诉用户。
- `source`：第一步是 `Gaode`，以后可能是 `Trip.com`。来源是 `Gaode` 时 `foreign_guests` 一律为 `unknown`，App 也一律显示「请在 Trip.com 确认」。来源是 `Trip.com` 时可能为 `accepted`、`not_accepted` 或 `unknown`。
- 可选字段缺失时直接省略，不发 `null`：`name_en`、`address_en`（仅英文请求，来自千问英译，失败时省略）、`rating`（字符串）、`price_cny`、`price_kind`、`metro`（最近地铁站在 2 公里以内才给）。`price_kind` 为 `reference` 时是高德参考价，不是实时房价。
- `booking_url` 是香港本站的交接链接，handle 由 22 位 `[A-Za-z0-9_-]` 组成，24 小时内有效，服务重启后失效。打开后 302 到 Trip.com 酒店列表页（带城市、日期、人数，酒店名填在搜索框）。城市不在已核对的列表里时，跳到 Trip.com 酒店首页。联盟 ID 只在香港配置，第一步不带。未知或过期的 handle 返回 404，不跳转到任何外部地址。
- `omitted_items`：被略去的条数，包括缺少名称、坐标或中文地址的行，类型或格式不合规的行，以及重复 `id` 的后续行（保留第一条）；没有略去时省略该字段。
- 同一响应内 `items[].id` 唯一。
- App 内不下单、不付款。预订和付款在 Trip.com 完成。

## 错误与额度

失败响应例如 `{"error":"quota_exceeded"}`。

| 状态 | 代码 | 含义 |
|---|---|---|
| 400 | `invalid_request` | 请求不合规 |
| 401 | `sign_in_required` | 未登录或 Bearer 无效 |
| 403 | `not_enabled` | 未开通 |
| 404 | `place_not_found` | 找不到 `near` 指定的区域或地标 |
| 409 | `request_already_used` | `request_id` 已使用过 |
| 413 | `request_too_large` | 请求体过大 |
| 429 | `quota_exceeded` | 达到额度上限 |
| 429 | `rate_limited` | 供应商限流 |
| 502 | `supplier_unavailable` | 供应商出错 |
| 503 | `unavailable` | 服务暂不可用 |
| 504 | `supplier_timeout` | 供应商超时 |

额度由服务端强制执行（JT 2026-11-25，#1523、#1534）：
- 每个账号每天（上海时间）最多 50 次搜索，按 `request_id` 计。
- 每次搜索最多调用高德 3 次：定位地标、列酒店、搜附近地铁站。
- 与「附近」一样单独计次：酒店搜索的高德调用总共最多 3000 次，不占条目 3 的地点次数，只与其他功能共用工具现金上限 ¥500（JT 2026-11-25 修订，#1534）。
- 同一城市加地标的结果缓存 60 秒，命中缓存时不调用高德，也不计数。
