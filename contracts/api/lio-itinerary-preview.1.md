# Lio 只读行程预览

`GET /v2/lio/itinerary-preview?conversation_id=…&message_id=…`

请求使用与 `/v2/lio/timeline` 相同的认证。两个参数都必填。结果属于当前账号、活跃会话和原消息，响应禁用缓存。找不到对应原消息或会话不匹配时返回 404。未认证、拒绝访问和依赖故障沿用 Lio 读取错误语义。

```json
{
  "version": "LIO-itinerary-preview.1",
  "conversation_id": "lio-dialogue-00000000000000000000000000000000",
  "message_id": "original-message",
  "preview": {
    "destination": null,
    "days": [
      {"day_index": 1, "activities": [{"place_name": "Forbidden City", "cancelled": false}]}
    ]
  }
}
```

`preview` 是原 RUN 同时用于生成可见正文的逐日活动。天序从 1 开始连续排列。当前仅支持无日期的只读建议，返回的是推荐活动，`cancelled` 为 `false`。这个版本的生产端尚无可信的逐项行政区，所以 `destination` 为 `null`，活动省略 `city_adcode`。字段为以后有可信来源的结果预留，消费方按单项证据判断城市归属。

当原 RUN 正在执行、结算未确认、逐日结构缺失或无效，或可见正文不匹配时，`preview` 为 `null`。正文继续使用原对话结果。旧消息和正式保存的 Trip 也可返回 `null`。此读取不调用模型，不保存或修改 Trip。
