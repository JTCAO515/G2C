# ROADBOOK.1 · 路书地点内容补充

`POST /v1/tools/roadbook/places` 使用现有 App Bearer 和内部测试账号白名单（`ROADBOOK_INTERNAL_SUBJECTS`，须为 G2C@01–99 的子集）。香港默认关闭：已带 Bearer 但未开通时返回 `403 not_enabled`。消费方用现有的 `X-Request-ID` 关联请求。范围与额度见授权清单 M4 条目 18（[#1529](https://github.com/JTCAO515/G2C/pull/1529)、[#1542](https://github.com/JTCAO515/G2C/pull/1542)、[#1566](https://github.com/JTCAO515/G2C/pull/1566)），方案见 [#1509](https://github.com/JTCAO515/G2C/issues/1509)。实现：`backend/cj_api/lio_roadbook.py`，预算 `backend/usage/cj_usage/roadbook_budget.py`。

## 请求

```json
{
  "version": "ROADBOOK.1",
  "request_id": "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10",
  "places": [
    {"id": "d1s2", "name_zh": "故宫博物院", "name_en": "Palace Museum", "city": "北京"},
    {"id": "d2s1", "name_zh": "慕田峪长城", "city": "北京", "poi_id": "B000A7BM4H"}
  ]
}
```

- `request_id`：小写 UUID，每次补充新生成。同一个 id 不会重复调用供应商，重复时返回 `409 request_already_used`。
- `places`：1–20 个，`id` 在请求内唯一，只能用字母、数字和 `._-`，1–64 个字符（App 用行程里的站点 id）。
- `name_zh`：中文地点名，必填；`name_en`：可选；`city`：中文城市名。都是 1–100 个可见字符（城市 1–50 个）。
- `poi_id`：可选，已知的高德 POI；有它时用地点详情识别，没有时用「名称 + 城市」文本搜索识别，二者只用其一。
- 只发送公开地点名和城市。地址、坐标、账号、行程标题、用户备注等字段一律拒绝（400 `invalid_request`）。

## 响应

```json
{
  "version": "ROADBOOK.1",
  "places": [
    {
      "id": "d1s2",
      "status": "ready",
      "poi_id": "B000A8UIN8",
      "content": {
        "zh": {
          "summary": "明清两代的皇宫，现为博物院。",
          "why_go": "中轴线上规模最大的古建筑群。",
          "time_needed": "约 3 小时",
          "hours_booking": "周二至周日 08:30-17:00；需提前实名预约，以官方为准。",
          "tickets": "约 40–60 元，以官方为准。",
          "getting_there": "地铁 1 号线天安门东站，步行约 10 分钟。",
          "food_tip": "附近的四季民福烤鸭店可以吃烤鸭。",
          "notes": "入口安检，带好护照；周一通常闭馆。"
        },
        "en": {"summary": "…", "why_go": "…", "time_needed": "…", "hours_booking": "…",
               "tickets": "…", "getting_there": "…", "food_tip": "…", "notes": "…"}
      },
      "metro": [{"name_zh": "天安门东站", "distance_m": 620}],
      "restaurants": [
        {"name_zh": "四季民福烤鸭店(故宫店)", "address_zh": "东华门大街32号",
         "lat": 39.913, "lng": 116.403, "distance_m": 450}
      ]
    },
    {"id": "d2s1", "status": "limited"}
  ]
}
```

- 顺序与请求相同，每个 `id` 一项。`status`：
  - `ready`：有 `poi_id`、`content.zh`、`content.en`（八个字段都在）、`metro`（0–2 个）、`restaurants`（0–3 个）。
  - `limited`：今天的补充额度已用完，或路书子额度已用到 80%（只读缓存）。App 只显示行程已有的内容，不重试。
  - `unavailable`：高德没找到这个地点，或这次生成没有通过检查。App 照常显示行程已有内容，可以稍后再试。
- 八个字段：`summary` 一句话简介、`why_go` 为什么值得去、`time_needed` 建议停留时长、`hours_booking` 开放时间与预约方式、`tickets` 门票约数、`getting_there` 怎么到达、`food_tip` 周边餐饮、`notes` 注意事项。中文每项不超过 120 字，英文不超过 320 个字符。
- 每个字段都经过服务端检查，没通过的字段换成 `以官方为准。`（英文 `Check official sources.`），其余字段照常返回：
  - 价格只能出现在 `tickets`，并且必须是「约 / about」加区间；
  - 不能出现「今天 / today」与「开放、营业、闭馆 / open、closed」的组合；
  - 时刻（如 08:30）只能出现在 `hours_booking`，并且必须与高德给的开放时间一致；
  - `food_tip` 里的店名只能是 `restaurants` 中的名字（可省略括号里的分店名）。
- `metro`、`restaurants` 直接来自高德周边搜索，按距离排序；`restaurants` 只收有中文地址的店，坐标为 GCJ-02，App 可以用它们「打车去这里」和「给司机看」。
- 模型输出被截断（`finish_reason=length`）或不是约定的 JSON 时，这个地点为 `unavailable`，不缓存；已发生的调用照常计费。

## 缓存与计费

- 按地点缓存公开内容（`poi_id`，没有 POI 时为「城市 + 中文名」，加提示词版本），不存任何账号信息。命中缓存的地点不调用高德或模型。
- **整个请求都命中缓存时不计费，也不计入每天 5 本**（M4 条目 18 的「路书」以实际发生模型调用的请求计）。
- 未命中的地点：高德识别 1 次（详情或文本搜索）+ 周边 1 次，模型中文、英文各 1 次（flash，不开思考，单次输出 ≤1000 tokens）。
- 每人每个北京日：新补充地点 ≤60、发生调用的请求 ≤5、高德 ≤120 次；高德合计 ≤2000 次，只共用高德 ¥500 现金；模型子额度 ¥300，计入 ¥10,000 停止线，用到 80% 后只读缓存。超出时相关地点为 `limited`。

## 错误

| 状态 | `code` | 含义 |
|---|---|---|
| 400 | `invalid_request` | 请求不符合本契约 |
| 401 | `sign_in_required` | 没有有效登录 |
| 403 | `not_enabled` | 未开通（不在白名单或香港关闭） |
| 409 | `request_already_used` | `request_id` 已用过 |
| 503 | `unavailable` | 预算账本暂时不可读，未调用任何供应商 |
