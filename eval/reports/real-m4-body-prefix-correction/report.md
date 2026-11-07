# M4 real rerun after PR532/540

Release disposition: **FAIL**. Product quality: **UNRUN**.

Smoke candidate: `e3b36c39b637f564a369e91ca559bcf4d64c0f79`. Fixed6 prerequisite cases: zh3/en3, place+route/weather/fact. Product corpus remains33 paired/11 fixed holdout.

First-round PR531 FAIL and original IDs/unknown fees remain intact. Per JT, its60 adapter-induced RUN UNKNOWN are not a product-quality conclusion. No old action was redispatched and no candidate/attempt was averaged away.

| Case | Language | Prerequisite | Original RUN | Reasons |
|---|---|---|---|---|
| place-route | zh | PASS | 75ed703f-eaa9-4730-98cd-40f2dcbc7ec3 | [] |
| place-route | en | PASS | 9fcd94e8-1df4-4d49-aa4b-82086d1c7ebe | [] |
| weather | zh | PASS | 955134d3-4d7e-4710-b8b7-e952003e2213 | [] |
| weather | en | PASS | ff6a623e-dbb0-4d6a-869e-1062b365bb7c | [] |
| fact | zh | FAIL | f016657e-e2c1-45e3-992b-ab26c8173c9e | ['same_RUN_complete_body_not_delivered'] |
| fact | en | UNRUN |  |  |

Full product batch: 0/66 executed. Missing full tasks are UNRUN, not product FAIL or quality PASS.

A smoke PASS requires actual specified tool receipts, a later complete Beijing model receipt and protected same-message/run complete nonempty body. Model-only text or Source links cannot pass. FACT date/region/eligibility UNKNOWN is by design after successful source fetch; actual excerpts are separately required.

Actual billed currency remains UNKNOWN. Conservative holds and complete-receipt token counts do not settle invoices or release unknown reservations.

```json
{
  "call_attempts_by_kind": {
    "model": 12,
    "place": 4,
    "route": 2,
    "weather": 2,
    "fact": 1
  },
  "complete_receipts": {
    "model": 12,
    "place": 4,
    "route": 2,
    "weather": 2,
    "fact": 1
  },
  "unknown_intents": {},
  "model_tokens_from_complete_receipts": {
    "prompt_tokens": 19126,
    "completion_tokens": 2792,
    "total_tokens": 21918
  },
  "token_unknown_model_attempt_n": 0,
  "conservative_hold_cny": {
    "model": 12,
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
    "complete_model_receipts": 12,
    "unknown_model_attempts": 0,
    "prompt_tokens": 19126,
    "completion_tokens": 2792,
    "known_receipt_subtotal_cny": "0.0228392",
    "entire_model_estimate_cny": "0.0228392",
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
    "model": 266,
    "weather": 67,
    "fact": 15,
    "place": 54,
    "route": 21
  },
  "model_hold_including_M1_cny": 279,
  "tool_hold_cny": 142,
  "raw_snapshot_sha256": "115f7ae3c8a80ae3f824cab1230f873c76ffb80da2ee688db145f347c2c8a73c"
}
```

Recorded measurement environment: {"id": "hk-private-real-exits", "kind": "local_real_services", "client_environment": "HK private Unix PG/original worker", "measurement_scope": "protected loopback snapshot polls at200ms; not a target-network observation"}. No target geography is inferred. Source links are excluded from first-body time; failures are not full answers. Real-user content and authorization-file edits remain prohibited.

Engineering test/fixture PASS is separate from real smoke and product quality. Original raw HTTP/process files remain outside git; formal audit retains every executed attempt, request hash, receipt state and timing. Unexecuted planned cells are explicit UNRUN.

| Product language | Completion ≥90% | Serious errors 0 | First body p95 ≤5s | Full answer p95 ≤90s |
|---|---|---|---|---|
| zh | UNRUN | UNRUN | UNRUN | UNRUN |
| en | UNRUN | UNRUN | UNRUN | UNRUN |
