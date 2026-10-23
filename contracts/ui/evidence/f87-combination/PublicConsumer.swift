import Foundation
import CJShell
import CJSession
import CJCleanupClient
import CJOfflineTrip

// Compile-only public composition. Never called, no operation or snapshot is
// invented, no transport/store is created, and no authorization is granted.
@MainActor func consumeFixedPublicGraph(shell: ShellState, cleanup: CleanupViewModel,
    snapshot: OfflineSnapshot, namespace: OfflineNamespace?, policy: OfflinePolicy?,
    clock: OfflineClock, lastTrustedWall: Int64?, minimumVersion: Int64,
    sessionAllowsOffline: Bool) -> (CleanupState, OfflineValidity) {
    _ = ShellView(state: shell)
    return (cleanup.state, OfflineValidityEvaluator.evaluate(snapshot, active: namespace,
        policy: policy, clock: clock, lastTrustedWall: lastTrustedWall,
        minimumVersion: minimumVersion, sessionAllowsOffline: sessionAllowsOffline))
}
