# CLEANUP-API@1 / CLEANUP-DEVICE@1

Additive App HTTP contracts for #27 and #24. Old internal cleanup and old
current-ALLOWED progress rc remain unchanged. This is not the Python DomainHook ABI.
Local-only host activation requires explicit key/TTL/inventory configuration; real
account/cloud/provider/device/backup acceptance is separate (#32/#29/#30).

## Credentials and common wire

Fresh ordinary `Authorization: Bearer <access JWT>` is required for device binding,
preparation, and the one explicit account confirmation. After confirmation that
credential no longer grants ordinary sensitive reads/writes. Cleanup credentials
never authenticate business routes:

- `Authorization: Cleanup <progress_token>`: only its original operation progress.
- `Authorization: Device <device_token>`: only its binding's invalidation call/query.
- `Authorization: Cleanup <receipt_token>`: only its exact original device receipt.

Tokens are purpose/subject/operation/binding/invocation bound, signed with an
explicit configured key and expiry. Store them in a separate trusted host secure
slot before clearing the ordinary SDK session; never log, place in URLs or reuse
them as a bearer JWT. Expired/tampered/wrong-key/purpose/scope credentials reject.
No key/production credential is shipped by this contract.

POST uses `application/octet-stream`, exact UTF8 JSON ≤16384 bytes. Duplicate,
extra and malformed keys/Unicode reject. No request owner, environment, scope,
registry bytes, hook code, SQL or file path is authority. Responses are final
encoded JSON ≤65536 bytes with generated `request_id` and `Cache-Control:no-store`.
IDs use the existing bounded ASCII identifier grammar; hashes are lowercase SHA256.
The App creates only action/device correlation IDs, never an account operation ID.

## Bind device, create and confirm original operation

1. `POST /v1/cleanup-devices` (Bearer), exactly
   `{version:"CLEANUP-DEVICE@1",action_id,device_id,state_ref}`. `state_ref` is the
   trusted native host's SHA256 reference to its prepared namespace/generation/key
   state, not permission or a filesystem selector. Response has `binding_id,
   device_id,state_ref,scope_digest,device_token,server_time,business_access` plus
   version/request_id. `business_access` is always `not_granted`; this response
   does not authorize a cache read or extend an offline deadline by itself.
2. `POST /v1/account-cleanup-operations` (Bearer), exactly
   `{version:"CLEANUP-API@1",action_id,binding_id}`. It freezes the host registry
   and affected plan, issues a **server-generated** `operation_id`, and returns
   `phase,registry_digest,plan_digest,binding_id,revision,confirmation,progress_token`.
   Phase starts prepared; confirmation literal is `DELETE_ACCOUNT`. No revocation
   or deletion occurs merely by opening the UI/preparing.
3. Unknown preparation ACK: `GET /v1/account-cleanup-preparations?action_id=<original>`
   (Bearer) returns `preparation:null` or the original server operation, frozen
   digests/binding/phase/revision and restricted progress token. Foreign/absent
   actions are indistinguishable. Null is an absence observation, not authority to
   invent another operation. Preserve original ID/bytes and reconcile first.
4. `POST /v1/account-cleanup-operations/{operation_id}/confirmation` (Bearer), exactly
   `{version:"CLEANUP-API@1",registry_digest,confirmation:"DELETE_ACCOUNT"}`.
   Own prepared operation, explicit confirmation and exact current frozen registry
   must match. An unready domain set returns blocked/prepared without revoking.
   A registry change conflicts; no silent scope enlargement/shrinking.

Same preparation action and exact bytes returns its original operation; different
bytes conflict. Confirmation binds exact original bytes. After possible confirmation
commit use the original progress token/GET, never retry deletion or mint a UI ID.
Repeated confirmation/ordinary registration after revocation reject. A failed or
unknown server response is not proof the account was physically erased.

## Restricted progress

`GET /v1/account-cleanup-operations/{operation_id}` with Cleanup progress token.
It cannot create another operation, restore membership, read business content,
dispatch a model/hook, retry deletion or recover an unknown worker. It audits current
registry coverage and may latch blocked; it never changes the confirmed target plan.
After retirement only the active original operation is accessible, even if another
preparation's credential was issued earlier.

Prepared progress has `phase:prepared,status:awaiting_confirmation,revision,steps:[]`.
Confirmed progress has `phase,status,online_status,revision,steps,devices,obligations,
complete_scope,business_access`. Each step is only target/state. Devices carry only
binding/invocation/state and `provenance:authenticated_current_device_report`.
Revision and these states come from one locked PG snapshot, not a synthesized
percentage or fixture. `business_access:revoked` does not claim remote Auth-user
deletion. Unknown/failed/blocked remain visible.

`online_status:complete` means only all confirmed frozen online domain results.
It is not overall `status:complete`: backups (30-day rolling), other devices and
external retention remain explicit unverified obligations until their real evidence
exists. Expiry, unprovisioned data, SDK clear or a queued call is not a domain receipt.

## Device call, original query and receipt bridge

`POST /v1/cleanup-device-calls` (Device), exactly
`{version:"CLEANUP-DEVICE@1",binding_id,reason}`. Reasons are `session_invalid` or
`offline_expired`; an active account deletion automatically links to its **original
operation** and server reason account_cleanup. Otherwise the server creates a
stable device-only invalidation operation, never an account deletion. Offline
expiry only targets the offline-trip cache and never renews a read lease.

Response: `call,request_digest,state,receipt_digest,receipt_token`. Call has exactly
`version,operation_id,invocation_id,binding_id,scope_digest,state_ref,reason,targets,
business_access`. IDs and expected digests are server-issued/persisted before any
native action. The App host verifies its current/recorded trusted account namespace,
generation/key state against scope/state references, then maps only known target
IDs to A's exact own-scope primitives. No raw route field becomes a path/key selector.
Mismatch/unreadable/changed state is UNKNOWN, never broad deletion of another user.

`GET /v1/cleanup-device-calls/{invocation_id}` (Device) queries this same persisted
call; it does not rerun the native hook or produce a new invocation.

`POST /v1/cleanup-device-receipts` (Cleanup receipt token), exactly
`{version:"CLEANUP-DEVICE@1",action_id,operation_id,invocation_id,binding_id,
request_digest,outcome}`. Outcome is confirmed/unknown/failed. Only the original
bound call is accepted; no exception text, private file content or arbitrary JSON
receipt is authoritative. A records/reconciles its actual original local execution
before reporting, commits before confirmed, and does not rerun an UNKNOWN native
erase simply because the HTTP ACK was lost. Keep exact original receipt bytes.
Same receipt replays; changed terminal bytes conflict; wrong scope/hash/purpose reject.

This is an authenticated **current-device report**, not server physical attestation
or proof every offline device was wiped. Other devices reconnect and report their
own original calls; the approved 14-day read cap does not become fake erase success.
Native and cross-device evidence remains with A/#29. Receipt processing may import
the existing domain result/continue only the original confirmed cleanup, granting
no ordinary business privilege or new deletion scope.

## Errors and examples

401 missing/malformed required credential; 400 shape/bounds; 403 unavailable
credential/own operation/intent (foreign and absent indistinguishable); 409 original
bytes/scope/terminal conflict; 503 dependency/commit uncertainty with original
reconciliation. No secret, principal or private exception is exposed.

Executable positive/negative examples: `account_gateway_pg.py` (actual signed
HTTP/runtime PG, create/confirm/recover/progress and device bridge),
`account_retention_pg.py` (original run_once/FakeProvider, real B hooks, before/at/
after 90-day timing only, other account/content/usage preserved), and capability
tamper/expiry/wrong-key/purpose tests. They are component proofs with an explicitly
provided inventory, not fake C/A hooks or whole-account/cloud/device acceptance.
