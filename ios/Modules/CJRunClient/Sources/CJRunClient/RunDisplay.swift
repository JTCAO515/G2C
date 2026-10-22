import Foundation
import Observation
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime

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
    public nonisolated var customMirror: Mirror { Mirror(self, children: [:]) }
}

@MainActor @Observable public final class RunDisplayModel {
    public typealias Credentials = @MainActor (SessionOperation) async throws -> String?
    private let endpoint: MessageEndpoint
    private let maxMessageIDBytes: Int
    private let maxTextBytes: Int
    private let credentials: Credentials
    private let transport: any ClientTransport
    private let owner = UUID()
    private var epoch = UUID()
    private var source: RunDisplaySource?
    private var executing = false
    private var prepared = false
    private var storedState: RunDisplayState = .unselected
    private var previous: RunDisplayValue?

    public convenience init(endpoint: MessageEndpoint, maximumMessageIDBytes: Int, maximumTextBytes: Int,
                            credentials: @escaping Credentials, liveReadTransport: NoRedirectTransport) throws {
        try self.init(endpoint: endpoint, maximumMessageIDBytes: maximumMessageIDBytes,
                      maximumTextBytes: maximumTextBytes, credentials: credentials, transport: liveReadTransport)
    }
    /// Internal interceptor seam; public composition only accepts the existing no-redirect transport.
    init(endpoint: MessageEndpoint, maximumMessageIDBytes: Int, maximumTextBytes: Int,
         credentials: @escaping Credentials, transport: any ClientTransport) throws {
        guard maximumMessageIDBytes > 0, maximumTextBytes > 0 else { throw RunDisplayFailure.invalidConfiguration }
        self.endpoint = endpoint; maxMessageIDBytes = maximumMessageIDBytes; maxTextBytes = maximumTextBytes
        self.credentials = credentials; self.transport = transport
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
        epoch = UUID(); source = nil; previous = nil; prepared = false; executing = false; storedState = .unselected
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
    public func prepareRead() -> RunDisplayWork? {
        guard !prepared, !executing, let original = source else { return nil }
        let token = epoch
        guard valid(original, token) else { retireIfOwned(original, token); return nil }
        // Reentrant validation may itself prepare work on the same source.
        guard !prepared, !executing, owns(original, token) else { return nil }
        epoch = UUID(); prepared = true; storedState = .loading
        return RunDisplayWork(owner: owner, epoch: epoch, source: original)
    }
    public func perform(_ work: RunDisplayWork?) async {
        guard let work, work.owner == owner, owns(work.source, work.epoch), prepared, !executing else { return }
        prepared = false; executing = true
        let original = work.source, token = work.epoch
        do {
            try check(original, token)
            let bearer = try await credentials(original.operation)
            try check(original, token)
            guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else {
                throw RunDisplayFailure.credentialsUnavailable
            }
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
                try check(original, token)
                previous = value; storedState = .loaded(value); executing = false
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
            storedState = .unavailable(failure); executing = false
        }
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
