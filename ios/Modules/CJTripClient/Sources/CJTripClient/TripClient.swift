import Foundation
import CJAPI
import CJMessageHTTP
import CJSession
import OpenAPIRuntime

/// One domain client per host lifetime. Reads never issue confirmation or authorize POST.
@MainActor public final class TripClient {
    let endpoint: TripEndpoint
    let credentials: TripCredentialCallback
    let currentBinding: @MainActor () -> TripBinding?
    let transport: any ClientTransport
    private let session: SessionLifecycle?
    private let sessionOperation: SessionOperation?
    let testWrites: Bool
    let liveWrites: Bool
    let store: TripPendingStore?
    var confirmed = Set<Data>()
    let owner = UUID()
    var generation = UUID()
    var detailSnapshotSource = UUID()
    var startedDetailSnapshotSource: UUID?

    public init(endpoint: TripEndpoint, credentials: @escaping TripCredentialCallback,
                currentBinding: @escaping @MainActor () -> TripBinding?, session: SessionLifecycle, sessionOperation: SessionOperation,
                pendingStore: TripPendingStore? = nil, liveReadTransport: NoRedirectTransport) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        transport = liveReadTransport; testWrites = false; liveWrites = false; store = pendingStore
        self.session = session; self.sessionOperation = sessionOperation
    }
    /// Live reads plus prepare/confirm writes. Requires the encrypted pending store, so every
    /// confirmed action is durable before it leaves the device.
    public init(endpoint: TripEndpoint, credentials: @escaping TripCredentialCallback,
                currentBinding: @escaping @MainActor () -> TripBinding?, session: SessionLifecycle, sessionOperation: SessionOperation,
                pendingStore: TripPendingStore, liveTransport: NoRedirectTransport, liveWrites: TripLiveWrites) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        _ = liveWrites
        transport = TripLiveTransport(reads: liveTransport, endpoint: endpoint.url)
        testWrites = false; self.liveWrites = true; store = pendingStore
        self.session = session; self.sessionOperation = sessionOperation
    }
    /// Internal test-only injection. Not a public capability to enable live writes.
    init(endpoint: TripEndpoint, credentials: @escaping TripCredentialCallback,
         currentBinding: @escaping @MainActor () -> TripBinding?, pendingStore: TripPendingStore? = nil,
         session: SessionLifecycle? = nil, sessionOperation: SessionOperation? = nil, interceptedTransport: any ClientTransport) {
        self.endpoint = endpoint; self.credentials = credentials; self.currentBinding = currentBinding
        transport = interceptedTransport; testWrites = true; liveWrites = false; store = pendingStore
        self.session = session; self.sessionOperation = sessionOperation
    }
    public func invalidate() { generation = UUID(); confirmed.removeAll(); invalidateDetailSnapshots() }
    /// True only for a host-granted live-write client with a durable pending store.
    public var acceptsUserActions: Bool { liveWrites && store != nil }
    var writesEnabled: Bool { testWrites || liveWrites }
    private var sessionIsCurrent: Bool {
        if let session, let sessionOperation { return session.isCurrent(sessionOperation) }
        return testWrites && session == nil && sessionOperation == nil
    }
    // Ownership may still be current after cancellation; UI must settle to unknown, not remain busy.
    func ownsBinding(_ binding: TripBinding) -> Bool {
        let token = generation
        let observed = currentBinding()
        return generation == token && observed == binding && sessionIsCurrent
    }
    func check(_ binding: TripBinding, _ token: UUID) throws {
        guard generation == token else { throw TripFailure.staleBinding }
        let observed = currentBinding()
        guard generation == token, observed == binding, sessionIsCurrent else { throw TripFailure.staleBinding }
        try Task.checkCancellation()
    }
    func capture(_ binding: TripBinding) throws -> UUID {
        let token = generation; try check(binding, token); return token
    }
    func api(_ binding: TripBinding, _ token: UUID,
             original: TripPending? = nil, detailCapture: TripDetailResponseCapture? = nil,
             detailSource: UUID? = nil) async throws -> Client {
        try check(binding, token)
        let bearer: String?
        do { bearer = try await credentials(binding) }
        catch { try check(binding, token); throw TripFailure.unconfigured }
        try check(binding, token)
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw TripFailure.unconfigured }
        return Client(serverURL: endpoint.url, configuration: .memory,
                      transport: TripTransport(underlying: transport, endpoint: endpoint, bearer: bearer, writes: writesEnabled, detailCapture: detailCapture,
                        validate: { [self] in
                            try check(binding, token)
                            if let detailSource, detailSnapshotSource != detailSource { throw TripFailure.staleBinding }
                            if let original {
                                guard let store else { throw TripFailure.unconfigured }
                                let proof = try store.requireOriginal(original)
                                try check(binding, token)
                                // Last resource callback has returned. Do not call it again after this check.
                                try store.validateDurability(proof)
                            }
                        }))
    }
    func exchange<T>(_ binding: TripBinding, _ token: UUID, _ work: () async throws -> T) async throws -> T {
        do { let value = try await work(); try check(binding, token); return value }
        catch {
            try check(binding, token)
            // Do not expose generated ClientError: it may include bearer/URL/private body.
            throw TripFailure.exchangeUnknown
        }
    }
    public func proposal(id: String, binding: TripBinding) async throws -> Components.Schemas.SourceTripProposalSnapshot {
        let token = try capture(binding)
        guard tripID(id) else { throw TripFailure.invalidInput }
        let client = try await api(binding, token)
        let output = try await exchange(binding, token) { try await client.getTripProposal(query: .init(proposal_id: id), headers: .init(X_hyphen_CJ_hyphen_Trip_hyphen_Content: .provenance_period_1)) }
        switch output {
        case .ok(let value):
            let proposal = try value.body.json.sourceProposal
            try validateProposal(proposal)
            guard same(proposal.proposal_id, id) else { throw TripFailure.invalidResponse }
            return proposal
        case .default(let status, let value): throw TripFailure.rejected(status, try value.body.json.error.code)
        }
    }
    public func detail(id: String, binding: TripBinding) async throws -> Components.Schemas.SourceTripRecord? {
        let previousSource = detailSnapshotSource
        let token = try capture(binding)
        guard tripID(id) else { throw TripFailure.invalidInput }
        guard previousSource == detailSnapshotSource else { throw TripFailure.staleBinding }
        invalidateDetailSnapshots()
        return try await readDetail(id: id, binding: binding, token: token)
    }
    // Presentation work already retired/captured its source synchronously. Do not
    // retire a newer source by starting an older queued or in-flight UI read.
    func selectedDetail(id: String, binding: TripBinding, source: UUID) async throws -> Components.Schemas.SourceTripRecord? {
        let token = try capture(binding)
        guard source == detailSnapshotSource else { throw TripFailure.staleBinding }
        guard tripID(id) else { throw TripFailure.invalidInput }
        return try await readDetail(id: id, binding: binding, token: token, source: source)
    }
    private func readDetail(id: String, binding: TripBinding, token: UUID,
                            source: UUID? = nil) async throws -> Components.Schemas.SourceTripRecord? {
        let client = try await api(binding, token, detailSource: source)
        let output = try await exchange(binding, token) { try await client.getTrip(query: .init(trip_id: id), headers: .init(X_hyphen_CJ_hyphen_Trip_hyphen_Content: .provenance_period_1)) }
        if let source, detailSnapshotSource != source { throw TripFailure.staleBinding }
        switch output {
        case .ok(let value):
            guard let trip = try value.body.json.sourceTrip() else { return nil }
            try validateRecord(trip)
            guard same(trip.trip_id, id) else { throw TripFailure.invalidResponse }
            return trip
        case .default(let status, let value): throw TripFailure.rejected(status, try value.body.json.error.code)
        }
    }
    public func list(limit: Int, after: TripCursor? = nil, binding: TripBinding) async throws -> TripPage {
        let token = try capture(binding)
        guard (1...100).contains(limit) else { throw TripFailure.invalidInput }
        if let after { guard after.owner == owner, after.binding == binding else { throw TripFailure.staleBinding } }
        let client = try await api(binding, token)
        let output = try await exchange(binding, token) { try await client.listTrips(query: .init(limit: limit, after: after?.after), headers: .init(X_hyphen_CJ_hyphen_Trip_hyphen_Content: .provenance_period_1)) }
        switch output {
        case .ok(let value):
            let body = try value.body.json.sourcePage
            guard body.trips.count <= limit else { throw TripFailure.invalidResponse }
            var previous = after?.after ?? ""
            for trip in body.trips {
                try validateRecord(trip)
                guard previous.utf8.lexicographicallyPrecedes(trip.trip_id.utf8) else { throw TripFailure.invalidResponse }
                previous = trip.trip_id
            }
            let next: TripCursor?
            switch body.next_after {
            case .case1(let id):
                guard let last = body.trips.last, same(last.trip_id, id) else { throw TripFailure.invalidResponse }
                next = TripCursor(owner: owner, binding: binding, after: id)
            case .case2(let null):
                guard null.value == nil, body.trips.isEmpty else { throw TripFailure.invalidResponse }; next = nil
            }
            return TripPage(trips: body.trips, next: next)
        case .default(let status, let value): throw TripFailure.rejected(status, try value.body.json.error.code)
        }
    }
}
