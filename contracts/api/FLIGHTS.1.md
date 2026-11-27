# FLIGHTS.1 · 航班查询

`POST /v1/tools/flights`，按航班号查某天的航班动态，或按两个机场查某天的航班列表，用飞常准（VariFlight）只读接口（[#2007](https://github.com/JTCAO515/G2C/issues/2007) 大交通「按航班号查询」使用；城际对比里的机票同一供应商，见 `TRANSPORT.1`）。只读：不下单、不付款、不关注航班。使用现有 App Bearer 和内部测试名单（G2C@01–99）。香港默认关闭：只有 `/control/travel-providers.json` 的 `flights_enabled` 为 true 且有 `CJ_VARIFLIGHT_MCP_KEY` 才注册本路由，否则有 Bearer 格式的请求返回 `403 not_enabled`。`transport_enabled` 只开启 `TRANSPORT.1` 的机票模式，两者共用同一个飞常准客户端、每日计数和停用标记；只开 `transport_enabled` 时本路由仍是 `403 not_enabled`。请求体上限 4 KiB，响应带 `Cache-Control: no-store`，客户端用 `X-Request-ID` 关联请求。授权见 `docs/authorizations/M4.md` 条目 14。

## 请求

按航班号：

```json
{"version": "FLIGHTS.1", "date": "2026-12-03", "flight_number": "MU5102"}
```

按机场：

```json
{"version": "FLIGHTS.1", "date": "2026-12-03", "departure": "SHA", "arrival": "PEK"}
```

- `date`：`YYYY-MM-DD`，必须是真实存在的日期（`2026-02-30` 为 `400`）。
- `flight_number`：大写航司代码加数字，正则 `[A-Z0-9]{2,3}[0-9]{1,4}[A-Z]?`；与 `departure`、`arrival` 互斥。
- `departure`、`arrival`：三字母机场代码，必须不同；与 `flight_number` 互斥。
- 两种方式二选一，其他组合、未知字段一律 `400 invalid_request`，并且不调用供应商。

## 响应

```json
{"version": "FLIGHTS.1", "source": "VariFlight", "date": "2026-12-03", "more": false,
 "items": [{"flight_number": "MU5102", "departure": "SHA", "arrival": "PEK", "status": "…",
            "planned_departure": "…", "planned_arrival": "…", "departure_terminal": "T2", "gate": "B2"}]}
```

- 每条只有 `flight_number` 必有，其余字段**有才给**，客户端对缺失一律显示「暂无」，不得猜测：`departure`、`arrival`（机场代码）、`codeshare`（布尔）、`status`、`planned_departure`、`planned_arrival`、`actual_departure`、`actual_arrival`、`departure_terminal`、`arrival_terminal`、`gate`、`check_in_counter`、`baggage_carousel`、`airline_name_zh`、`airline_name_en`、`departure_airport_name_zh/en`、`arrival_airport_name_zh/en`。
- 时间和状态文字**原样转发供应商给的字符串**（长度上限 120，无控制字符）；服务端不换算时区，不翻译。客户端展示时间时应能容忍「完整日期时间」和「只有时分」两种写法，认不出就原文显示。
- `more` 为 `true` 表示供应商给了超过 100 条，只返回前 100 条。单条无法校验的航班被跳过；整个应答有行但一条都不可用时按供应商不可用（`502`）处理；供应商返回 0 行时是 `200` 加空 `items`，不是错误。
- 同一查询 60 秒内走服务端缓存，不再调用供应商，也不再计供应商调用次数，但仍计账号的每日路由次数。

## 额度与错误

- Asia/Shanghai 每日每人 50 次（路由 `/v1/tools/flights`），与 `TRANSPORT.1` 的机票共用同一计数（M4 条目 14：两处合计 50 次）；用尽返回 `429 quota_exceeded`。
- 错误正文 `{"error": "<代码>"}`：`400 invalid_request`、`401 sign_in_required`、`403 not_enabled`、`413 request_too_large`、`429 quota_exceeded`（账号每日次数用尽）、`429 rate_limited`（飞常准自己限流）、`502 supplier_unavailable`、`503 unavailable`（本地计数不可用）、`503 not_enabled`（供应商停用期间，见下）、`504 supplier_timeout`。供应商的错误信息不回显，供应商应答里出现密钥的结果整体丢弃。
- 飞常准返回需要付费（HTTP 402 或 RPC 402）时，与城际机票共用的停用标记立即生效，两处都停止调用，直到人工确认后移除；停用期间（停用标记存在，或香港内测授权校验失败，例如试用期已过）本路由返回 `503 not_enabled`，客户端应当按「暂时不能查询」处理，不要重试。服务端只允许 `getFlightList`、`getFlightStatus` 两个只读工具。

## 隐私

只向飞常准发送航班号或机场代码和日期，不发送账号、手机号或其他身份信息。飞常准已列入隐私政策的数据接收方。

## 未验证

按航班号返回的原始字段名（上面的别名映射）以 `getFlightList` 的实测结果和公开文档为准，`getFlightStatus` 的真实字段未经香港实测；实测由 S 线在冒烟时读一次（L3），字段不符时只改 `variflight_tools.py` 的别名表，本契约的字段名不变。
