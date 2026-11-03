# CLEANUP-DEVICE-COMPLETION@2

Additive replacement for new DEVICE4 consumers of merged A480's two erasure
journals. COMPLETION1 remains exclusively DEVICE3 for A453 until migration;
its frozen semantics and consumers remain unchanged.

`GET /v2/cleanup-device-completions/{original_invocation_id}?request_digest=<original_call_sha256>`
uses `Authorization: Device <original_device_token>` for DEVICE4 only. The
exact response fields, bounded4096-byte read-only snapshot, original receipt,
account inventory/result/registry proof, lifetime/close checks, no business
access and all refusal rules in [COMPLETION1](DEVICE-COMPLETION-V1.md) apply,
with `version:"CLEANUP-DEVICE-COMPLETION@2"` and the original DEVICE4 binding,
descriptor and authenticated receipt. No additional selectors/credentials,
writes, hooks, resume, capability issuance or native finalization are added.

Positive: the own DEVICE4 call's confirmed receipt plus independently complete
frozen online domains returns their exact original evidence. Negative: DEVICE3
credential on this route, DEVICE4 on COMPLETION1, foreign binding/hash/purpose,
expiry, corrupt original evidence or registry drift reject; confirmed device
with unfinished content stays unknown/blocked. This never upgrades an old call
or treats Python/device status as native, backup or all-device erasure proof.
