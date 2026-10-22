# CJ006 conditional original-attempt USAGE reader

Scope is only the read-only user-facing slice of [CJ008 / Issue9](https://github.com/JTCAO515/G2C/issues/9), read through official GitHub repository ID1428033587. No metering/charge/balance/quota/provider/dispatch, remote cancellation or automatic retry is implemented.

## Production source audit and explicit gap

The current CJShell has no trusted production original-attempt receipt. AssistantMessageHost stores an accepted canonical MessageReceipt with message/conversation/generation/run/sequence/input hash; none is a usage attempt. RunDisplaySnapshot has original message/run/status/text/highwater but no attempt. AccountHost's AuthAttempt is a login-flow attempt and must not be substituted. Usage's current GET requires an already known attempt_id and cannot discover it. No hand-entered field, random business ID or message/run-derived fallback is provided.

The exact missing input is a protected original execution association: original attempt plus optional operation/run from the SAME evidence, together with trusted actor identity bytes/original SessionOperation/current source ownership. Main has returned that producer/wire work to its original owners. No new route/signature/receipt/provenance type is guessed here. Until a genuine source is delivered, default product state is unavailable, no model/source/read/Task is created and no source is fetched automatically. Synthetic test bindings demonstrate only the conditional client integration.

## Trusted resource and selection lifecycle

Root may inject UsageContainerConfiguration: original SessionLifecycle, explicit MessageEndpoint limits, accepted credential callback, canonical NoRedirectTransport, ShellGeneration and a mandatory current-source admission callback. The callback receives the actual captured UsageBinding and must verify its original source/actor/revision/operation. It is not a new principal or authorization provider. The server remains authoritative. There is no default endpoint, actor, original attempt, credential or operation.

Only root may select an existing UsageBinding. The host preserves original source, actor bytes, SessionOperation and revision, and allocates a NEW local selectionGeneration on EVERY switch including A-B-A. Incoming background selections are withheld; reappearance never restores or queries old source automatically. The generation is UI lifetime data, not a new attempt/business ID. Each source has a distinct UsageViewModel; language changes preserve the current model/selection.

The explicit Read event reserves the host request before callbacks, then calls the public model.prepare synchronously BEFORE creating its Task. The module's independent preparation owner handles same-revision reentry. A stale outer caller returns without invalidating newer model/work. Host cleanup only touches a matching configuration/model/selection/request. Old model/task are detached before invalidation/cancellation; no old-lifetime host mutation follows their callbacks. Read failures cannot retire a new selection or cancel its Task.

The current-binding callback checks captured source/actor/generation/revision and SessionOperation before/after trusted admission; foreground/configuration/ShellGeneration are rechecked afterward. Account/root invalidation removes resources and source. Background/disappearance clears source and cancels only the local read; no server attempt is cancelled. A new foreground requires a freshly selected trusted source and a separate explicit Read.

## UI and exact semantics

An entry in the existing Assistant sheet router embeds the public UsageStatusView, with no new tab or editable attempt field. Historical source associations are displayed from the actual returned snapshot. Only original attempt_id is queried; optional operation/run expectations are retained/checkable rather than invented. No polling or on-appear request.

Amounts/outputs remain exact decimal strings (including values larger than Int64). Unknown null remains unknown; actual "0" remains zero. Unit identifiers are opaque, not money. The host performs no arithmetic, conversion, clipping or price/balance inference. Reserved/unknown/released/settled/cancelled/exceeded meanings come from the public component; historical results cannot authorize another dispatch or promise rollback/refund. Actual real-execution source and full Issue9/I acceptance remain pending.
