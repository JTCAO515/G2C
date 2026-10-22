# Single shared CJAPI RUN display export candidate

Exact parent514e0e3a80bd9a3e34248122915d52c86ee46230; existing cj-009-memory-api-pin
branch/tree and exclusive module Package/prepare/export/test/evidence scope.
Fixed official producerc02cf08e52a0d8ffc2fefac99226654a7e01539c; source is in independent
review, not a merged/accepted/runtime-ready claim. This work does NOT resolve69d/b868 HOLD.

One versioned candidate:
`ios/Modules/CJMessageClient/.generated/c02cf08e52a0d8ffc2fefac99226654a7e01539c/CJFoundation`

Existing prepare mechanism exports16 exact official package/source files including the
required MemoryClientConfiguration.swift; source hashes in generated-pin.json. No generated
source modifications, second package identity, private wire model, SDK upgrade or other
consumer manifest changes. Prior201156/d688/9dc/573 exports rehashed fully unchanged.

Compatibility against201156: all21 prior paths and79 prior component schemas exactly equal.
Official SDK manifest/lock/date helper byte-identical. Only new GET /v1/run-display with
getRunDisplaySnapshot and RunDisplaySnapshot/RunDisplayResponse schemas. Snapshot has
nine required fields and response has server request_id; no nullable successful snapshot.
Existing runtime POST/PUT gates and current App active pin remain unchanged.

PASS: standalone Swift6.4/macOS build and41 checks in8 suites: old38 consumer checks plus
three new official generation checks. Actual generated GET is invoked only against a
process-local interceptor: required original message_id query preserves exact UTF8 with
one query parameter; method/operation are GET/getRunDisplaySnapshot, no body; required
response header omission fails. Codec checks all7 declared statuses and complete/partial
text_state values, message_sequence distinct from event_highwater, absent/null snapshot,
missing generation, unknown status/text-state and extra scope field rejection.

These are type/codec checks, not proof of authoritative snapshot provenance, full numeric
bounds/cross-field semantic validation, header/body identity matching, producer lifetime,
RUN completion/provider success, SSE, actual PG or real HTTP. Future display consumer must
apply its own approved actor/binding/trace/semantic guards; no new consumer is implemented
here. Explicit complete-for-completed fixture pairs do not imply the generated decoder
alone enforces that cross-field rule.

PASS: actual standalone SwiftPM graph contains one CJFoundation location (c02). Resolved
SDK revisions all match prior fixed main locks. Automatic standalone lock expansion was
preserved in ignored build evidence then source lock restored; no shared/root lock edits.
Exact versions/OpenAPI/log hashes in run-display-api-pin-provenance.json; concise output
run-display-api-pin-tests.txt, full log under ignored .build/run-display-pin-evidence.

Full App same-pin integration remains UNRUN and Main-coordinated; no Memory/Trip/Needs/
Feedback/Shell package edits. No business network, credentials, Keychain, PG, server,
signing, write activation, push, PR, merge or deploy. Prior failures/HOLD and source PG
acceptance attribution remain separate from this compilation/export result.
