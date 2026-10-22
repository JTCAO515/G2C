# CJ006 canonical accepted MESSAGE → closed USAGE association host

This is a separate official-provenance path after the f6 conditional explicit-host usage reader. The old UsageSource/UsageContainerHost remains compatibility-only; it cannot construct a ResolvedUsageSource or supply this UI's source. No attempt, actor bytes, receipt or association is derived from message/run identifiers or user text.

## Actual record capture

AssistantMessageHost exposes an opaque AcceptedMessageUsageInput with no public constructor. It captures only the current accepted ActionRecord, its actual MessageRecovery/StorageScope/original Lease and current-selection ownership. Record/receipt bytes are not reconstructed. Client captureAcceptedMessage performs strict decode, original envelope/receipt/digest/conversation validation and creates its own CLOSED AcceptedUsageMessage. The host does not implement a seven-reference parser or claim acceptance from a DTO.

Root config supplies its existing verified SessionLifecycle/original SessionOperation, nonempty trusted actorIdentity bytes, revision, endpoint/credential callback, canonical NoRedirectTransport and current admission callback. Actor bytes do not come from StorageScope.account, a UUID guess or AuthAttempt. Missing config/actor/accepted record is unavailable. Backend association still proves only stored original linkage, not a usage row, dispatch, provider, payment or real execution; RUN's current writer remains synthetic-only.

## Two explicit user actions

1. Resolve usage link for selected message: capture canonical MESSAGE selection, make a per-selection OriginalUsageViewModel, call public captureAcceptedMessage and prepareAssociation synchronously, then Task/read. Only the official original-message association GET runs. On success the public closed source is shown as source-ready, explicitly not as queried/charged usage.
2. Read original attempt status: only the current model's closed ResolvedUsageSource can be passed to prepareStatus before its Task/read. This is a separate button action; there is no automatic second GET, polling or retry. Invalid/absent/503 association never creates a source and cannot trigger status read. Legacy UsageSource is not a fallback.

Loaded status uses the existing public UsageStatusView and exact decimal/null/unit meanings. No arithmetic, conversion, current balance or new call permission is implied. IDs shown in source-ready/loaded states come from the actual validated response.

## Lifetime and final callback fences

Every resolve installs host ownership before MESSAGE or admission callbacks and uses a fresh selection generation; the model installs its own preparation owner. Old resolve/status error/task cannot clear a newer request/model. MESSAGE selection changes including ABA, receipt query/retirement, account/root invalidation, inactive/background/disappearance synchronously clear source/model. Cancellation of captured old task from the synchronous MESSAGE hook is deferred so its cancellation callbacks cannot overwrite the message selection being committed. This does not issue remote cancellation.

Current-source checks are bounded: original configuration/session/selection; admission; original MESSAGE current check; admission again; final callback-free canonical MESSAGE lease/record, host selection/actor/binding/session/foreground checks. No callback follows the final ownership check. This is not a new AUTH provider. A state access invokes the same source guards; a previously loaded copy is not authority or a fallback after retirement.

Language changes preserve the current model. Reappearance never restores/reads old source automatically. The sourceReady step requires actual selected MESSAGE recovery record; newly bound source cannot relabel an old closed token. An older UI route or worker cannot auto-select an association from another message.

Actual real-account resources, server execution associations, App/device/redirect/network/I remain separate acceptance layers. Until actual trusted resources/source are connected, product state remains unavailable. This source work is an integration candidate, not proof of real business dispatch.
