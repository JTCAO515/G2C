# M4 real rerun after PR532/540

Release disposition: **FAIL**. Product quality: **UNRUN**.

Smoke candidate: `04dd91b28218517ef49cc7f60add34ee975ee9fc`. Fixed6 prerequisite cases: zh3/en3, place+route/weather/fact. Product corpus remains33 paired/11 fixed holdout.

First-round PR531 FAIL and original IDs/unknown fees remain intact. Per JT, its60 adapter-induced RUN UNKNOWN are not a product-quality conclusion. No old action was redispatched and no candidate/attempt was averaged away.

| Case | Language | Prerequisite | Original RUN | Reasons |
|---|---|---|---|---|
| place-route | zh | PASS | bdc3e279-9568-4b4f-87aa-cbbe1ae651df | [] |
| place-route | en | PASS | 457d4177-832f-44e4-9de0-b822f6c091bf | [] |
| weather | zh | PASS | 28e24175-5f1e-43c6-9696-a96362fd62e1 | [] |
| weather | en | FAIL | 3f2efc4c-23e7-4cfa-935d-05d776d429b7 | ['complete_model_continuation_after_tool_missing', 'original_RUN_not_completed', 'original_operation_receipt_incomplete', 'same_RUN_complete_body_not_delivered'] |
| fact | zh | UNRUN |  |  |
| fact | en | UNRUN |  |  |

Full product batch: 0/66 executed. Missing full tasks are UNRUN, not product FAIL or quality PASS.

A smoke PASS requires actual specified tool receipts, a later complete Beijing model receipt and protected same-message/run complete nonempty body. Model-only text or Source links cannot pass. FACT date/region/eligibility UNKNOWN is by design after successful source fetch; actual excerpts are separately required.

Actual billed currency remains UNKNOWN. Conservative holds and complete-receipt token counts do not settle invoices or release unknown reservations.

```json
{
  "call_attempts_by_kind": {
    "model": 10,
    "place": 4,
    "route": 2,
    "weather": 2
  },
  "complete_receipts": {
    "model": 9,
    "place": 4,
    "route": 2,
    "weather": 2
  },
  "unknown_intents": {
    "model": 1
  },
  "model_tokens_from_complete_receipts": {
    "prompt_tokens": 17798,
    "completion_tokens": 2528,
    "total_tokens": 20326
  },
  "token_unknown_model_attempt_n": 1,
  "conservative_hold_cny": {
    "model": 10,
    "tool": 8
  },
  "token_price_estimate": {
    "currency": "CNY",
    "basis": "estimated_public_price_not_billed",
    "source": "https://help.aliyun.com/zh/model-studio/qwen3-8-flash",
    "source_as_of": "2026-11-05",
    "model": "qwen3.8-flash",
    "region": "cn-beijing",
    "input_per_million": "0.8",
    "output_per_million": "2.7",
    "complete_model_receipts": 9,
    "unknown_model_attempts": 1,
    "prompt_tokens": 17798,
    "completion_tokens": 2528,
    "known_receipt_subtotal_cny": "0.021064",
    "entire_model_estimate_cny": null,
    "actual_billed_cny": "UNKNOWN",
    "tool_monetary_cost": "UNKNOWN",
    "exclusions": "Incomplete windows, tools, cache discounts, credits and invoice adjustments are not inferred; UNKNOWN holds stay reserved"
  },
  "actual_billed_cny": "UNKNOWN",
  "note": "Original authorization/call attempts; not every uncertain intent is proven sent. No invoice supplied."
}
```

Shared budget end snapshot (includes earlier M1/B/C, not all attributed to this rerun):

```json
{
  "counts": {
    "model": 232,
    "weather": 61,
    "fact": 14,
    "place": 42,
    "route": 15
  },
  "model_hold_including_M1_cny": 245,
  "tool_hold_cny": 118,
  "raw_snapshot_sha256": "9edf63df0f749e0bb7b94c0355af66574b60d72f3ad6d63a9e5842e08f24b69a"
}
```

Recorded measurement environment: {"id": "hk-private-real-exits", "kind": "local_real_services", "client_environment": "HK private Unix PG/original worker", "measurement_scope": "protected loopback snapshot polls at200ms; not a target-network observation"}. No target geography is inferred. Source links are excluded from first-body time; failures are not full answers. Real-user content and authorization-file edits remain prohibited.

Engineering test/fixture PASS is separate from real smoke and product quality. Original raw HTTP/process files remain outside git; formal audit retains every executed attempt, request hash, receipt state and timing. Unexecuted planned cells are explicit UNRUN.

| Product language | Completion ≥90% | Serious errors 0 | First body p95 ≤5s | Full answer p95 ≤90s |
|---|---|---|---|---|
| zh | UNRUN | UNRUN | UNRUN | UNRUN |
| en | UNRUN | UNRUN | UNRUN | UNRUN |
