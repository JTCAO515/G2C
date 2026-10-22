# History wire consumption and trusted context seam

Delta parent ac2981078ec3a001c577de1d557337010feb5d43. Consumed CJ005 exact proposal
commit e3a15696b9ca640fc2ce98ba0016356efab4a31a, contracts/api/history-draft-proposal.md,
SHA256 1417a8173a3bd7101a2ad48d052f3ba6d8acce158bdb3511374ae0060ff814c8. Git-object
readback matches the earlier supplied bytes. No shared source/route/OpenAPI change here.

## Acceptance and required seam replacement

CJ009 confirms the four minimal routes/projections as compatible with b722281 internals:
conversation list; message history with exact raw bytes base64 + validated text; draft
GET nullable only in an owned active current generation; draft PUT plain UTF8 octets,
including empty, expected_revision compare-and-write. It creates no message/run/receipt.
Nullable properties must be required and fallback checked for actual null. IDs preserve
exact bytes via correct single query encoding; no client owner/principal/scope fields.

Explicit host codec/TTL/token/page/body/output bounds and missing-capability refusal are
accepted. Draft revision conflict stays conflict, unknown save requires original draft
read/version reconciliation, not automatic PUT or proof from equal text. Auth denial,
unavailable/missing/foreign/stale chat never become null/empty. Resync409/retry_safe_read
means fresh first-page READ only. Commit/return/rollback uncertainty remains conservative;
this slice adds no reliable rollback receipt or production retention assumption.

DO NOT consume Boundary._service or do a second unrelated authentication to obtain codec
identity. New public server-only seam:

`Boundary.with_history_context(token, operation)`

operation is a synchronous callback receiving a short-lived HistoryReadContext. It offers:
- principal: the exact real CJ007 TrustedPrincipal from the captured allowed decision.
- scope: the exact repository scope selected by the server resolver for that decision.
- conversations(cursor=None, limit=20), message_history(id,cursor=None,limit=20),
  read_draft(id,generation): the existing guarded Service reads, with current gates.

No write/repository property or caller-claims constructor is exposed. Construction requires
a module-private factory marker; this is API misuse prevention, not a sandbox against
arbitrary Python code. Context is not Codable, not a credential, and cannot be made from
request JSON. A trusted host could introspect Python internals; such behavior is outside
this server-composition contract, not an alternative authorization path.

## Single identity and callback lifetime

One initial allowed decision selects one repository; its principal and scope are captured.
Fresh checks compare against that SAME principal plus unchanged repository scope, not a
new separately resolved actor. A fresh check occurs after resolver/before callback; each
read retains transaction/commit/return guards; another fresh check occurs AFTER codec
encoding/projection and BEFORE returning the callback result. Then context expires on
success/error. Accessing context methods/metadata afterward raises. Deferred coroutine/
generator/async-generator or direct-context result is rejected; no await is supported.
Host must not retain metadata as later authority or nest context into a response object.

Recommended host structure (pseudo-code, codec interface is CJ005's responsibility):

```
def materialize(ctx):
    # environment comes from explicit trusted host config; issuer/subject/audience
    # and storage scope come from this exact ctx, never from decoded token claims.
    cursor = codec.validate_and_decode(input_token, ctx.principal, ctx.scope, query)
    rows, next_cursor = ctx.conversations(cursor, configured_limit)
    # encode next cursor, validate/base64/project rows, enforce final output budget here
    return fully_materialized_response
response = boundary.with_history_context(token, materialize)
```

Decode never selects the repository. Codec must authenticate purpose/version/expiry and
compare environment/issuer/subject/audience/scope/query against ctx; generations/epoch/
high-water then undergo domain checks. Do not use volatile token iat/exp as stable storage
partition identifiers. Trusted environment mapping/codec policy are host-supplied, not new
principal fields invented by MESSAGE. No actual codec/signing key/TTL is implemented here.

Draft PUT requires no public cursor; continue existing Boundary.save_draft and existing
unknown-effect mapping. Read-only context deliberately has no save method, avoiding
codec/projection failures after a new draft write under this seam. Existing receive/query/
draft transaction semantics and SQL are unchanged. All fencing remains synchronous, not
distributed atomic revocation; provider freshness and publication races remain limitations.

## Validation

Python3.14.7 + exact fixed AUTH79f88b interface/gate; synthetic verifier/policy/repository.
7 targeted checks PASS: single resolver identity, forged cursor scope rejection, identity
change during codec blocks read, final projection deny/unknown/identity withholds output,
expired context/deferred work/error, caller constructor rejection/scope drift, entry unknown.
3 targeted existing receive tests PASS after shared bind extraction: normal repeated gates,
precommit revocation rollback, postcommit denial preserves original recovery. Evidence:
evidence/history-context-tests.txt and history-context-regression.txt.
No database/server/key/provider/Keychain/network call, no PG rerun. Source syntax and diff
checks PASS. Domain/postgres/SQL and Swift source unchanged. Independent review pending.
This explicit seam and the confirmed proposal are ready for CJ005 bounded implementation;
no need to wait for complete MESSAGE/AUTH freeze, but not permission to deploy/apply old DB.

Feedback-source additive seam: CONTEXT-QUERY-MESSAGE.md defines public ctx.query_message
with original raw/digest/ID verification and callback-thread/context lifetime protection.
It returns the existing Stored/Receipt shape, not serialized receipt bytes or RUN completion.
No source lookup should call private _service or cross-domain SQL for this association.
