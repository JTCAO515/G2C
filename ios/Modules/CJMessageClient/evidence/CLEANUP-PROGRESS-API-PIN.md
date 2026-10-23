# Shared current-account cleanup-progress SDK candidate

Exact parent6936a632ecc5cdbfd615b80c75312a09ed64b23a on existing shared owner branch.
Fixed producerf87a78a9d8984c59905e385483f17dddd8144d8a; read its CLEANUP-PROGRESS-WIRE.md,
authoritative OpenAPI and actual generated inputs. Source/root review remain independent;
this is an export/consumer compatibility candidate, not real deletion/I acceptance.

One candidate path:
`ios/Modules/CJMessageClient/.generated/f87a78a9d8984c59905e385483f17dddd8144d8a/CJFoundation`

Existing prepare mechanism exports16 exact official inputs, hashes in generated-pin.json.
Against33, all25 old paths and90 old component schemas exactly equal; SDK manifest/lock/
Memory datehelper byte-identical. All eight older inventories preserved. One actual
standalone CJFoundation graph location, no alternate SDK or other consumer manifest edits.
Transport94 remains byte-exact SHA256 fe1b002d25e56290e7518b96110ff5a17440d304436bfca4842a4a4be6c76472.
No business source, permissions, write activation or current App graph change.

New GET /v1/account-cleanup-progress, getCurrentAccountCleanupProgress, takes ONLY the
existing original operation_id and returns required nonnull progress. Fixed contract is
current ALLOWED account only: no postlogout credentials/capability path, create/recover/
retry/import receipt/hook/delete operation. A complete status concerns only its original
frozen metadata operation, never universal physical account deletion or production success.
This SDK export creates no cleanup actor, runtime client UI or authority to perform one.

PASS: standalone Swift6.4/macOS compile plus five targeted methods, not a full old suite:
three new current-account GET/codec checks + original Host rejection + original usage
association GET regression. Generated method runs ONLY through an in-process interceptor;
GET/no body/original operation query retained. blocked/pending/hook-unavailable remains
blocked; unknown state remains unknown. Six status enum values and five step-state enum
values exist. Missing/null progress, undeclared status and extra private scope reject.
503 CLEANUP_PROGRESS_UNAVAILABLE stays BASE unknown/retry_safe_read with one request,
not successful empty/complete, no automatic recovery/hook/permission restoration.

Fixtures are metadata-only and synthetic; decoding does not prove actual current AUTH,
strict close/domain guard/registry coverage, semantic status combinations, numeric/array
bounds, full physical cleanup, offline/backup completion or caller ownership. Future
consumer must apply fixed binding/trace/semantic/UI rules; this patch adds none. Only
actual root/producer layers may establish those claims under their separate evidence.

Resolved SDK states match existing locks; no upgrade. Temporary standalone resolution
preserved only in ignored .build/cleanup-progress-pin-evidence then source lock restored.
Exact source/log/version metadata in cleanup-progress-api-pin-provenance.json; concise
output cleanup-progress-api-pin-tests.txt. No real account/network/Keychain/PG/service,
root lock/API edit, signing, push, merge or deployment. Full App coordination, independent
double review and original cleanup I remain pending; existing gates/HOLD unchanged.
