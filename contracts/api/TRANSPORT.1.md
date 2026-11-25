# TRANSPORT.1 · 城际交通

`POST /v1/tools/transport/search`，供「工具 → 城际交通」比较两座城市之间的火车和飞机（[#1517](https://github.com/JTCAO515/G2C/issues/1517)）。只读：不下单、不付款，订票在 12306 或 Trip.com 完成。使用现有 App Bearer 和内部测试名单（G2C@01–99）。香港默认关闭，有 Bearer 格式的请求返回 `403 not_enabled`。请求体上限 4 KiB，响应带 `Cache-Control: no-store`。客户端用现有 `X-Request-ID` 关联请求。授权见 `docs/authorizations/M4.md` 条目 11、12④、14（JT 2026-11-25，[#1518](https://github.com/JTCAO515/G2C/issues/1518)）。

## 请求

```json
{"version": "TRANSPORT.1", "origin": "shanghai", "destination": "beijing", "date": "2026-12-03", "modes": ["rail", "flight"]}
```

- `origin`、`destination`：城市 id，取值为 `beijing`、`shanghai`、`guangzhou`、`shenzhen`、`chengdu`、`chongqing`、`xian`、`hangzhou`、`nanjing`、`wuhan`、`guilin`、`kunming`（与 App 的城市表一致），两者必须不同。
- `date`：`YYYY-MM-DD`，Asia/Shanghai 的今天到 60 天后。
- `modes`：`rail`、`flight` 中的一到两个，不重复。大巴没有接口，App 只给静态指引。
- 未知字段、其他取值一律 `400 invalid_request`，并且不调用任何供应商。

## 响应

```json
{
  "version": "TRANSPORT.1",
  "date": "2026-12-03",
  "origin": {"id": "shanghai", "name_zh": "上海", "name_en": "Shanghai"},
  "destination": {"id": "beijing", "name_zh": "北京", "name_en": "Beijing"},
  "rail": {"status": "ok", "source": "AMap", "items": [
    {"number": "G2", "depart_station": {"name_zh": "上海虹桥站", "name_en": "Shanghai Hongqiao Railway Station"},
     "arrive_station": {"name_zh": "北京南站", "name_en": "Beijing South Railway Station"},
     "depart_time": "08:00", "arrive_time": "12:28", "duration_min": 268, "next_day": false,
     "seats": [{"class_zh": "二等座", "class_en": "Second class", "price_cny_minor": 62600}],
     "availability": null}],
    "availability_note_zh": "余票以 12306 为准", "availability_note_en": "Seats left: check on 12306"},
  "flight": {"status": "ok", "source": "VariFlight", "items": [
    {"number": "MU5101", "carrier": {"name_zh": "东方航空", "name_en": "China Eastern"},
     "depart_airport": {"iata": "SHA", "name_zh": "上海虹桥国际机场", "name_en": "Shanghai Hongqiao International Airport"},
     "arrive_airport": {"iata": "PEK", "name_zh": "北京首都国际机场", "name_en": "Beijing Capital International Airport"},
     "depart_time": "07:30", "arrive_time": "09:40", "duration_min": 130, "next_day": false}],
    "price_note_zh": "价格随时变动，以订票页为准", "price_note_en": "Prices change often; check when booking"},
  "links": [
    {"mode": "rail", "provider": "12306", "url": "https://www.12306.cn/en/index.html"},
    {"mode": "rail", "provider": "trip.com", "url": "https://www.trip.com/trains/china/route/shanghai-to-beijing/"},
    {"mode": "flight", "provider": "trip.com", "url": "https://www.trip.com/flights/showfarefirst?dcity=sha&acity=bjs&ddate=2026-12-03&triptype=ow&class=y&quantity=1"}]
}
```

- 只返回请求了的方式。每种方式各自带 `status`：`ok`（有结果）、`empty`（供应商没有结果）、`unavailable`（供应商出错、超时、限流或结果无法校验）、`not_enabled`（这种方式没有配置，或因出现扣费已停用）、`quota_exceeded`（这种方式的额度用完）。某一方式失败不影响另一方式，整次请求仍返回 200。
- 火车：最多 20 条，按出发时间排序，同一车次同一出发时间只保留一条。站名缺「站」时补上；英文站名只在城市表里有时给出。`seats` 只保留 12306 席别代码 `9`、`P`、`M`、`O`、`4`、`3`、`1` 且价格为 0–100000 元、最多两位小数的项，其他席别丢弃，不猜。`availability` 恒为 `null`：本接口不提供余票，客户端必须显示「余票以 12306 为准」。高德只返回所给时间（08:00）附近的少量方案，客户端不得把列表称为全天时刻表。
- 机票：对两城所有机场组合（最多 4 组）查询飞常准航线航班，合并后最多 20 条，按出发时间排序；同一起降机场与时刻的代码共享航班只保留一条；只保留请求当天出发、时间可解析的航班。机场中英名取城市表。暂不返回价格。
- `links` 是公开订票页面。Trip.com 联盟凭据交接后（#1368），服务端可把 Trip.com 链接换成服务端交接链接；联盟 ID 只在服务端，客户端按 #225 显示推广披露。
- `next_day` 为 `true` 表示到达时间是次日；跨越多日的车次按时刻差计算，可能少算整天。

## 额度与停用

Asia/Shanghai 每日按账号计数，鉴权和请求校验通过后、调用供应商前持久预留：

| 计数 | 上限 | 用尽时 |
|---|---|---|
| 路由 `/v1/tools/transport/search` | 每人每天 50 次 | 整次请求 `429 quota_exceeded` |
| 火车 `amap:transit-crosscity` | 每人每天 30 次；所有账号合计 1500 次 | `rail.status = quota_exceeded` |
| 机票（与 `FLIGHTS.1` 路由共用同一计数） | 每人每天 50 次（两处合计） | `flight.status = quota_exceeded` |

每次火车查询调用高德公交路径规划（`/v3/direction/transit/integrated`，跨城）一次，只发送两城市中心坐标、中文城市名和日期。每次机票查询最多调用飞常准 4 次（每组机场一次，各自计入 `variflight:dispatch`），只发送机场代码和日期。不发送账号、手机号或其他身份信息。飞常准返回需要付费（HTTP 402 或 RPC 402）时，与航班插件共用的停用标记立即生效，两处都停止调用飞常准，直到人工确认后移除；此时 `flight.status = not_enabled`。供应商错误信息不回显，响应中出现密钥的结果整体丢弃。

## 错误

整次请求的错误只有：`400 invalid_request`、`401 sign_in_required`、`403 not_enabled`、`413 request_too_large`、`429 quota_exceeded`（路由次数）、`503 unavailable`（本地计数不可用）。错误正文为 `{"error": "<代码>"}`。
