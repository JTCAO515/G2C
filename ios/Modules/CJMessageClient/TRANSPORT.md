# Controlled receive transport candidate

Parent e58dba3cb6da55669fce6c2e319c0f67c96f2e4a. Official generated input is fixed
CJ005 d886677a805db51759a3116f8d2c0d4f3b8dddb3, NOT a claim of merged main. Backend
AUTH pin discrepancy under CJ005 repair is separate; only its ios package is consumed.
`scripts/prepare_generated.py <CJ005 git repository>` exports exact package/source/test
blobs into ignored `.generated/CJFoundation`; SHA256 manifest evidence/generated-pin.json.
No generated file edited or second wire Codable type introduced. Local dependency lock
records resolved dependencies; production integration consumes the SAME official CJAPI.
Fresh checkout must run prepare before SwiftPM; the original core itself has no external
imports, though this combined package now resolves the transport dependency graph.

CJMessageHTTP uses generated receiveMessage with `.binary(HTTPBody(originalUTF8))`.
The current raw ID/conversation are checked without re-encoding the outgoing bytes.
Explicit endpoint, scope, credentials provider, request/response byte limits and transport
are required; there is no default URL/token/key. Endpoint rejects credentials/query/
fragment/path-prefix and non-HTTPS except explicitly allowed numeric loopback HTTP.
Host is responsible for choosing its authorized endpoint/environment pair. Scope/lease
rechecked after async credentials; original queryRequired persists before network send.

NoRedirectTransport supplies ephemeral URLSession with cookies/cache/credential store
disabled and refuses redirects in the delegate before destination dispatch. It is never
constructed by default. Injected transports are a trusted seam and must also not follow
redirects; tests use only in-process interception. CheckedTransport rejects 3xx and
unexpected baseURL/operation/path, bounds response collection, rejects duplicate request
trace headers and generic duplicate JSON keys, and compares UUID header/body trace.
No custom wire decoder is supplied; after generic validation official CJAPI decodes.
Receipt ID/digest/current operation and original conversation/nonempty generation/run/
positive sequence are checked before acceptance. Error recovery never auto-retries POST.
Generated transport errors may retain Authorization-bearing requests, so public network
failure is sanitized to exchangeUnknown; underlying errors are not logged/exposed.

## Exact blocked query field

At d886677, OpenAPI MessageReceiptQueryResponse requires `receipt` with anyOf
MessageReceipt/null, but generated Types+Components+Schemas.swift contains ONLY
request_id in that struct and CodingKeys. It cannot distinguish a real receipt, null,
or missing field. Main routed correction to CJ005. Until a fixed regenerated source
arrives, `query` fails explicitly queryGeneratedFieldMissing WITHOUT network or state
mutation. No substitute wire type or manual interpretation of absent field exists.
This is a partial receive transport candidate, NOT complete query recovery acceptance.

## Evidence / limits

Swift6.4/macOS, 7 targeted TransportTests PASS (evidence/transport-tests.txt): original
binary body once; duplicate/mismatched trace/JSON keys; invalid receipt/3xx; credential
and response await identity changes; BASE retry_safe_read never rePOST; explicit config/
missing credentials; query missing-field blocker. Existing core tests reused except
new validateScope helper is exercised by transport tests. Initial test helper access
modifier compile error corrected, assertions unchanged. Library compiled with fixed CJAPI.
No actual HTTP socket or Internet business request, credentials, Keychain, backend or PG
run. Live URLSession redirect rejection is source/compile evidence, not a live-network
redirect test. Independent review, query transport, real host and device still pending.

Fixed f1ce075 CJ-MESSAGE-KEYS interface inspected: independent key namespace/purpose and
existing(expectedID:) can support a separate adapter. Current local encrypted format has
no key ID and cannot yet provide expectedID; next isolated delta will add authenticated
key-ID binding, explicit old-format rejection and read-only existing-key adaptation.
No session token/AES conversion or production cross-account shared key is accepted.

Subsequent activation delta: liveReadTransport composition and concrete NoRedirectTransport
both reject POST before outflow until authoritative anti-rollback input exists. The old
`transport:` test seam is now explicitly `interceptedTestTransport:`. See ACTIVATION-GATE.md;
this supersedes any implication that the compiled receive path may be activated live.

## Query blocker resolved in fixed consumer delta

Current official generated pin is 312a69caf0bd97ed65679cfd8ff049972c212cef, exported
under a versioned ignored directory. query now consumes its REQUIRED receiptPayload;
only case2.value == nil means notObserved, all non-null fallback/missing invalid.
The earlier d886677 blocker above is historical, retained as failure provenance.
See evidence/QUERY-CONSUMPTION.md for 10+2 actual checks. No live POST activation changed.
