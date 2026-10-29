import Foundation
import Observation
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

public enum RunDisplayFailure: Error, Equatable, Sendable {
    case invalidConfiguration, invalidReference, unavailable, invalidResponse
    case staleContext, cancelled, credentialsUnavailable, inconsistentSnapshot
    case rejected(status: Int)
}

/// Trusted composition input. Receipt must come from accepted canonical MESSAGE recovery
/// or accepted host context, never UI text. It proves linkage, not RUN creation.
/// Host callback must recheck source ownership AND current UI selection/lifecycle/admission.
/// It grants no server permission; no caller principal, scope or token-derived identity.
@MainActor public final class RunDisplaySource: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let receipt: Components.Schemas.MessageReceipt
    let session: SessionLifecycle
    let operation: SessionOperation
    let isCurrent: @MainActor () -> Bool
    public init(receipt: Components.Schemas.MessageReceipt, session: SessionLifecycle,
                operation: SessionOperation, isCurrent: @escaping @MainActor () -> Bool) throws {
        guard receipt.sequence > 0,
              [receipt.message_id, receipt.conversation_id, receipt.generation, receipt.run_id].allSatisfy({ !$0.isEmpty }) else {
            throw RunDisplayFailure.invalidReference
        }
        self.receipt = receipt; self.session = session; self.operation = operation; self.isCurrent = isCurrent
    }
    public nonisolated var description: String { "<redacted original run source>" }
    public nonisolated var debugDescription: String { description }
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

/// Session-only display value; no Codable, persistent store, or sensitive debug projection.
public struct RunDisplayValue: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let snapshot: Components.Schemas.RunDisplaySnapshot
    public let requestID: String
    public var description: String { "<redacted run display>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}
public enum RunDisplayState: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    case unselected, ready, loading, loaded(RunDisplayValue), unavailable(RunDisplayFailure)
    public var description: String { "<redacted run display state>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

/// Opaque, single-use original work captured synchronously before a UI Task is enqueued.
@MainActor public struct RunDisplayWork: CustomReflectable {
    fileprivate let owner: UUID
    fileprivate let epoch: UUID
    fileprivate let source: RunDisplaySource
    fileprivate let streaming: Bool
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

public enum RunCancellationState: Sendable { case idle, stopping, unknown }
@MainActor public struct RunCancellationWork: CustomReflectable {
    fileprivate let owner: UUID
    fileprivate let epoch: UUID
    fileprivate let source: RunDisplaySource
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

@MainActor @Observable public final class RunDisplayModel {
    public typealias Credentials = @MainActor (SessionOperation) async throws -> String?
    private let endpoint: MessageEndpoint
    private let maxMessageIDBytes: Int
    private let maxTextBytes: Int
    private let credentials: Credentials
    private let transport: any ClientTransport
    private let cancellationTransport: (any ClientTransport)?
    private var cancellationPrepared = false
    private var storedCancellation: RunCancellationState = .idle
    private let owner = UUID()
    private var epoch = UUID()
    private var source: RunDisplaySource?
    private var executing = false
    private var prepared = false
    private var storedState: RunDisplayState = .unselected
    private var previous: RunDisplayValue?
    private var storedStream: RunStreamProgress?

    public var streamProgress: RunStreamProgress? {
        guard let original = source else { return nil }
        let token = epoch
        guard valid(original, token) else { retireIfOwned(original, token); return nil }
        return storedStream
    }

    public convenience init(endpoint: MessageEndpoint, maximumMessageIDBytes: Int, maximumTextBytes: Int,
                            credentials: @escaping Credentials, liveReadTransport: NoRedirectTransport,
                            liveCancellationTransport: RunCancellationTransport? = nil) throws {
        try self.init(endpoint: endpoint, maximumMessageIDBytes: maximumMessageIDBytes,
                      maximumTextBytes: maximumTextBytes, credentials: credentials, transport: liveReadTransport, cancellationTransport: liveCancellationTransport)
    }
    /// Internal interceptor seam; public composition only accepts the existing no-redirect transport.
    init(endpoint: MessageEndpoint, maximumMessageIDBytes: Int, maximumTextBytes: Int,
         credentials: @escaping Credentials, transport: any ClientTransport, cancellationTransport: (any ClientTransport)? = nil) throws {
        guard maximumMessageIDBytes > 0, maximumTextBytes > 0 else { throw RunDisplayFailure.invalidConfiguration }
        self.endpoint = endpoint; maxMessageIDBytes = maximumMessageIDBytes; maxTextBytes = maximumTextBytes
        self.credentials = credentials; self.transport = transport; self.cancellationTransport = cancellationTransport
    }
    /// Fail closed on access too: host still must eagerly invalidate when its ownership changes.
    public var state: RunDisplayState {
        guard let source else { return storedState }
        let token = epoch
        guard valid(source, token) else {
            retireIfOwned(source, token)
            return .unavailable(.staleContext)
        }
        return storedState
    }
    @discardableResult public func select(_ original: RunDisplaySource) -> Bool {
        invalidate(); source = original
        let token = epoch
        guard original.receipt.message_id.utf8.count <= maxMessageIDBytes, valid(original, token) else {
            retireIfOwned(original, token); return false
        }
        storedState = .ready
        return true
    }
    /// Call synchronously for selection/source/account/auth changes, background and disappearance.
    /// Resuming requires a newly accepted source. Does not cancel the server RUN.
    public func invalidate() {
        cancellationPrepared = false; storedCancellation = .idle
        epoch = UUID(); source = nil; previous = nil; storedStream = nil; prepared = false; executing = false; storedState = .unselected
    }
    private func owns(_ original: RunDisplaySource, _ token: UUID) -> Bool { source === original && epoch == token }
    private func valid(_ original: RunDisplaySource, _ token: UUID) -> Bool {
        guard owns(original, token), original.session.isCurrent(original.operation) else { return false }
        let current = original.isCurrent()
        return current && owns(original, token) && original.session.isCurrent(original.operation)
    }
    private func retireIfOwned(_ original: RunDisplaySource, _ token: UUID) {
        guard owns(original, token) else { return }
        invalidate(); storedState = .unavailable(.staleContext)
    }
    private func check(_ original: RunDisplaySource, _ token: UUID) throws {
        guard valid(original, token) else { throw RunDisplayFailure.staleContext }
        guard !Task.isCancelled else { throw RunDisplayFailure.cancelled }
    }
    public func prepareRead() -> RunDisplayWork? { prepare(streaming: false) }
    /// Explicit GET-only continuation; never resends a message or starts a model run.
    public func prepareStream() -> RunDisplayWork? { prepare(streaming: true) }
    private func prepare(streaming: Bool) -> RunDisplayWork? {
        guard !prepared, !executing, !cancellationPrepared, storedCancellation != .stopping, let original = source else { return nil }
        let token = epoch
        guard valid(original, token) else { retireIfOwned(original, token); return nil }
        // Reentrant validation may itself prepare work on the same source.
        guard !prepared, !executing, !cancellationPrepared, storedCancellation != .stopping, owns(original, token) else { return nil }
        epoch = UUID(); prepared = true; storedState = .loading
        return RunDisplayWork(owner: owner, epoch: epoch, source: original, streaming: streaming)
    }
    /// A just-accepted MESSAGE can precede the worker's RUN row. Retry only this
    /// initial 503 read, at most three GET attempts, never after any stream progress.
    public func performInitialStream(_ work: RunDisplayWork?) async {
        guard let work, work.streaming else { return }
        await perform(work)
        var completedEpoch = work.epoch
        for _ in 0..<2 {
            guard owns(work.source, completedEpoch), storedStream == nil, previous == nil,
                  storedCancellation == .idle,
                  case .unavailable(.rejected(status: 503)) = storedState else { return }
            do {
                try check(work.source, completedEpoch)
                try await Task.sleep(for: .milliseconds(200))
                try check(work.source, completedEpoch)
            } catch { return }
            guard let retry = prepareStream() else { return }
            completedEpoch = retry.epoch
            await perform(retry)
        }
    }

    public func perform(_ work: RunDisplayWork?) async {
        guard let work, work.owner == owner, owns(work.source, work.epoch), prepared, !executing else { return }
        prepared = false; executing = true
        let original = work.source, token = work.epoch
        do {
            try check(original, token)
            let bearer: String?
            do { bearer = try await credentials(original.operation) }
            catch { try check(original, token); throw RunDisplayFailure.credentialsUnavailable }
            try check(original, token)
            guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else {
                throw RunDisplayFailure.credentialsUnavailable
            }
            if work.streaming { try await receiveEvents(original, token, bearer: bearer) }
            let checked = RunReadTransport(underlying: transport, endpoint: endpoint, bearer: bearer,
                originalMessageID: original.receipt.message_id, validate: { [self] in try check(original, token) })
            let client = Client(serverURL: endpoint.url, configuration: .memory, transport: checked)
            let response = try await client.getRunDisplaySnapshot(query: .init(message_id: original.receipt.message_id))
            try check(original, token)
            switch response {
            case .ok(let response):
                let body = try response.body.json
                try validate(body.snapshot, original: original.receipt)
                let value = RunDisplayValue(snapshot: body.snapshot, requestID: body.request_id)
                if let previous { try validateProgress(body.snapshot, after: previous.snapshot) }
                if work.streaming, let progress = storedStream {
                    guard exact(body.snapshot.text, progress.text), body.snapshot.status.rawValue == progress.status else {
                        throw RunDisplayFailure.inconsistentSnapshot
                    }
                }
                try check(original, token)
                previous = value; storedStream = nil; storedState = .loaded(value); executing = false; storedCancellation = .idle
            case .default(let status, let response):
                _ = try response.body.json // Official BASE decoding; never publish raw server error text.
                throw RunDisplayFailure.rejected(status: status)
            }
        } catch {
            // Generated ClientError may contain the bearer/body. Never expose, log or stringify it.
            guard valid(original, token) else { retireIfOwned(original, token); return }
            let failure: RunDisplayFailure
            if Task.isCancelled || error is CancellationError { failure = .cancelled }
            else { failure = (error as? RunDisplayFailure) ?? .unavailable }
            switch failure {
            case .rejected, .credentialsUnavailable, .invalidResponse, .inconsistentSnapshot:
                storedStream = nil
            default: break // A transport interruption alone retains visibly partial text.
            }
            storedState = .unavailable(failure); executing = false
        }
    }
    public var supportsCancellation: Bool { cancellationTransport != nil }
    public var cancellationState: RunCancellationState {
        guard let original = source else { return .idle }
        let token = epoch
        guard valid(original, token) else { retireIfOwned(original, token); return .idle }
        return storedCancellation
    }
    public var canCancel: Bool {
        guard cancellationTransport != nil, storedCancellation == .idle, !cancellationPrepared,
              let original = source else { return false }
        let token = epoch
        guard valid(original, token), storedCancellation == .idle, owns(original, token) else { return false }
        if let status = storedStream?.status ?? previous?.snapshot.status.rawValue {
            return status == "queued" || status == "running"
        }
        return true
    }
    public func prepareCancellation() -> RunCancellationWork? {
        guard canCancel, let original = source else { return nil }
        // Retire any in-flight read before cancellation, without erasing received text.
        if storedStream == nil, let previous {
            storedStream = RunStreamProgress(text: previous.snapshot.text, status: previous.snapshot.status.rawValue)
        }
        epoch = UUID(); prepared = false; executing = false; cancellationPrepared = true
        storedCancellation = .stopping
        return RunCancellationWork(owner: owner, epoch: epoch, source: original)
    }
    public func performCancellation(_ work: RunCancellationWork?) async {
        guard let work, work.owner == owner, cancellationPrepared, let cancellationTransport,
              owns(work.source, work.epoch), storedCancellation == .stopping else { return }
        cancellationPrepared = false
        let original = work.source, token = work.epoch
        do {
            try check(original, token)
            let bearer = try await credentials(original.operation)
            try check(original, token)
            guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else {
                throw RunDisplayFailure.credentialsUnavailable
            }
            let input = Components.Schemas.RunCancellationRequest(version: .RUN_hyphen_cancel_period_1,
                                                                  message_id: original.receipt.message_id)
            var request = HTTPRequest(method: .post, scheme: nil, authority: nil, path: "/v1/run-cancellations")
            request.headerFields[.contentType] = "application/json"
            request.headerFields[.authorization] = "Bearer " + bearer
            let (response, responseBody) = try await cancellationTransport.send(request,
                body: HTTPBody(try JSONEncoder().encode(input)), baseURL: endpoint.url, operationID: Operations.cancelOriginalRun.id)
            try check(original, token)
            guard response.status.code == 200 else { throw RunDisplayFailure.rejected(status: response.status.code) }
            guard let responseBody else { throw RunDisplayFailure.invalidResponse }
            let bytes = try await Data(collecting: responseBody, upTo: endpoint.maximumResponseBytes)
            try check(original, token)
            let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
            let controls = response.headerFields.filter { $0.name == .cacheControl }
            let media = response.headerFields.filter { $0.name == .contentType }
            guard traces.count == 1, UUID(uuidString: traces[0].value) != nil,
                  controls.count == 1, controls[0].value.lowercased() == "no-store",
                  media.count == 1, media[0].value.split(separator: ";").first?.lowercased() == "application/json" else {
                throw RunDisplayFailure.invalidResponse
            }
            var parser = StrictRunJSON(bytes: Array(bytes)); try parser.check()
            let receipt = try JSONDecoder().decode(Components.Schemas.RunCancellationResponse.self, from: bytes)
            guard exact(receipt.request_id, traces[0].value), exact(receipt.message_id, original.receipt.message_id),
                  exact(receipt.run_id, original.receipt.run_id), receipt.event_highwater > 0 else { throw RunDisplayFailure.invalidResponse }
            let checked = RunReadTransport(underlying: transport, endpoint: endpoint, bearer: bearer,
                originalMessageID: original.receipt.message_id, validate: { [self] in try check(original, token) })
            let api = Client(serverURL: endpoint.url, configuration: .memory, transport: checked)
            let output = try await api.getRunDisplaySnapshot(query: .init(message_id: original.receipt.message_id))
            try check(original, token)
            guard case .ok(let response) = output else { throw RunDisplayFailure.unavailable }
            let body = try response.body.json
            try validate(body.snapshot, original: original.receipt)
            guard body.snapshot.status.rawValue == receipt.status.rawValue,
                  body.snapshot.event_highwater == receipt.event_highwater,
                  body.snapshot.text.utf8.starts(with: (storedStream?.text ?? "").utf8) else { throw RunDisplayFailure.inconsistentSnapshot }
            if let previous { try validateProgress(body.snapshot, after: previous.snapshot) }
            try check(original, token)
            let value = RunDisplayValue(snapshot: body.snapshot, requestID: body.request_id)
            previous = value; storedStream = nil; storedState = .loaded(value); storedCancellation = .idle
        } catch {
            guard valid(original, token) else { retireIfOwned(original, token); return }
            let failure = (error as? RunDisplayFailure) ?? .unavailable
            switch failure {
            case .rejected(status: 401), .rejected(status: 403), .credentialsUnavailable, .invalidResponse, .inconsistentSnapshot:
                storedStream = nil
            default: break // Uncertain transport outcome retains only visibly partial text.
            }
            storedCancellation = .unknown
            storedState = .unavailable(failure) // sanitized; original read is the recovery path
        }
    }

    private func receiveEvents(_ original: RunDisplaySource, _ token: UUID, bearer: String) async throws {
        let prefix = storedStream?.text ?? previous?.snapshot.text ?? ""
        var parser = try RunEventParser(text: prefix, maximumTextBytes: maxTextBytes,
                                        maximumWireBytes: endpoint.maximumResponseBytes)
        var components = URLComponents()
        components.path = "/v1/run-events"
        components.queryItems = [URLQueryItem(name: "message_id", value: original.receipt.message_id)]
        // Query decoders treat a literal '+' as a space; opaque IDs must survive exactly.
        components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        guard let path = components.string else { throw RunDisplayFailure.invalidReference }
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: path)
        request.headerFields[.authorization] = "Bearer " + bearer
        request.headerFields[.accept] = "text/event-stream"
        request.headerFields[HTTPField.Name("Last-Event-ID")!] = String(prefix.utf8.count)
        try check(original, token)
        let (response, body) = try await transport.send(request, body: nil, baseURL: endpoint.url,
                                                         operationID: "streamRunEvents")
        try check(original, token)
        guard response.status.code == 200 else { throw RunDisplayFailure.rejected(status: response.status.code) }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let controls = response.headerFields.filter { $0.name == .cacheControl }
        let media = response.headerFields.filter { $0.name == .contentType }
        guard traces.count == 1, UUID(uuidString: traces[0].value) != nil,
              controls.count == 1, controls[0].value.lowercased() == "no-store",
              media.count == 1, media[0].value.split(separator: ";").first?.lowercased() == "text/event-stream",
              let body else { throw RunDisplayFailure.invalidResponse }
        for try await chunk in body {
            try check(original, token)
            if let progress = try parser.append(chunk) {
                try check(original, token)
                storedStream = progress
            }
        }
        try check(original, token)
        try parser.finish()
        // SSE has no RUN highwater or complete receipt binding. The existing canonical
        // snapshot GET below verifies both before any final successful display state.
    }

    private func validate(_ value: Components.Schemas.RunDisplaySnapshot, original: Components.Schemas.MessageReceipt) throws {
        guard exact(value.message_id, original.message_id), exact(value.conversation_id, original.conversation_id),
              exact(value.generation, original.generation), exact(value.run_id, original.run_id),
              value.message_sequence == original.sequence, value.message_sequence > 0, value.event_highwater >= 0,
              value.text.utf8.count <= maxTextBytes,
              value.status == .queued ? (value.event_highwater == 0 && value.text.isEmpty) : value.event_highwater > 0,
              (value.status == .completed) == (value.text_state == .complete) else { throw RunDisplayFailure.invalidResponse }
    }
    private func validateProgress(_ new: Components.Schemas.RunDisplaySnapshot, after old: Components.Schemas.RunDisplaySnapshot) throws {
        guard new.event_highwater >= old.event_highwater, new.text.utf8.starts(with: old.text.utf8) else { throw RunDisplayFailure.inconsistentSnapshot }
        if new.event_highwater == old.event_highwater {
            guard new.status == old.status, new.text_state == old.text_state, exact(new.text, old.text) else {
                throw RunDisplayFailure.inconsistentSnapshot
            }
        }
        // A terminal observation cannot be silently revived, even at a larger highwater.
        if old.status != .queued && old.status != .running {
            guard new.status == old.status, new.event_highwater == old.event_highwater, exact(new.text, old.text) else {
                throw RunDisplayFailure.inconsistentSnapshot
            }
        }
        if old.status == .running && new.status == .queued { throw RunDisplayFailure.inconsistentSnapshot }
    }
}
func exact(_ a: String, _ b: String) -> Bool { a.utf8.elementsEqual(b.utf8) }
