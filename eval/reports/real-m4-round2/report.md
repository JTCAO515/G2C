# M4 real rerun after PR532/540

Release disposition: **FAIL**. Product quality: **UNRUN**.

Smoke candidate: `b13f141306d0edc310d4691b4e19166cff987f49`. Fixed6 prerequisite cases: zh3/en3, place+route/weather/fact. Product corpus remains33 paired/11 fixed holdout.

First-round PR531 FAIL and original IDs/unknown fees remain intact. Per JT, its60 adapter-induced RUN UNKNOWN are not a product-quality conclusion. No old action was redispatched and no candidate/attempt was averaged away.

| Case | Language | Prerequisite | Original RUN | Reasons |
|---|---|---|---|---|
| place-route | zh | FAIL | 482e9130-3aaf-4057-9f7d-a73f24bedef2 | ['complete_model_continuation_after_tool_missing', 'original_RUN_not_completed', 'original_operation_receipt_incomplete', 'required_tool_kind_missing', 'same_RUN_complete_body_not_delivered'] |
| place-route | en | UNRUN |  |  |
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
    "model": 1
  },
  "complete_receipts": {},
  "unknown_intents": {
    "model": 1
  },
  "model_tokens_from_complete_receipts": {},
  "conservative_hold_cny": {
    "model": 1,
    "tool": 0
  },
  "actual_billed_cny": "UNKNOWN",
  "note": "Original intents/call attempts; not a claim that every uncertain request reached the vendor. No invoice supplied."
}
```

Shared budget end snapshot (includes earlier M1/B/C, not all attributed to this rerun):

```json
{
  "counts": {
    "model": 167,
    "weather": 57,
    "fact": 10,
    "place": 17
  },
  "model_hold_including_M1_cny": 180,
  "tool_hold_cny": 74,
  "raw_snapshot_sha256": "fbb879e29b59d1cad2e8e2c43d254020e87b41d60a9a48d9febbb5706ff0ec6a"
}
```

Only development-Mac TCP protected snapshots at200ms polling were measured. api-beta overseas/China target-network phases remain UNRUN until B #30 readiness. Source links are excluded from first-body time; failures are not full answers. No real-user content, extra service, cloud operation, or authorization-file edit by C.

Engineering test/fixture PASS is separate from real smoke and product quality. Original raw HTTP/process files remain outside git; formal audit retains every executed attempt, request hash, receipt state and timing. Unexecuted planned cells are explicit UNRUN.

| Product language | Completion ≥90% | Serious errors 0 | First body p95 ≤5s | Full answer p95 ≤90s |
|---|---|---|---|---|
| zh | UNRUN | UNRUN | UNRUN | UNRUN |
| en | UNRUN | UNRUN | UNRUN | UNRUN |
