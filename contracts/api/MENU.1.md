# MENU.1 · 点餐：菜单识别与菜品解释

`POST /v1/tools/menu/explain` 使用现有 App Bearer 和内部测试账号白名单（须为 G2C@01–99 的子集，名单与开关由 S 线部署时配置）。香港默认关闭：已带 Bearer 但未开通时返回 `403 not_enabled`。消费方用现有的 `X-Request-ID` 关联请求。范围与额度见授权清单 M4 条目 19 与条目 9 的点餐增补（[#1587](https://github.com/JTCAO515/G2C/pull/1587)），方案与 JT 批准记录见 [#1581](https://github.com/JTCAO515/G2C/issues/1581)。实现：`backend/cj_api/lio_menu.py`；预算：`backend/usage/cj_usage/menu_budget.py`（解释），图片识别记在 `translation_budget.py`（条目 9）。

## 请求

```json
{
  "version": "MENU.1",
  "request_id": "8f14e45f-ceea-4e7a-9c3b-2b0d4c1e9a10",
  "media": "<base64 JPEG 或 PNG>"
}
```

- `request_id`：小写 UUID，每张菜单新生成。同一个 id 不会重复调用供应商，重发返回 `409 request_already_used`。
- `media`：一张菜单照片，JPEG 或 PNG，解码后不超过 3 MB 减 4 KB（与翻译相同）。App 先缩到长边 2048 像素、JPEG 质量 0.8，通常只有几百 KB。
- 请求体（JSON，含 base64）不超过 4 MiB；中转按 6 MiB 设请求体上限，超过直接拒绝，不进服务。
- 只有这三个字段。**不发送**忌口、账号、位置或其他个人信息；多出的字段一律拒绝（400 `invalid_request`）。
- 照片只在本次请求的内存中处理，不落盘，不进日志或账本元数据。

## 处理

1. **识别**（条目 9）：用翻译中转的图片文字识别模型 `qwen-vl-ocr` 识别 1 次，计入翻译账本每人每天图片 ≤50 张与翻译子额度。
2. **分行**：按行切分，先做全角转半角；一行里识别出两道菜时，在两个以上空格、制表符或「价格 + 空格 + 汉字」处再切开；去掉空行、超过 60 个字符的行、含不可见控制字符的行，以及不含汉字的行（纯英文、纯数字）。行尾的价格（如 `¥38`、`26元`、`15/份`、`12.5元/位`）由服务端截下，原样作为 `price_text` 返回，不发给模型，模型也不写价格。整行识别结果只有一个价格的行（如 `38`、`26元`、`30/份`）也不发给模型（同一行里与菜名切开的编号或价格，如 `1 宫保鸡丁`、`¥38 宫保鸡丁`，不算）：识别常把一栏菜名读完再读这一栏的价格，所以连续 k 行纯价格按顺序配给紧挨在它前面、连续 k 行没有自带价格的菜（`dish` 或 `unclear`）；判为其他（`other`，如分类标题）的行、自带价格的行或上一段价格会截断这一段。只要有一段对不上（数量不等，或这一段前面是判为其他的行、自带价格的行或没有行，例如每道菜上方单独印一个编号或价格），整张菜单的纯价格行都不配，`price_text` 为 `null`，因为漏读一个价格或多出一个编号会让后面的价格全部错位；菜名同一行自带的价格照常返回。最多取前 30 行，多出的不处理，`truncated` 为 `true`。
3. **缓存**：按行文字（去空白）加提示词版本查全局缓存；命中的行不再调用模型。缓存只存公开菜品知识（菜名、说明、配料标签），不存照片或任何用户信息。
4. **解释**（条目 19）：未命中的行每 15 行一次，至多 2 次，调用 flash 档 `qwen3.8-flash`（不开思考，JSON 输出，单次输出 ≤6000 tokens；每道菜约 220 tokens）。模型逐行判断是菜（`dish`）、看不清的菜名（`unclear`）还是其他（`other`），菜给出中英说明和配料标签。模型只看到这些行的文字。提示词要求每行恰好一项、字段用短词，并列出隐性配料的对应（酱油→大豆与麸质、蚝油→虾蟹贝类、花生油→花生、猪油→猪肉、高汤与鸡精→肉汤、料酒→酒等），宁可多标「可能」，不要漏。
5. **检查**：
   - `name_zh` 去空白后必须是本行文字中连续的一段，否则这一行改为 `unclear`；
   - `name_en` 必须有；`spice` 只能是 0–3 或 `null`；`contains` 必须是对象，键只收下面 16 种配料（其他键丢弃），值只收 `likely` / `possible`（其他值按 `possible`）。任一不符，这一行改为 `unclear`；
   - 说明类字段超长（中文 >60 字、英文 >160 个字符）、含不可见字符，或含「安全」「不含」「无花生」「safe」「peanut-free」「does not contain」这类保证，就置为空字符串；
   - 模型输出被截断（`finish_reason=length`）或不是约定的 JSON（`items` 不是数组、行号越界或重复、`kind` 不认识、条数多于输入行）时，整个请求返回 `502 supplier_unavailable`，不缓存；已发生的调用照常计费。
   - 模型没有给出的行视为 `other`，不返回，也不缓存。`unclear` 不缓存。

## 响应

```json
{
  "version": "MENU.1",
  "truncated": false,
  "items": [
    {
      "id": "l2",
      "kind": "dish",
      "name_zh": "宫保鸡丁",
      "name_en": "Kung Pao Chicken",
      "summary_en": "Diced chicken stir-fried with peanuts and dried chili.",
      "summary_zh": "鸡丁与花生、干辣椒同炒，酸甜微麻。",
      "ingredients_en": "Chicken, peanuts, dried chili",
      "ingredients_zh": "鸡肉、花生、干辣椒",
      "method_en": "Stir-fried",
      "method_zh": "爆炒",
      "portion_en": "Shared plate, about 2 people",
      "portion_zh": "一盘，约 2 人份",
      "spice": 2,
      "contains": {"poultry": "likely", "peanut": "likely", "soy": "likely", "alcohol": "possible"},
      "price_text": "¥38"
    },
    {"id": "l4", "kind": "unclear", "price_text": null}
  ]
}
```

- `items` 按菜单行的顺序，只含 `dish` 和 `unclear`。`id` 为 `l` 加行号，在一次响应内唯一，App 用它下单。
- `dish`：上例全部字段都在。说明类字段可能是空字符串（App 不显示该行）。`spice`：0 不辣、1 微辣、2 中辣、3 很辣，`null` 为不确定。
- `unclear`：只有 `id`、`kind`、`price_text`。App 显示「看不清，请问服务员」，不做忌口判断，也不能加入点单卡。
- `contains` 的键：`pork`、`beef`、`lamb`、`poultry`、`fish`、`shellfish`、`peanut`、`tree_nut`、`egg`、`dairy`、`gluten`、`soy`、`sesame`、`alcohol`、`coriander`、`animal_broth`。值 `likely` 表示按常见做法通常会用，`possible` 表示常作调料、高汤或点缀。**没有列出不代表不含**：服务端和 App 都不说「安全」或「不含」。
- 忌口比对只在 App 本机进行：过敏一律显示「可能含有××，请向服务员确认」。
- `price_text` 是照片上印的价格原文，没有则为 `null`。

## 计费与额度

- 每张菜单：识别 1 次（条目 9）+ 解释 0–2 次（条目 19）。整张菜单都命中缓存时不调用模型、不计入每天 10 份（与 ROADBOOK.1 相同：条目 19 的「份」以实际发生模型调用的菜单计），识别仍计入每天 50 张图片。
- 每人每个北京日：发生解释调用的菜单 ≤10 份；模型子额度 ¥100，计入 ¥10,000 停止线，用到 80% 后不再接受新菜单。
- 请求开始时先只读检查当天份数与子额度，不够时直接返回 `429 quota_exceeded`，不识别照片。

## 错误

| 状态 | `code` | 含义 |
|---|---|---|
| 400 | `invalid_request` | 请求不符合本契约 |
| 401 | `sign_in_required` | 没有有效登录 |
| 403 | `not_enabled` | 未开通（不在白名单或香港关闭） |
| 409 | `request_already_used` | `request_id` 已用过 |
| 429 | `quota_exceeded` | 今天的菜单份数或图片张数已用完，或点餐子额度已到 80% |
| 502 | `supplier_unavailable` | 识别或解释失败、输出被截断或不合约定 |
| 503 | `unavailable` | 预算账本暂时不可读、已过授权期或超时，未调用后续供应商 |
