# MESSAGE send activation — ADR-0008 / #164

Authority is the server conversation head defined by [ADR-0008](../../../docs/adr/0008-message-send-permit.md) and [MESSAGE-SEND@1](../../../contracts/message/SEND-PERMIT.md). An encrypted snapshot, a key ID, a restored phase or a receipt-query null is never fresh sending authority.

## Build and session boundary

- The public `NoRedirectTransport.developmentMessages` factory exists only as a granting path in **DEBUG iOS Simulator** builds. Other builds throw before creating a sending capability.
- Its endpoint must be explicit `http://127.0.0.1:<port>`. The trusted development host supplies a validator capturing the actual current account, environment and session lease. Default transports remain read-only; no permissive boolean opens them.
- Release, physical-device and production sending remain closed. Their later activation requires the separate L2 account/resource decision specified by ADR-0008.
- `interceptedTestTransport` and the internal transport-test initializer are strictly non-network test seams. A product host must use the live factory; a live transport must never be placed in an interceptor seam.

## Head provenance and first send

`MessageHTTPClient.readSendHead` reads the official status endpoint under the current recovery scope/lease. The head cache is process-local and is cleared on lease changes; it is not Codable or stored in `Snapshot`. A preceding validated receipt can advance the cached head for the same conversation.

`stageSend` constructs `MESSAGE-send.1` bytes from that head, explicit user text and creation intent, with `trip_id = null`. It refuses a missing head, an unresolved original action in the conversation, or an already observed ID/body. It reserves the head before storage callbacks. `submitPrepared` requires the exact prepared digest and consumes the existing `MessageRecovery` once-only authorization before handing bytes to transport. It persists uncertainty before any credential or network await.

A later `SEQUENCE_CONFLICT` is not permission to change the ID, input or head: the original action stays query-required and sending status must be read again.

## Two independent sending checks

1. The live client requires the explicit development capability, current binding, current-process head provenance, exact original bytes and once-only authorization. Its first capability check occurs before credentials are requested.
2. The live `NoRedirectTransport` capability admits only official `receiveMessage`, `POST /v1/messages`, the bound endpoint, exact octet-stream media type and a valid send.1 body. Alternate paths, methods, operation labels, host/authority overrides, old versions, duplicate fields and invalid integer heads are rejected. It revalidates the host before outflow and after response materialization, rejects redirects and bounds both bodies.

The pre-existing read-only manual-preview capability is separate and unchanged. A message capability does not grant preview, Trip, draft PUT, or other writes; no other module's transport is modified.

## Original-action recovery

A send-status request reads the original receipt and head together. Required nullable generated containers must contain **actual null**; a fallback enum case containing an object is invalid. Missing, malformed, foreign-bound, failed or unknown responses keep the original action query-required.

| Receipt | Head | Decision |
|---|---|---|
| Matching original hash | Any, including null | accepted |
| Different hash | Any | integrity error; stop this conversation |
| null | null | not accepted; original request can no longer be accepted |
| null | Different generation | not accepted |
| null | Sequence above original expectation | not accepted |
| null | Same generation and sequence | original-byte resubmission may be offered |
| null | Sequence below original expectation | resync required; stop this conversation |

An offered resubmission always uses the same ID and exact bytes and consumes a new once-only authorization only after that current status read. A process that already crossed this action's sending intent may resubmit without a second confirmation. **Every action restored from storage requires explicit user confirmation** after the read. Confirmation by itself never creates permission. An `INPUT_CONFLICT` on submission is an integrity error, not a retry loop.

`notAccepted`, `integrityError` and `resyncRequired` are persisted local outcomes; they grant no head authority. Integrity/resync outcomes continue blocking the conversation after reopening. A new message after not-accepted still needs a fresh process-local head and a new user action. Do not describe not-accepted as proof that an earlier server execution never happened; ADR-0008's server restore rule remains in force.

## Storage and compatibility

The encrypted original ID/body, original receipt, existing Keychain namespace isolation and process-local denial memory remain authoritative for local recovery. No file deletion, key rotation, empty-store fallback or input rewrite is used to make an old action fresh. Loaded staged records still become query-required.

Historical draft.1 local records remain readable by the existing recovery/query path, but cannot pass either live send gate. Older binaries do not understand the new terminal phase values and fail closed rather than discard/rewrite them; do not use downgrade as a recovery shortcut.

Historical rollback and once-only evidence remains in [FRESH-AUTHORIZATION.md](FRESH-AUTHORIZATION.md) and its linked evidence files. Current acceptance is tracked in [#164](https://github.com/JTCAO515/G2C/issues/164); unit/interceptor evidence alone is not Simulator, real-service or production acceptance.
