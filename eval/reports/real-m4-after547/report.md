# M4 real rerun after PR532/540

Release disposition: **FAIL**. Product quality: **UNRUN**.

Smoke candidate: `0b89f4909fd166406d8569fa93ab360e0168aa8c`. Fixed6 prerequisite cases: zh3/en3, place+route/weather/fact. Product corpus remains33 paired/11 fixed holdout.

First-round PR531 FAIL and original IDs/unknown fees remain intact. Per JT, its60 adapter-induced RUN UNKNOWN are not a product-quality conclusion. No old action was redispatched and no candidate/attempt was averaged away.

| Case | Language | Prerequisite | Original RUN | Reasons |
|---|---|---|---|---|
| place-route | zh | PASS | df8a342b-fed1-4471-90fd-a0dcc1bf89a8 | [] |
| place-route | en | FAIL | 57baaabd-c256-4d21-afa3-11fd749fc0bb | ['complete_model_continuation_after_tool_missing', 'native_tool_result_not_in_followup_model', 'original_RUN_not_completed', 'required_tool_success_not_proven', 'same_RUN_complete_body_not_delivered'] |
| weather | zh | UNRUN |  |  |
| weather | en | UNRUN |  |  |
| fact | zh | UNRUN |  |  |
| fact | en | UNRUN |  |  |

Full product batch: 0/66 executed. Missing full tasks are UNRUN, not product FAIL or quality PASS.

A smoke PASS requires actual specified tool receipts, a later complete Beijing model receipt and protected same-message/run complete nonempty body. Model-only text or Source links cannot pass. FACT date/region/eligibility UNKNOWN is by design after successful source fetch; actual excerpts are separately required.

Actual billed currency remains UNKNOWN. Conservative holds and complete-receipt token counts do not settle invoices or release unknown reservations.

```json
{
  "call_attempts_by_kind": {
    "model": 12,
    "place": 5,
    "route": 6
  },
  "complete_receipts": {
    "model": 12,
    "place": 5,
    "route": 6
  },
  "unknown_intents": {},
  "model_tokens_from_complete_receipts": {
    "completion_tokens": 2244,
    "prompt_tokens": 36607,
    "total_tokens": 38851
  },
  "conservative_hold_cny": {
    "model": 12,
    "tool": 11
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
    "prompt_tokens": 36607,
    "completion_tokens": 2244,
    "known_receipt_subtotal_cny": "0.0353444",
    "entire_model_estimate_cny": "0.0353444",
    "actual_billed_cny": "UNKNOWN",
    "tool_monetary_cost": "UNKNOWN",
    "exclusions": "Incomplete windows, tools, cache discounts, credits and invoice adjustments are not inferred; UNKNOWN holds stay reserved"
  },
  "actual_billed_cny": "UNKNOWN",
  "note": "Original intents/call attempts; not a claim that every uncertain request reached the vendor. No invoice supplied."
}
```

Shared budget end snapshot (includes earlier M1/B/C, not all attributed to this rerun):

```json
{
  "counts": {
    "model": 190,
    "weather": 57,
    "fact": 10,
    "place": 27,
    "route": 9
  },
  "model_hold_including_M1_cny": 203,
  "tool_hold_cny": 93,
  "raw_snapshot_sha256": "9e939f20a12445b20cdd043c97a6c8e36fd93f3476cb18c63844dcbb46f27167"
}
```

Only development-Mac TCP protected snapshots at200ms polling were measured. api-beta overseas/China target-network phases remain UNRUN until B #30 readiness. Source links are excluded from first-body time; failures are not full answers. No real-user content, extra service, cloud operation, or authorization-file edit by C.

Engineering test/fixture PASS is separate from real smoke and product quality. Original raw HTTP/process files remain outside git; formal audit retains every executed attempt, request hash, receipt state and timing. Unexecuted planned cells are explicit UNRUN.

| Product language | Completion ≥90% | Serious errors 0 | First body p95 ≤5s | Full answer p95 ≤90s |
|---|---|---|---|---|
| zh | UNRUN | UNRUN | UNRUN | UNRUN |
| en | UNRUN | UNRUN | UNRUN | UNRUN |
