import Foundation
import CJAPI
import OpenAPIRuntime

/// A single original formal-detail read prepared before asynchronous work is queued.
/// Has no public constructor and is not an accepted-response claim.
public struct TripDetailSnapshotRequest: Sendable {
    fileprivate let owner: UUID
    fileprivate let generation: UUID
    fileprivate let source: UUID
    fileprivate let binding: TripBinding
    fileprivate let tripID: String
}

/// Proof only that this client accepted this exact formal-detail response in its
/// captured lifetime. Bytes are available only through the client's current guard.
public final class AcceptedTripDetailSnapshot: Sendable, CustomStringConvertible,
    CustomDebugStringConvertible, CustomReflectable {
    public static let apiSourceCommit = "c02cf08e52a0d8ffc2fefac99226654a7e01539c"
    fileprivate let request: TripDetailSnapshotRequest
    fileprivate let responseBytes: Data
    fileprivate let record: Components.Schemas.TripRecord
    fileprivate let requestID: String
    fileprivate init(request: TripDetailSnapshotRequest, responseBytes: Data,
                     record: Components.Schemas.TripRecord, requestID: String) {
        self.request = request; self.responseBytes = responseBytes
        self.record = record; self.requestID = requestID
    }
    public var description: String { "<accepted formal Trip detail snapshot>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

/// Per-exchange temporary bytes. Recording here does not establish acceptance.
@MainActor final class TripDetailResponseCapture {
    private(set) var value: (bytes: Data, trace: String)?
    func record(_ bytes: Data, trace: String) throws {
        guard value == nil else { throw TripFailure.invalidResponse }
        value = (bytes, trace)
    }
}

extension TripClient {
    /// Call synchronously at the original selection event, before creating its Task.
    public func prepareDetailSnapshot(id: String, binding: TripBinding) throws -> TripDetailSnapshotRequest {
        guard tripID(id) else { throw TripFailure.invalidInput }
        let previous = detailSnapshotSource
        let token = try capture(binding)
        guard previous == detailSnapshotSource else { throw TripFailure.staleBinding }
        invalidateDetailSnapshots()
        let source = detailSnapshotSource
        let request = TripDetailSnapshotRequest(owner: owner, generation: token, source: source, binding: binding, tripID: id)
        try checkDetailSnapshot(request)
        return request
    }

    /// A selection change retires all earlier requests and accepted snapshots.
    /// Does not clear storage, change authentication or issue a network request.
    public func invalidateDetailSnapshots() {
        detailSnapshotSource = UUID(); startedDetailSnapshotSource = nil
    }

    func retireDetailSnapshots(ifCurrent binding: TripBinding) throws {
        let previous = detailSnapshotSource
        _ = try capture(binding)
        guard previous == detailSnapshotSource else { throw TripFailure.staleBinding }
        invalidateDetailSnapshots()
    }

    private func checkDetailSnapshot(_ request: TripDetailSnapshotRequest) throws {
        guard request.owner == owner, request.source == detailSnapshotSource else { throw TripFailure.staleBinding }
        try check(request.binding, request.generation)
        // currentBinding is a host callback and may have changed the selection.
        guard request.owner == owner, request.source == detailSnapshotSource else { throw TripFailure.staleBinding }
    }

    public func detailSnapshot(for request: TripDetailSnapshotRequest) async throws -> AcceptedTripDetailSnapshot? {
        try checkDetailSnapshot(request)
        guard startedDetailSnapshotSource != request.source else { throw TripFailure.staleBinding }
        startedDetailSnapshotSource = request.source
        let captured = TripDetailResponseCapture()
        let output: Operations.getTrip.Output
        do {
            let client = try await api(request.binding, request.generation,
                                       detailCapture: captured, detailSource: request.source)
            output = try await exchange(request.binding, request.generation) {
                try await client.getTrip(query: .init(trip_id: request.tripID))
            }
        } catch {
            try checkDetailSnapshot(request)
            throw error
        }
        try checkDetailSnapshot(request)
        switch output {
        case .ok(let value):
            do {
                let body = try value.body.json
                switch body.trip {
                case .TripRecord(let record):
                    try validateRecord(record)
                    guard same(record.trip_id, request.tripID), let received = captured.value,
                          same(body.request_id, received.trace) else { throw TripFailure.invalidResponse }
                    try checkDetailSnapshot(request)
                    return AcceptedTripDetailSnapshot(request: request, responseBytes: received.bytes,
                                                      record: record, requestID: received.trace)
                case .case2(let null):
                    guard null.value == nil else { throw TripFailure.invalidResponse }
                    try checkDetailSnapshot(request)
                    return nil
                }
            } catch {
                try checkDetailSnapshot(request)
                if let failure = error as? TripFailure { throw failure }
                throw TripFailure.invalidResponse
            }
        case .default(let status, let value):
            throw TripFailure.rejected(status, try value.body.json.error.code)
        }
    }

    /// Recheck after every consumer await and immediately before using the source.
    /// An unchanged binding alone cannot relabel a snapshot from another client/read.
    public func validateDetailSnapshot(_ snapshot: AcceptedTripDetailSnapshot) throws {
        try checkDetailSnapshot(snapshot.request)
    }

    /// The callback is synchronous and read-only. If it changes identity or source,
    /// its result is withheld. External persistence owns its own pre-write fence.
    public func withCurrentDetailSnapshot<T>(
        _ snapshot: AcceptedTripDetailSnapshot,
        _ read: (Data, Components.Schemas.TripRecord, String, TripBinding) throws -> T
    ) throws -> T {
        try validateDetailSnapshot(snapshot)
        do {
            let result = try read(snapshot.responseBytes, snapshot.record, snapshot.requestID, snapshot.request.binding)
            try validateDetailSnapshot(snapshot)
            return result
        } catch {
            try validateDetailSnapshot(snapshot)
            throw error
        }
    }
}
