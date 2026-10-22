# Single shared CJAPI readonly manual-preview candidate

Exact parent540da02a335e96e98917ffd3d94a395f8ca2d892, existing cj-009-memory-api-pin
branch/tree and original module Package/prepare/export/test/evidence scope.
Fixed producerc5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a; read that commit's
backend/cj_api/MANUAL-PREVIEW-WIRE.md and actual generated types. Root source is in
independent review, not a merged/accepted/runtime-complete claim. Later producer PG
receipts are separate evidence and do not cause another source export.

One candidate location:
`ios/Modules/CJMessageClient/.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation`

Existing preparation mechanism exports16 exact official files; all hashes in generated-pin.json.
Oldc02/201156/d688/9dc/573 inventories rehashed byte-identical. One actual standalone
CJFoundation graph location; no alternate SDK/package identity. Original SDK manifest,
lock and Memory datehelper bytes unchanged, no dependency version upgrade. Againstc02,
all22 prior paths and81 prior component schemas remain exact; only readonly preview
operation and five corresponding schema types are added. No business source modified.

New operation previewManualTripEdit is HTTP POST but only readonly computation in its
producer contract. This module references/compiles it and NEVER invokes it. No change to
current live POST/PUT prohibition, Trip write/confirmation/Proposal, feasibility, protection
provider, default permissions or App pin. An encoded LOCAL preview never means saved.

PASS: standalone Swift6.4/macOS compilation; three new ManualPreviewExportTests plus
three targeted old smoke checks (Memory configuration, Trip methods, original message
query receipt/null). Prior broad business evidence reused, full41 suite NOT rerun.
New checks preserve original content base64 through official request codec; required
title/order presence and actual null; original Trip/diff JSON-value bytes; LOCAL plus
UNKNOWN protection and can_save=false; required preview; exact fixed BASE409 conflict /
503 unknown recovery types cannot decode as preview success. All fixtures synthetic,
with no transport invocation, live request, service, Keychain or PG use.

Important exact generated limitation: ManualPreview.can_save is Swift Bool; the decoder
does not enforce JSON Schema const:false. Test decodes an injected true flag and its
explicit TEST-ONLY no-save assertion rejects it. Actual preview consumer MUST independently
require LOCAL/UNKNOWN/!can_save before displaying a valid readonly preview, and must never
derive write authority from this DTO. Likewise nullable fallback must mean actual nil,
not any case2 value. No production preview consumer/guard was added by this export slice.
Root's producer validation and later client/UI validation remain separately owned.

Concise output manual-preview-api-pin-tests.txt; exact compiler/SDK/source/log hashes in
manual-preview-api-pin-provenance.json; raw log and temporary standalone resolution kept
under ignored .build/manual-preview-pin-evidence. All resolved versions match prior fixed
SDK locks. Automatic standalone lock expansion restored to source base; no root/shared
lock changes. No other consumer package or active App graph changed; combined App is UNRUN
until Main coordinates same-pin consumers. Existing69d/b868 HOLD unaffected. No push,
PR, signing, deployment, actual POST, business network, credentials or new resource access.
