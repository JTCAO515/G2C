# CJ021 withdrawal-observation.internal.1

Internal candidate for [Issue 26](https://github.com/JTCAO515/G2C/issues/26), fixed input
`8ea1b35756726f60727f10deaf157c40b8df1072`. Not MEMORY@1.0, a public wire,
accepted source-history policy, cleanup protocol, or activation approval.

`backend/memory_withdrawal/cj_memory_withdrawal/domain.py` is the only action codec.
`Action.parse(original_utf8)` requires immutable UTF8 bytes <=32768 bytes, exact keys:

| Key | Required value |
| --- | --- |
| action_id, item_id, source_id | Nonblank exact string, <=4096 characters |
| operation | `withdraw` |
| expected_version, expected_source_version | Integer >=1, never bool |

Duplicate/missing/extra keys, non-UTF8 and pause/resume/delete are rejected. IDs,
Unicode and original bytes are preserved; whitespace changes are replay conflicts.
No owner, authorization boolean, confirmation credential or scope comes from wire.
This shape is a consumer proposal pending original-owner confirmation.

`OriginalAction` is an immutable **read observation**, currently synthetic-only.
It uses canonical `cj_memory.domain.Receipt`, with withdrawn status, exact original
action ID/item/hash and resulting version = expected_version+1. Its positive epoch
and nonempty bounded history are metadata supplied by a future original producer.
It cannot issue a receipt, certify durability or establish complete source history.
`recover(scope, original_utf8)` returns that historical receipt, never mutates,
retries, reactivates, replaces an ID or restarts cleanup. Wrong scope is unavailable;
changed original bytes conflict. No local shadow ledger or MEMORY table exists.
An absent original receipt remains UNKNOWN and never authorizes resend.

`check_history` refuses missing/ambiguous history, missing current source revision,
unknown reverse references and sources shared with another item. 1000 references is
a candidate input bound, not truncation or product retention. The owner must supply
the complete locked history; passing shape checks does not prove completeness.
No source revision, authority or item is changed here.

`check_candidate_references` rejects the withdrawn item, **any revision of any old
source ID**, missing/duplicate/overbound provenance, old epochs and cross-scope input.
This is a bounded negative check for retained-chat re-extraction, summaries, rebuilds
and late results. Passing gives no freshness/publication authority and cannot detect
hidden provenance. Preserve canonical `Transaction.require_current` and its SAME
scope lock through actual publication; detached epoch checks are insufficient.
New explicit save must use a new approved source, without reviving the original
withdrawn item. No new save or source-approval path is implemented here.

## Cleanup observations

`progress.observe_cleanup(original_cj024_operation, trusted_link)` binds exact
original scope/operation/confirmation digest/manifest. The link is trusted-host
metadata, not an authorization issuer. `project` also binds the exact original
withdrawal bytes and memory scope, refusing a different action or expected version.
It checks full original target coverage,
invocations and original receipt bytes using **CJ024's existing receipt decoder**.
`Operation.status` is the only cleanup reducer; its precedence is not copied.
All step states/gaps remain visible. Original `complete` is labelled
`limited_complete`, bounded to that original frozen manifest digest.

The original CJ024 protocol is **account cleanup**, including auth revocation and
all its mandatory barriers. CJ021 neither constructs nor dispatches it for a single
item. No account barrier is renamed or skipped to simulate item deletion. There is
no accepted single-item operation-to-cleanup binding producer at this input.
The optional linkage is therefore exercised only with synthetic original CJ024
objects, independently of the synthetic memory observations.

`project` distinguishes stop_use `unknown`/`stopped` from the nested original cleanup
state (`blocked`, `awaiting_revocation`, `in_progress`, `failed`, `unknown`,
`limited_complete`). Even synthetic finite cleanup completion **cannot clear** the
fixed missing-producer/mapping/retained-chat-integration blockers. Overall CJ021 is
unknown without its original receipt and blocked with a valid observation. Callers
cannot pass booleans to clear blockers. No physical deletion success is issued.

`execute_withdrawal` and `public_factory` always refuse. No persistence, SQL,
network, provider, DB connection, hook, API route or destructive executor exists.

## Required original-owner seams

See [SEAM-REQUEST.md](SEAM-REQUEST.md). These block persistent withdrawal only;
the codec, immutable recovery validation and observations can be reviewed now.
No source-history cleanup/retention policy is invented. Retained original chat
must be fenced at **every** raw/summary/retrieval ingress before actual use. Scope
epoch alone cannot discover or prevent an unintegrated alternate context path.

No claim to erase already displayed history, requests already sent to a model,
external model/provider retention, backups or disconnected-device copies. Only
original-owner verified controllable storage can later receive finite completion.
Actual CJ020 derived storage/RUN/model context, durable memory writes, accounts,
UI/device, permissions, real hooks, independent gates, CI and release are UNRUN.
Issue 26 remains open; this candidate does not satisfy its I prerequisites.
