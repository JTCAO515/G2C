# Official generated read-only history/draft client — CJ006 consumption candidate

Parent e4ca761bf1bb4f60a5d02be102fe0d5f721e478b. Only CJMessageClient package changes.
Official CJ005 CJAPI source pinned to 2f8be7c3e2dd298457488412b3a5e3b2ca59ca93;
prepare_generated.py exports exact fixed ios package blobs under ignored versioned
.generated/2f8be7c3e2dd298457488412b3a5e3b2ca59ca93/CJFoundation. File SHA256 inventory:
evidence/generated-pin.json. No generated source edited, authority fork, custom wire
Codable types, backend/CJShell/CJAuth changes, or root/shared configuration changes.

## Public read-only host interface

On existing MessageHTTPClient:

- conversations(limit:after:limits:lease:) → MessageReadResult<[CJAPI.Components.Schemas.ConversationSummary]>
- history(conversationID:limit:after:limits:lease:) → MessageReadResult<[CJAPI.Components.Schemas.MessageHistoryItem]>
- draft(conversationID:generation:limits:lease:) → MessageReadResult<CJAPI.Components.Schemas.MessageDraftSnapshot?>
- validateRead(result, lease:) before displaying/using a retained result after any await.

MessageReadLimits requires maximumPageItems(1..100), maximumCursorBytes,
maximumDecodedBytes and maximumPages, all explicitly configured; no product defaults.
Existing MessageEndpoint still requires request/response byte limits and explicit URL;
credentials provider and transport remain required. Use liveReadTransport only for an
explicitly authorized host; its POST prohibition is unchanged. This slice exposes no
PUT draft method and makes no real host call. Tests exclusively use named interception.

MessageReadResult is a NON-Codable local wrapper over official generated values, with
requestID and optional local MessageReadCursor, plus private originating lease/client
identity. MessageReadCursor is also non-Codable: opaque server token + private local
query/lease/client/continuation metadata. No cursor inspection for authorization or public
constructor. A first page uses after:nil; pass result.next back to the SAME client/current
lease and SAME query. Account/environment/generation change discards continuation and
starts a new authorized first-page read. It is not a server authentication capability.

Results contain private history payloads. Host must clear views on invalidation and
validateRead after await before use; values cannot be magically erased from a host that
retains them. Validation checks scope/lease/client, not permission independently of AUTH.
No response/body/token contents are logged or copied into another storage cache here.

## Validation and failure semantics

Before/after credentials await and after generated HTTP await, current scope/lease is
checked. CheckedTransport remains common to receive/query and new GETs: exact configured
baseURL and operation path allowlist, response byte bound, duplicate JSON keys/trace
headers refusal and matching UUID request_id/header. Required nullable generated fallback
is accepted ONLY when actual value is nil; missing/non-null unexpected fallback fails.
All rows are validated before a result is returned; no partial output or fabricated empty
success on validation, dependency, auth or limit failure.

List validates nonempty IDs/generations, nonnegative epoch, positive strictly increasing
list_sequence and no repeated exact UTF8 conversation IDs across the continuation chain.
Gaps in list_sequence are valid (database identity allocation across scopes). History
requires contiguous message sequence from1/previous page, same conversation and creation
generation, nonempty run/message IDs, canonical base64 and decoded UTF8 within per-page
budget. It verifies original raw-body SHA256/message ID/conversation/text against the
official receipt/text fields without reconstructing raw bytes or adding a wire model.

Draft GET distinguishes explicit null from a real empty saved draft. Non-null snapshot
must match requested conversation/generation, revision>0, canonical base64/valid UTF8 and
decoded-byte bound. No write, draft merge, revision bump, send or receipt creation occurs.

Next token must be nonempty, fit configured bytes, not repeat any token already in this
chain, and remain within host maximumPages. A nonterminal page at the maximum permitted
page count is refused rather than promising another page. Continuation returned IDs and
ordinals enforce no repeat/backward page. Empty initial page with null is legitimate;
empty continuation or empty page with next token is anomalous. Limits/malformed output
throw rather than truncate. Server 409 HISTORY_RESYNC_REQUIRED maps to explicit
MessageReadFailure.resyncRequired; caller may initiate a new safe first-page read under
current authorization, never an automatic write. Other BASE errors are thrown as typed
rejected; network/decode errors remain sanitized exchangeUnknown, not empty history.

The generation/epoch/high-water authority still belongs to server/context/codec; local
checks cannot establish a globally stable snapshot if a malicious server lies. No cursor
is treated as ownership, no new auth fields are invented, and no automatic paging loop
or write retry exists. Existing original-query null rule, once-only authorization and
live POST disabled gate remain unchanged. History does not grant first-send authority.

## Executed evidence

Swift6.4/macOS, exact official generated package compiled. Seven new HistoryReadTests
PASS: six in evidence/history-read-tests.txt, one explicit-budget case in
history-read-regression.txt. That latter run also executes three affected prior checks:
original receive octets, original receipt/null query, live POST remains disabled. Total
7 new +3 existing checks, not a full suite rerun. Covers successful list continuation,
query-purpose binding, duplicate/missing/invalid/oversized pages/cursors, original body
binding/canonical base64, null vs empty draft, server resync, late scope invalidation,
repeated opaque cursor and stale-result validation. All responses are synthetic in-process
interceptors; recorded outbound methods are GET for new methods. No real HTTP socket,
credential, Keychain, PG or API service invoked. Prior storage/backend evidence reused.

Independent review and actual CJ006 host/real identity/key/provider/device acceptance are
pending. No complete Issue10/server-history/real service acceptance or publication claim.
