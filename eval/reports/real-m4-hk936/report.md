# M4 real rerun after PR532/540

Release disposition: **FAIL**. Product quality: **UNRUN**.

Smoke candidate: `375f47aa2521fab5964ebb8e9d5c1858fda1332c`. Fixed6 prerequisite cases: zh3/en3, place+route/weather/fact. Product corpus remains33 paired/11 fixed holdout.

First-round PR531 FAIL and original IDs/unknown fees remain intact. Per JT, its60 adapter-induced RUN UNKNOWN are not a product-quality conclusion. No old action was redispatched and no candidate/attempt was averaged away.

| Case | Language | Prerequisite | Original RUN | Reasons |
|---|---|---|---|---|
| place-route | zh | PASS | e3091c9d-bbe0-4ac8-9ba0-eb0819d140e5 | [] |
| place-route | en | PASS | da731dc6-2061-4e95-84f6-8fb01e75c345 | [] |
| weather | zh | PASS | f7d1dad9-1166-4f26-b6a8-be42b1f6bead | [] |
| weather | en | PASS | 322c5fee-ffb1-4da4-be37-ee06edd8fdd2 | [] |
| fact | zh | FAIL | 33d99058-3205-4f42-bd72-0472a0b56bda | ['complete_model_continuation_after_tool_missing', 'official_page_excerpt_not_proven', 'original_RUN_not_completed', 'original_operation_receipt_incomplete', 'required_tool_kind_missing', 'same_RUN_complete_body_not_delivered'] |
| fact | en | UNRUN |  |  |

Full product batch: 0/66 executed. Missing full tasks are UNRUN, not product FAIL or quality PASS.

A smoke PASS requires actual specified tool receipts, a later complete Beijing model receipt and protected same-message/run complete nonempty body. Model-only text or Source links cannot pass. FACT date/region/eligibility UNKNOWN is by design after successful source fetch; actual excerpts are separately required.

Actual billed currency remains UNKNOWN. Conservative holds and complete-receipt token counts do not settle invoices or release unknown reservations.

```json
{
  "call_attempts_by_kind": {
    "model": 11,
    "place": 4,
    "route": 2,
    "weather": 2,
    "fact": 1
  },
  "complete_receipts": {
    "model": 11,
    "place": 4,
    "route": 2,
    "weather": 2
  },
  "unknown_intents": {
    "fact": 1
  },
  "model_tokens_from_complete_receipts": {
    "prompt_tokens": 18468,
    "completion_tokens": 3675,
    "total_tokens": 22143
  },
  "token_unknown_model_attempt_n": 0,
  "conservative_hold_cny": {
    "model": 11,
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
    "complete_model_receipts": 11,
    "unknown_model_attempts": 0,
    "prompt_tokens": 18468,
    "completion_tokens": 3675,
    "known_receipt_subtotal_cny": "0.0246969",
    "entire_model_estimate_cny": "0.0246969",
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
    "model": 216,
    "weather": 59,
    "fact": 12,
    "place": 36,
    "route": 13
  },
  "model_hold_including_M1_cny": 229,
  "tool_hold_cny": 108,
  "raw_snapshot_sha256": "6a1ef87f320f0d462591e2b5d37fa9b14b22f9c5423e62395b9a1632ec7d7cfe"
}
```

Recorded measurement environment: {"id": "hk-private-real-exits", "kind": "local_real_services", "client_environment": "HK private Unix PG/original worker", "measurement_scope": "protected loopback snapshot polls at200ms; not a target-network observation"}. No target geography is inferred. Source links are excluded from first-body time; failures are not full answers. Real-user content and authorization-file edits remain prohibited.

Engineering test/fixture PASS is separate from real smoke and product quality. Original raw HTTP/process files remain outside git; formal audit retains every executed attempt, request hash, receipt state and timing. Unexecuted planned cells are explicit UNRUN.

| Product language | Completion ≥90% | Serious errors 0 | First body p95 ≤5s | Full answer p95 ≤90s |
|---|---|---|---|---|
| zh | UNRUN | UNRUN | UNRUN | UNRUN |
| en | UNRUN | UNRUN | UNRUN | UNRUN |
