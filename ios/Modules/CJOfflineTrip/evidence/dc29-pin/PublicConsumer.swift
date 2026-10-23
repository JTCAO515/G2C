import Foundation
import CJOfflineTrip
import CJTripClient

@MainActor func consumePublicSource(_ client: TripClient, request: TripDetailSnapshotRequest) async throws {
    guard let source = try await client.detailSnapshot(for: request) else { return }
    try client.validateDetailSnapshot(source)
    try client.withCurrentDetailSnapshot(source) { bytes, record, trace, binding in
        _ = bytes; _ = record; _ = trace; _ = binding
    }
}
func evaluateExisting(_ snapshot: OfflineSnapshot, namespace: OfflineNamespace,
                      policy: OfflinePolicy?, clock: OfflineClock, lastTrustedWall: Int64?) -> OfflineValidity {
    _ = SnapshotCodec.appFactoryAvailable
    return OfflineValidityEvaluator.evaluate(snapshot, active: namespace, policy: policy, clock: clock,
        lastTrustedWall: lastTrustedWall, minimumVersion: 1, sessionAllowsOffline: false)
}
