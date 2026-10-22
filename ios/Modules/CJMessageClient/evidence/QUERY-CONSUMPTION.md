# Fixed generated query consumption

Delta parent e298734196a7ab0b84db3ac83874f015c1e0df25.
Official CJ005 source 312a69caf0bd97ed65679cfd8ff049972c212cef (parent d886677),
not a merged/independently accepted claim. Exact ios package export is versioned under
.generated/312a69caf0bd97ed65679cfd8ff049972c212cef/CJFoundation; old export retained.
prepare_generated.py pins this commit, generated-pin.json records file hashes. No
manual generated edits, substitute Codable wire model, or moving-source import.

Consumption confirmed from actual generated MessageReceiptQueryResponse:
receipt is required, nonoptional receiptPayload; .MessageReceipt(value) uses generated
six-field receipt; .case2(container) is accepted as notObserved ONLY when container.value
is nil. Arbitrary non-null fallback throws invalidResponse and retains queryRequired.
Missing property is DecodingError.keyNotFound(receipt), converted by transport to safe
exchangeUnknown, never empty/null. Normal receipt still validates original message ID,
input hash/conversation, generation/run nonempty, sequence and current local operation.

Query obtains explicit current credentials, rechecks scope/lease, begins query for the
ORIGINAL action, and uses generated queryMessageReceipt with original messageID. Raw
outgoing POST bytes are unchanged. Every response passes duplicate-key/header/UUID
request-ID checks before generated decoding. Error/unknown keeps original action; null
is only scoped not-observed, not authoritative absence and never permission to POST.
Late null/receipt cannot persist across local invalidation. Live POST activation gate
remains closed; this change enables only the query path, not a freshness authority.

PASS: 10 TransportTests (query-transport-tests.txt), including regenerated original
receive path, valid query receipt/null, missing/false/object fallback, invalid receipt,
late null, error-no-rePOST, request trace/redirect and live POST gate regressions.
Then 2 additional targeted checks PASS (query-additional-tests.txt): exact generated
keyNotFound classification; opaque ID containing slash/plus/percent/ampersand/decomposed
Unicode round-trips through generated query encoding once with exact UTF8 retained.
Existing storage/key/PG/AUTH evidence reused; no full old-suite rerun.

Swift6.4/macOS in-process interception only. No real credentials, network request, host
Keychain or server invocation. The generated decoder fallback remains broader than the
wire null branch; explicit consumer nil check is essential and is tested. Production
host/key implementation/anti-rollback authority/device and independent review remain
pending. AUTH backend-pin changes in CJ005 are not consumed by this Swift-only export.
