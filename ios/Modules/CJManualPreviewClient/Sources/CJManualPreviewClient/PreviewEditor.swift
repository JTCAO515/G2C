import Foundation
import Observation
import CJAPI
import CJTripClient
import CJSession
import CJMessageHTTP
import OpenAPIRuntime

public enum PreviewFailure: Error, Equatable, Sendable {
    case invalidInput, invalidResponse, retired, unavailable, unknown, conflict, rejected(Int)
}
public enum PreviewStatus: Equatable, Sendable { case editing, loading, local, conflict, unknown, invalidResponse, unavailable }

/// Immutable one-use request captured at the synchronous button event. No business action ID.
public final class PreviewWork: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let owner: UUID
    let revision: UUID
    let id = UUID()
    let request: Components.Schemas.ManualPreviewRequest
    let bytes: Data
    init(owner: UUID, revision: UUID, request: Components.Schemas.ManualPreviewRequest, bytes: Data) {
        self.owner = owner; self.revision = revision; self.request = request; self.bytes = bytes
    }
    public var description: String { "<readonly manual preview work>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

public struct PreviewDisplay: Sendable {
    public let original: Components.Schemas.TripRecord
    public let titleSelected: Bool
    public let selectedIDs: [String]
    public let title: String
    public let textUpdates: [String: String]
    public let order: [String]
    public let status: PreviewStatus
    /// Server's exact display bytes and diff; never a locally generated patch.
    public let preview: Components.Schemas.ManualPreview?
}

/// Transient per-selection editor. Host must retire it synchronously on selection/account changes.
@Observable @MainActor public final class PreviewEditor {
    private let trip: TripClient
    private let source: AcceptedTripDetailSnapshot
    private let original: Components.Schemas.TripRecord
    private let originalResponse: Data
    private let originalTrace: String
    private let binding: TripBinding
    private let endpoint: MessageEndpoint
    private let session: SessionLifecycle
    private let operation: SessionOperation
    private let credentials: TripCredentialCallback
    private let transportFactory: @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    private let owner = UUID()
    private var revision = UUID()
    private var preparation = UUID()
    private var active: UUID?
    private var started: UUID?
    private var retired = false
    private var selectedIDs: [String] = []
    private var titleSelected = false
    private var title: String
    private var textUpdates: [String: String] = [:]
    private var order: [String]
    private var orderChanged = false
    private var status: PreviewStatus = .editing
    private var result: Components.Schemas.ManualPreview?

    public convenience init(trip: TripClient, source: AcceptedTripDetailSnapshot, endpoint: MessageEndpoint,
                            session: SessionLifecycle, operation: SessionOperation,
                            credentials: @escaping TripCredentialCallback, liveTransport: NoRedirectTransport) throws {
        try self.init(trip: trip, source: source, endpoint: endpoint, session: session, operation: operation,
                      credentials: credentials, interceptedTransport: liveTransport)
    }
    /// Explicit readonly computation opt-in. The shared validator is bound to each
    /// original work/source/session, including revision ABA and callback reentry.
    public convenience init(trip: TripClient, source: AcceptedTripDetailSnapshot, endpoint: MessageEndpoint,
                            session: SessionLifecycle, operation: SessionOperation,
                            credentials: @escaping TripCredentialCallback,
                            previewRequestTimeout: TimeInterval, previewResourceTimeout: TimeInterval) throws {
        guard previewRequestTimeout > 0, previewResourceTimeout > 0,
              previewRequestTimeout.isFinite, previewResourceTimeout.isFinite else { throw PreviewFailure.invalidInput }
        try self.init(trip: trip, source: source, endpoint: endpoint, session: session, operation: operation,
                      credentials: credentials, transportFactory: { validate in
            try NoRedirectTransport.readOnlyManualPreview(endpoint: endpoint, requestTimeout: previewRequestTimeout,
                resourceTimeout: previewResourceTimeout, validate: validate)
        })
    }
    /// Only module tests may inject a non-network transport.
    convenience init(trip: TripClient, source: AcceptedTripDetailSnapshot, endpoint: MessageEndpoint,
         session: SessionLifecycle, operation: SessionOperation,
         credentials: @escaping TripCredentialCallback, interceptedTransport: any ClientTransport) throws {
        try self.init(trip: trip, source: source, endpoint: endpoint, session: session, operation: operation,
                      credentials: credentials, transportFactory: { _ in interceptedTransport })
    }
    /// Internal factory seam for testing the actual shared capability without URLSession traffic.
    init(trip: TripClient, source: AcceptedTripDetailSnapshot, endpoint: MessageEndpoint,
         session: SessionLifecycle, operation: SessionOperation,
         credentials: @escaping TripCredentialCallback,
         transportFactory: @escaping @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport) throws {
        let captured = try trip.withCurrentDetailSnapshot(source) { ($0, $1, $2, $3) }
        guard session.isCurrent(operation) else { throw PreviewFailure.retired }
        self.trip = trip; self.source = source; originalResponse = captured.0; original = captured.1
        originalTrace = captured.2; binding = captured.3; self.endpoint = endpoint
        self.session = session; self.operation = operation; self.credentials = credentials; self.transportFactory = transportFactory
        title = original.document.title; order = original.document.items.map(\.id)
        try check()
    }
    private func check(revision expected: UUID? = nil, work: PreviewWork? = nil, preparation expectedPreparation: UUID? = nil, cancellation: Bool = true) throws {
        func local() throws {
            guard !retired, session.isCurrent(operation), expected == nil || expected == revision,
                  expectedPreparation == nil || expectedPreparation == preparation,
                  work == nil || (work?.owner == owner && work?.id == active) else { throw PreviewFailure.retired }
        }
        try local()
        try trip.validateDetailSnapshot(source) // host callback may synchronously edit or retire us
        try local()
        if cancellation { try Task.checkCancellation() }
    }
    public func retire() { retired = true; revision = UUID(); active = nil; result = nil; textUpdates = [:]; title = ""; order = []; selectedIDs = [] }
    public func display() -> PreviewDisplay? {
        let token = revision
        guard (try? check(revision: token, cancellation: false)) != nil else { return nil }
        return .init(original: original, titleSelected: titleSelected, selectedIDs: selectedIDs, title: title,
                     textUpdates: textUpdates, order: order, status: status, preview: result)
    }
    private func edit(_ change: () throws -> Void) throws {
        let token = revision; try check(revision: token)
        try change()
        revision = UUID(); active = nil; result = nil; status = .editing
    }
    public func selectTitle(_ selected: Bool) throws {
        try edit { titleSelected = selected; if !selected { title = original.document.title } }
    }
    public func selectItem(_ id: String, selected: Bool) throws {
        guard original.document.items.contains(where: { exact($0.id, id) }) else { throw PreviewFailure.invalidInput }
        try edit {
            selectedIDs.removeAll { exact($0, id) }
            if selected { selectedIDs.append(id) } else { textUpdates.removeValue(forKey: id) }
            order = original.document.items.map(\.id); orderChanged = false
        }
    }
    public func setTitle(_ value: String) throws {
        guard titleSelected else { throw PreviewFailure.invalidInput }
        try edit { title = value }
    }
    public func setText(_ value: String, for id: String) throws {
        guard selectedIDs.contains(where: { exact($0, id) }) else { throw PreviewFailure.invalidInput }
        try edit { textUpdates[id] = value }
    }
    public func setOrder(_ value: [String]) throws {
        let old = original.document.items.map(\.id)
        guard value.count == old.count, Set(value.map { Data($0.utf8) }) == Set(old.map { Data($0.utf8) }),
              zip(old, value).allSatisfy({ selectedIDs.contains($0.0) || exact($0.0, $0.1) }) else { throw PreviewFailure.invalidInput }
        try edit { order = value; orderChanged = true }
    }
    /// Freeze generated input and its UTF8 before starting a Task. No refresh/rebase or automatic retry.
    public func preparePreview() throws -> PreviewWork {
        let token = revision
        // Reserve before source callbacks: a nested prepare owns its newer work even
        // when the draft did not change and this older caller discards its result.
        let preparing = UUID(); preparation = preparing
        try check(revision: token, preparation: preparing)
        guard !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              textUpdates.values.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else { throw PreviewFailure.invalidInput }
        let request = Components.Schemas.ManualPreviewRequest(trip_id: original.trip_id, expected_version: original.version,
            original_content_utf8_base64: original.content_utf8_base64, selected_ids: selectedIDs, title_selected: titleSelected,
            title: titleSelected ? .case1(title) : .case2(try .init()),
            text_updates: selectedIDs.compactMap { id in textUpdates[id].map { .init(item_id: id, text: $0) } },
            order: orderChanged ? .case1(order) : .case2(try .init()))
        let bytes = try encoded(request)
        guard bytes.count <= endpoint.maximumRequestBytes else { throw PreviewFailure.invalidInput }
        try check(revision: token, preparation: preparing)
        let work = PreviewWork(owner: owner, revision: token, request: request, bytes: bytes)
        active = work.id; started = nil; result = nil; status = .loading
        return work
    }
    public func cancelPreview() {
        revision = UUID(); active = nil; result = nil; status = .unknown
    }
    public func perform(_ work: PreviewWork) async {
        do {
            try check(revision: work.revision, work: work)
            guard started != work.id else { return }; started = work.id
            let bearer = try await credentials(binding)
            try check(revision: work.revision, work: work)
            guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw PreviewFailure.unavailable }
            let validate: @MainActor @Sendable () throws -> Void = { [self] in
                try check(revision: work.revision, work: work)
            }
            let transport = try transportFactory(validate)
            try check(revision: work.revision, work: work)
            let client = Client(serverURL: endpoint.url, configuration: .memory,
                transport: PreviewTransport(underlying: transport, endpoint: endpoint, bearer: bearer, requestBytes: work.bytes,
                    validate: validate))
            let output = try await client.previewManualTripEdit(body: .json(work.request))
            try check(revision: work.revision, work: work)
            switch output {
            case .ok(let response):
                let preview = try response.body.json.preview
                try validatePreview(preview, request: work.request, original: original)
                try check(revision: work.revision, work: work)
                result = preview; status = .local
            case .default(let code, _):
                status = code == 409 ? .conflict : .unknown
            }
        } catch {
            let cause = (error as? ClientError)?.underlyingError ?? error
            let invalid = (cause as? PreviewFailure) == .invalidResponse || cause is DecodingError
            let unavailable = (cause as? PreviewFailure) == .unavailable ||
                (cause as? MessageHTTPFailure).map { if case .productionActivationUnavailable = $0 { true } else { false } } == true
            let failureStatus: PreviewStatus = invalid ? .invalidResponse : (unavailable ? .unavailable : .unknown)
            if Task.isCancelled {
                // The Trip public guard checks Task cancellation too. A separate UI-only
                // settlement checks the SAME captured work/source, never prepares new work.
                await Task { @MainActor in self.settleFailure(work, status: failureStatus) }.value
            } else { settleFailure(work, status: failureStatus) }
        }
    }
    private func settleFailure(_ work: PreviewWork, status failureStatus: PreviewStatus) {
        guard (try? check(revision: work.revision, work: work)) != nil else { return }
        result = nil; status = failureStatus
    }
}

func exact(_ a: String, _ b: String) -> Bool { Data(a.utf8) == Data(b.utf8) }
func encoded<T: Encodable>(_ value: T) throws -> Data {
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    return try encoder.encode(value)
}
