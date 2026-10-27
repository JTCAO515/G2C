# MESSAGE-SEND@1：发送许可与发送状态

决策依据：[ADR-0008](../../docs/adr/0008-message-send-permit.md)。本文件冻结 wire 形状与判定语义；正式 OpenAPI 由 #163 按本文写入 `contracts/api/openapi.json`。
正负样例：[send-permit-samples.json](send-permit-samples.json)；参考检查：[check_send_permit.py](check_send_permit.py)（进入 `scripts/test.py`）。

状态：随 ADR-0008 一起冻结（JT 批准后生效）。改动按 `docs/contracts.md` 的版本规则走新版本。

## 1. 提交：`POST /v1/messages`

请求体是原始 UTF-8 JSON 字节（`application/octet-stream`），字段**恰好**为：

| 字段 | 类型 | 规则 |
|---|---|---|
| `version` | string | 必须为 `"MESSAGE-send.1"` |
| `conversation_id` | string | 非空白，≤ 256 字节，不含 NUL |
| `message_id` | string | 非空白；作用域内唯一，是幂等键 |
| `text` | string | 非空白 |
| `trip_id` | null | 必须为 `null`（非空 Trip 待 CJ-015/016） |
| `creation_intent` | string | `none` 或 `consider_trip` |
| `expected_generation` | string | 非空白；来自服务端读到的会话头 |
| `expected_sequence` | integer | ≥ 0；JSON 整数，不接受 `1.0`、字符串或布尔值 |

此外，下列请求一律拒绝：

- 有重复 key 的；
- 有未知字段的；
- 缺少字段的；
- `version` 为 `MESSAGE-draft.1` 的，包括重放。

所有拒绝都返回 400 `INVALID_INPUT`。

服务端判定顺序：

1. **按 `message_id` 查回执**：同字节返回 200 和原回执；不同字节返回 409 `INPUT_CONFLICT`。
2. **会话不可用**（不存在、他人、已关闭）：返回现有 unavailable 响应，不区分原因。
3. **会话头不等于预期值**：返回 409 `SEQUENCE_CONFLICT`，`category = conflict`，`outcome = failed`，`recovery = reconcile_original`。
4. **相等**：接收，`sequence = expected_sequence + 1`，回执、原字节和投递义务在同一事务内写入。

第 1 步在第 3 步之前。所以结果未知的请求原样重放，即使会话头已经因为它前进了，仍然拿回原回执。

## 2. 发送状态：`GET /v1/message-send-status`

查询参数：

- `conversation_id`（必填）；
- `message_id`（可选）。

响应：

```json
{
  "request_id": "<RequestId>",
  "receipt": "<MessageReceipt> | null",
  "head": {"conversation_id": "...", "generation": "...", "last_sequence": 0}
}
```

字段语义：

- `head` 为 `null`：会话不可用。他人的、不存在的、已关闭的会话都返回 `null`，不可区分。
- `receipt`：按当前作用域查 `message_id`；未提供 `message_id` 或查不到时为 `null`。
- `receipt` 与 `head` 必须来自**同一读事务**。
- 认证失败按现有 401/403/503 规则处理，**不能**返回 `head = null`。

## 3. 判定表（客户端）

预期值为 `(g, s)` 的消息 M，原字节哈希为 `h`。每行对应 `check_send_permit.py` 里的 `classify` 函数：

| receipt | head | 判定 |
|---|---|---|
| 非空，`input_sha256 == h` | 任意 | `accepted` |
| 非空，`input_sha256 != h` | 任意 | `integrity_error` |
| null | null | `not_accepted` |
| null | `generation != g` | `not_accepted` |
| null | `last_sequence > s` | `not_accepted` |
| null | `(g, s)` | `resubmit_original` |
| null | `last_sequence < s` | `resync_required` |

动作约束：

- `resubmit_original`：只允许原 `message_id` 和原字节。
- `not_accepted`：之后只能由用户发起新消息，换新 `message_id`，并以当前会话头为预期值。
- `integrity_error`、`resync_required`：停止该会话的发送。

## 4. 不变量（#163 必须用 PG 测试证明）

1. 同一 `(scope, conversation_id, generation, sequence)` 最多一条回执（已有唯一约束）。
2. 两条预期值相同、`message_id` 不同的并发请求，恰好一条成功，另一条得到 `SEQUENCE_CONFLICT`。
3. 同一个请求重复 N 次（包括与它并发的重放），只产生一条回执和一个运行。
4. 会话头越过 `s` 后，任何带 `expected_sequence = s` 的新 `message_id` 都不会再被接受。
5. 账号 B 对账号 A 的 `conversation_id`、`message_id` 调用发送状态，得到 `receipt = null`、`head = null`，与不存在时无法区分。
