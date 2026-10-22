// Compile-only public API consumer. Never invoked; no transport, account or storage.
import Foundation
import CJAPI
import CJTripClient

@MainActor func consumeAcceptedDetail(client: TripClient, binding: TripBinding) async throws -> Int? {
    let original = try client.prepareDetailSnapshot(id: "trip1", binding: binding)
    guard let snapshot = try await client.detailSnapshot(for: original) else { return nil }
    let count = try client.withCurrentDetailSnapshot(snapshot) { bytes, record, requestID, originalBinding in
        _ = record.version; _ = requestID; _ = originalBinding
        return bytes.count
    }
    try client.validateDetailSnapshot(snapshot)
    return count
}
@MainActor func legacyConsumer(client: TripClient, binding: TripBinding) async throws -> Components.Schemas.TripRecord? {
    try await client.detail(id: "trip1", binding: binding)
}
