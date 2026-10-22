# CJ006 Trip tab container

Trusted root injects `TripContainerHost` into the existing `ShellView`. Default is unavailable with no client, account, session, key, endpoint, directory, trip/proposal ID or confirmation. `TripContainerBinding` receives the actual canonical client/binding, original SessionLifecycle/SessionOperation, ShellGeneration, bounded page size and the same trusted current-binding callback as the client. Optional currentTripID/proposalID are existing application context only; the shell does not invent a trip or treat their presence as authorization.

## State and action ownership

Each installed binding gets a distinct canonical `TripPresentation`. The shell retains only navigation/selected ID and an action epoch, not another Trip record/store/wire model. At the UI event, the shell checks the captured `TripContainerAction`, synchronously calls canonical prepareProposal/prepareTrip/prepareTrips/prepareReconciliation, and returns a `TripContainerWork` containing the opaque `TripPresentationWork`. Only then does the button create Task to perform that work. A work cannot be executed twice or release another in-flight work's busy state. Dispatch and completion recheck the shell, trusted callback, original session operation and epoch. Selection changes retire old queued actions. Client authentication/transport checks remain canonical; local operation ownership is not business authorization.

Identity/environment/selection replacement must explicitly invalidate the host before installing a trusted new client/binding. Account cleanup and inactive/background scene cleanup clear own references before invalidating the old presentation; the old instance is never rebound to B. Language changes retain the current instance. No automatic foreground rebind/GET occurs. Trip cleanup is added before existing Memory/history/message callbacks with the same generation recheck, preserving their existing ordering/fences. This is local private UI cleanup, not remote deletion.

## Read and recovery UI

- Explicit list/next-page controls use canonical `TripPresentation.loadTrips` and cursors. A short nonempty page still permits next page; no complete snapshot is claimed.
- Selection accepts actual returned trip IDs or the trusted root's currentTripID. Selecting B hides A's cached detail until B is explicitly read. `TripDetailView` renders the actual current formal version, source evidence and pending facts.
- Only an injected current proposal ID can trigger proposal GET. `TripProposalCard` renders the canonical candidate, original content/hash, basis/expected version, deadline/status and pending facts. Read/view is not confirmation, and accept/reject remain disabled.
- Pending actions come only from canonical secure-store reads. Selection rereads the store and must still be loaded afterward; a missing key cannot turn an old selected ID into new selection success.
- Original-action query uses the selected frozen action, with its own host-captured context. Null/malformed/cancelled outcomes remain unknown, never permit resend or invent a new action. Historical receipt/version is displayed separately from a later formal detail read; latest version does not overwrite the original receipt.
- Missing configuration/store/key is explicit unavailable/failed. The container never creates a key, falls back to plaintext, changes namespace or modifies the ledger.

Producer12df fixes its queued controls with canonical prepare/perform. The shell retains its existing list composition from canonical rows for host navigation and root fences, now using those same public prepare/perform APIs, and reuses the domain detail/proposal components. The embedded proposal card is read-only (`disabled(true)`), including its internal query button; the host supplies the active original-query button with the exact origin fence. No producer file is patched to change behavior.

Production POST is closed in both canonical public API and UI; `canSubmitDecision` remains false. No viewed flag, confirmation reference, action ID or permission is manufactured. Full confirmation/Trip integration and device acceptance remain separate gates.
