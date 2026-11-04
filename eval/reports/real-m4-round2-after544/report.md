# M4 real rerun after PR532/540

Release disposition: **FAIL**. Product quality: **UNRUN**.

Smoke candidate: `1ccd44e1acb3aefb212de3449f78e50e9853fc7a`. Fixed6 prerequisite cases: zh3/en3, place+route/weather/fact. Product corpus remains33 paired/11 fixed holdout.

First-round PR531 FAIL and original IDs/unknown fees remain intact. Per JT, its60 adapter-induced RUN UNKNOWN are not a product-quality conclusion. No old action was redispatched and no candidate/attempt was averaged away.

| Case | Language | Prerequisite | Original RUN | Reasons |
|---|---|---|---|---|
| place-route | zh | FAIL | 2ea137ca-7836-4d17-a86a-1527ff8f709f | ['original_RUN_not_completed', 'required_tool_kind_missing', 'required_tool_success_not_proven', 'same_RUN_complete_body_not_delivered'] |
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
    "model": 5,
    "place": 2,
    "route": 2
  },
  "complete_receipts": {
    "model": 5,
    "place": 2,
    "route": 2
  },
  "unknown_intents": {},
  "model_tokens_from_complete_receipts": {
    "completion_tokens": 686,
    "prompt_tokens": 10527,
    "total_tokens": 11213
  },
  "conservative_hold_cny": {
    "model": 5,
    "tool": 4
  },
  "actual_billed_cny": "UNKNOWN",
  "note": "Original intents/call attempts; not a claim that every uncertain request reached the vendor. No invoice supplied."
}
```

Shared budget end snapshot (includes earlier M1/B/C, not all attributed to this rerun):

```json
{
  "counts": {
    "model": 174,
    "weather": 57,
    "fact": 10,
    "place": 20,
    "route": 2
  },
  "model_hold_including_M1_cny": 187,
  "tool_hold_cny": 79,
  "raw_snapshot_sha256": "2b2e0b3399bc1791e74758a1750499f77a6cc9218fdb6b969deac9ae80e9c988"
}
```

Only development-Mac TCP protected snapshots at200ms polling were measured. api-beta overseas/China target-network phases remain UNRUN until B #30 readiness. Source links are excluded from first-body time; failures are not full answers. No real-user content, extra service, cloud operation, or authorization-file edit by C.

Engineering test/fixture PASS is separate from real smoke and product quality. Original raw HTTP/process files remain outside git; formal audit retains every executed attempt, request hash, receipt state and timing. Unexecuted planned cells are explicit UNRUN.

| Product language | Completion ≥90% | Serious errors 0 | First body p95 ≤5s | Full answer p95 ≤90s |
|---|---|---|---|---|
| zh | UNRUN | UNRUN | UNRUN | UNRUN |
| en | UNRUN | UNRUN | UNRUN | UNRUN |
