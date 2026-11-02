import Foundation
import CJSession
import CJAPI
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

/// Host-owned lifetime for one selected original account workflow. It remains
/// usable for restricted progress after ordinary SDK clear, and is explicitly
/// invalidated on account/progress-scope selection changes. It grants no business access.
@MainActor public final class AccountCleanupLifetime {
    public let scope: AccountCleanupScope
    private(set) var active = true
    public init(scope: AccountCleanupScope) { self.scope = scope }
    public func invalidate() { active = false }
}
public enum AccountCleanupClientState: Sendable {
    case ready, registrationUnknown, registered, preparationUnknown
    case awaitingConfirmation(AccountCleanupPreparation), confirmationStaged(AccountCleanupPreparation)
    case confirmationUnknown(AccountCleanupPreparation), progress(AccountCleanupProgress), unavailable
}
fileprivate enum AccountCleanupWorkKind: Equatable { case registration, preparation, confirmation, preparationQuery, progress }
/// Opaque work is captured synchronously at the user's explicit event.
@MainActor public final class AccountCleanupWork {
    fileprivate let owner: UUID
    fileprivate let kind: AccountCleanupWorkKind
    fileprivate let originalRecord: Data
    fileprivate let path: String
    fileprivate let operation: String
    fileprivate let body: Data?
    fileprivate var consumed = false
    fileprivate init(owner: UUID, kind: AccountCleanupWorkKind, originalRecord: Data, path: String, operation: String, body: Data?) {
        self.owner = owner; self.kind = kind; self.originalRecord = originalRecord
        self.path = path; self.operation = operation; self.body = body
    }
}
public enum AccountCleanupReadResult: Sendable { case notObserved, prepared(AccountCleanupPreparation), progress(AccountCleanupProgress) }

@MainActor public final class AccountCleanupClient {
    private struct Ordinary {
        let session: SessionLifecycle
        let operation: SessionOperation
        let credentials: @MainActor () async throws -> String?
        /// Must quiesce all business writers. SDK clearing is performed by the
        /// host after this original confirmation exits (including UNKNOWN).
        let beforeConfirmation: @MainActor (String) throws -> Void
    }
    private let owner = UUID()
    private let lifetime: AccountCleanupLifetime
    private let journal: AccountCleanupJournal
    private let endpoint: MessageEndpoint
    private let ordinary: Ordinary?
    private let transportFactory: @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    private var active = true
    private var inFlight = false

    /// Explicit local simulator factory only. The host supplies the actual verified
    /// SDK operation and a DIFFERENT secure slot from the ordinary SDK persistence.
    public init(development endpoint: MessageEndpoint, lifetime: AccountCleanupLifetime,
        securePersistence: any SessionPersistence, session: SessionLifecycle, sessionOperation: SessionOperation,
        credentials: @escaping @MainActor () async throws -> String?,
        beforeConfirmation: @escaping @MainActor (String) throws -> Void,
        requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        #if DEBUG && targetEnvironment(simulator)
        try Self.validateDevelopmentConfiguration(endpoint, requestTimeout: requestTimeout, resourceTimeout: resourceTimeout)
        self.endpoint = endpoint; self.lifetime = lifetime
        journal = try AccountCleanupJournal(persistence: securePersistence, scope: lifetime.scope)
        ordinary = Ordinary(session: session, operation: sessionOperation, credentials: credentials, beforeConfirmation: beforeConfirmation)
        transportFactory = { try NoRedirectTransport.developmentAccountCleanup(endpoint: endpoint,
            requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: $0) }
        try checkLifetime(ordinary: true)
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }
    /// Restores only a real persisted original operation and its restricted token.
    /// It never acquires ordinary SDK credentials or permits a write.
    public init(developmentRestrictedProgress endpoint: MessageEndpoint, lifetime: AccountCleanupLifetime,
        securePersistence: any SessionPersistence, requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        #if DEBUG && targetEnvironment(simulator)
        try Self.validateDevelopmentConfiguration(endpoint, requestTimeout: requestTimeout, resourceTimeout: resourceTimeout)
        self.endpoint = endpoint; self.lifetime = lifetime; ordinary = nil
        journal = try AccountCleanupJournal(persistence: securePersistence, scope: lifetime.scope)
        _ = try journal.record.original()
        transportFactory = { try NoRedirectTransport.developmentAccountCleanup(endpoint: endpoint,
            requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: $0) }
        try checkLifetime(ordinary: false)
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }
    /// Non-network component seam, unavailable to App callers.
    init(endpoint: MessageEndpoint, lifetime: AccountCleanupLifetime, securePersistence: any SessionPersistence,
        session: SessionLifecycle? = nil, sessionOperation: SessionOperation? = nil,
        credentials: (@MainActor () async throws -> String?)? = nil,
        beforeConfirmation: @escaping @MainActor (String) throws -> Void = { _ in },
        interceptedTransport: any ClientTransport) throws {
        self.endpoint = endpoint; self.lifetime = lifetime
        journal = try AccountCleanupJournal(persistence: securePersistence, scope: lifetime.scope)
        if let session, let sessionOperation, let credentials {
            ordinary = Ordinary(session: session, operation: sessionOperation, credentials: credentials, beforeConfirmation: beforeConfirmation)
        } else {
            guard session == nil, sessionOperation == nil, credentials == nil else { throw CleanupFailure.unavailable }
            ordinary = nil
            _ = try journal.record.original()
        }
        transportFactory = { _ in interceptedTransport }
        try checkLifetime(ordinary: ordinary != nil)
    }
    private static func validateDevelopmentConfiguration(_ endpoint: MessageEndpoint, requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        guard endpoint.url.scheme == "http", endpoint.url.host == "127.0.0.1", let port = endpoint.url.port,
              (1...65535).contains(port), endpoint.maximumRequestBytes <= 16384, endpoint.maximumResponseBytes <= 65536,
              requestTimeout > 0, requestTimeout.isFinite, resourceTimeout > 0, resourceTimeout.isFinite else { throw CleanupFailure.unavailable }
    }
    public func invalidate() { active = false }
    private func checkLifetime(ordinary required: Bool) throws {
        guard active, lifetime.active else { throw CleanupFailure.stale }
        if required {
            guard let ordinary, ordinary.session.isCurrent(ordinary.operation) else { throw CleanupFailure.stale }
        }
        try Task.checkCancellation()
    }
    private func check(_ expected: Data?, ordinary required: Bool) throws {
        try checkLifetime(ordinary: required)
        try journal.requireOriginal(expected)
        try checkLifetime(ordinary: required)
    }
    public var state: AccountCleanupClientState {
        do {
            try check(journal.bytes, ordinary: false)
            let record = journal.record
            if let progress = try record.currentProgress(), !record.confirmationDispatched || record.confirmationResponse != nil || progress.businessRevoked { return .progress(progress) }
            if record.prepared != nil {
                let original = try record.original()
                if record.confirmationDispatched { return .confirmationUnknown(original) }
                if record.confirmation != nil { return .confirmationStaged(original) }
                return .awaitingConfirmation(original)
            }
            if record.preparation != nil { return .preparationUnknown }
            if record.registered != nil { return .registered }
            if record.registration != nil { return .registrationUnknown }
            return .ready
        } catch { return .unavailable }
    }
    /// A durable possible confirmation requires the host to keep ordinary
    /// business access quiesced; only a checked pre-commit blocked ACK releases it.
    public var requiresRestrictedProgress: Bool {
        get throws {
            try check(journal.bytes, ordinary: false)
            guard journal.record.confirmationDispatched else { return false }
            if let bytes = journal.record.confirmationResponse {
                return try AccountCleanupProgress(accountCleanupDocument(bytes), originalOperationID: journal.record.original().operationID).businessRevoked
            }
            return true
        }
    }
    /// Historical original confirmation response is separate from later GET state.
    public var historicalConfirmation: AccountCleanupProgress? {
        get throws {
            try check(journal.bytes, ordinary: false)
            guard let bytes = journal.record.confirmationResponse else { return nil }
            return try AccountCleanupProgress(accountCleanupDocument(bytes), originalOperationID: journal.record.original().operationID)
        }
    }
    private func save(_ record: AccountCleanupRecord, ordinary required: Bool) throws {
        try journal.save(record) { try self.checkLifetime(ordinary: required) }
        try check(journal.bytes, ordinary: required)
    }
    private func encode(_ fields: [String: String]) throws -> Data {
        let bytes = try JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys, .withoutEscapingSlashes])
        guard bytes.count <= 16384 else { throw CleanupFailure.unavailable }
        return bytes
    }
    private func work(_ kind: AccountCleanupWorkKind, path: String, operation: String, body: Data?) throws -> AccountCleanupWork {
        guard let bytes = journal.bytes else { throw CleanupFailure.unavailable }
        return AccountCleanupWork(owner: owner, kind: kind, originalRecord: bytes, path: path, operation: operation, body: body)
    }
    public func prepareDeviceRegistration(stateRef: String) throws -> AccountCleanupWork {
        guard !inFlight else { throw CleanupFailure.stale }; inFlight = true; defer { inFlight = false }
        try check(journal.bytes, ordinary: true)
        _ = try accountCleanupDigest(.string(stateRef))
        guard journal.record.registration == nil else { throw CleanupFailure.unavailable }
        var record = journal.record
        record.registration = try encode(["version":"CLEANUP-DEVICE@1", "action_id":UUID().uuidString,
            "device_id":UUID().uuidString, "state_ref":stateRef])
        try save(record, ordinary: true)
        return try work(.registration, path: "/v1/cleanup-devices", operation: "registerCleanupDeviceV1", body: record.registration)
    }
    public func prepareAccountDeletion() throws -> AccountCleanupWork {
        guard !inFlight else { throw CleanupFailure.stale }; inFlight = true; defer { inFlight = false }
        try check(journal.bytes, ordinary: true)
        guard journal.record.preparation == nil else { throw CleanupFailure.unavailable }
        var record = journal.record
        record.preparation = try encode(["version":"CLEANUP-API@1", "action_id":UUID().uuidString, "binding_id":record.device().bindingID])
        try save(record, ordinary: true)
        return try work(.preparation, path: "/v1/account-cleanup-operations", operation: "prepareAccountCleanupV1", body: record.preparation)
    }
    public func prepareConfirmation(operationID: String, registryDigest: String, confirmation: String) throws -> AccountCleanupWork {
        guard !inFlight else { throw CleanupFailure.stale }; inFlight = true; defer { inFlight = false }
        try check(journal.bytes, ordinary: true)
        let original = try journal.record.original()
        guard original.phase == "prepared", original.operationID == operationID, original.registryDigest == registryDigest,
              confirmation == "DELETE_ACCOUNT", journal.record.confirmation == nil,
              try journal.record.currentProgress()?.businessRevoked != true else { throw CleanupFailure.unavailable }
        var record = journal.record
        record.confirmation = try encode(["version":"CLEANUP-API@1", "registry_digest":registryDigest, "confirmation":confirmation])
        try save(record, ordinary: true)
        return try work(.confirmation, path: try path(original.operationID) + "/confirmation", operation: "confirmAccountCleanupV1", body: record.confirmation)
    }
    /// Explicit resume is available only while the durable marker proves that
    /// this original confirmation has never entered the HTTP exit. UNKNOWN does not qualify.
    public func prepareStagedConfirmation(operationID: String, registryDigest: String, confirmation: String) throws -> AccountCleanupWork {
        guard !inFlight else { throw CleanupFailure.stale }
        try check(journal.bytes, ordinary: true)
        let original = try journal.record.original()
        guard !journal.record.confirmationDispatched, let body = journal.record.confirmation,
              original.operationID == operationID, original.registryDigest == registryDigest,
              confirmation == "DELETE_ACCOUNT" else { throw CleanupFailure.unavailable }
        return try work(.confirmation, path: path(original.operationID) + "/confirmation", operation: "confirmAccountCleanupV1", body: body)
    }
    public func prepareOriginalRead() throws -> AccountCleanupWork {
        guard !inFlight else { throw CleanupFailure.stale }
        try check(journal.bytes, ordinary: false)
        if journal.record.prepared != nil {
            return try work(.progress, path: path(journal.record.original().operationID), operation: "readOriginalAccountCleanupV1", body: nil)
        }
        try check(journal.bytes, ordinary: true)
        // Registration has no read-by-original-action route in DEVICE@1. UNKNOWN
        // therefore stays UNKNOWN; never silently repeat its POST or mint a new ID.
        let actionID = try journal.record.preparationActionID()
        var parts = URLComponents(); parts.path = "/v1/account-cleanup-preparations"
        parts.queryItems = [.init(name: "action_id", value: actionID)]
        guard let target = parts.string else { throw CleanupFailure.unavailable }
        return try work(.preparationQuery, path: target, operation: "queryAccountCleanupPreparationV1", body: nil)
    }
    private func path(_ operationID: String) throws -> String {
        guard cleanupIdentifier(operationID, maximum: 160), let segment = operationID.addingPercentEncoding(
            withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/%?#"))) else { throw CleanupFailure.invalidResponse }
        return "/v1/account-cleanup-operations/" + segment
    }
    public func perform(_ work: AccountCleanupWork) async throws {
        try checkLifetime(ordinary: true)
        guard work.owner == owner, !work.consumed, !inFlight,
              [.registration, .preparation, .confirmation].contains(work.kind), let ordinary, let body = work.body else { throw CleanupFailure.stale }
        inFlight = true; work.consumed = true; defer { inFlight = false }
        try check(work.originalRecord, ordinary: true)
        let bearer = try await ordinaryBearer(expected: work.originalRecord)
        if work.kind == .confirmation {
            do { try ordinary.beforeConfirmation(journal.record.original().operationID) }
            catch {
                try check(work.originalRecord, ordinary: true)
                if let safe = error as? CleanupFailure { throw safe }
                throw CleanupFailure.unavailable
            }
            try check(work.originalRecord, ordinary: true)
            var record = journal.record; record.confirmationDispatched = true
            try save(record, ordinary: true)
        }
        let expected = journal.bytes
        try check(expected, ordinary: true)
        let bytes = try await exchange(work, authorization: "Bearer " + bearer, expected: expected, ordinary: true)
        var next = journal.record
        switch work.kind {
        case .registration:
            let fields = try next.registrationFields()
            _ = try AccountCleanupDeviceBinding(accountCleanupDocument(bytes), deviceID: fields.deviceID, stateRef: fields.stateRef)
            next.registered = bytes
        case .preparation:
            _ = try AccountCleanupPreparation(accountCleanupDocument(bytes), expectedBindingID: next.device().bindingID, fromQuery: false)
            next.prepared = bytes; next.preparedFromQuery = false
        case .confirmation:
            _ = try AccountCleanupProgress(accountCleanupDocument(bytes), originalOperationID: next.original().operationID)
            next.confirmationResponse = bytes
        default: throw CleanupFailure.stale
        }
        try save(next, ordinary: true)
    }
    public func read(_ work: AccountCleanupWork) async throws -> AccountCleanupReadResult {
        try checkLifetime(ordinary: work.kind != .progress)
        guard work.owner == owner, !work.consumed, !inFlight,
              [.preparationQuery, .progress].contains(work.kind), work.body == nil else { throw CleanupFailure.stale }
        inFlight = true; work.consumed = true; defer { inFlight = false }
        let needsOrdinary = work.kind == .preparationQuery
        try check(work.originalRecord, ordinary: needsOrdinary)
        let authorization: String
        if needsOrdinary {
            authorization = try await "Bearer " + ordinaryBearer(expected: work.originalRecord)
        } else { authorization = try "Cleanup " + journal.record.original().progressToken }
        let bytes = try await exchange(work, authorization: authorization, expected: work.originalRecord, ordinary: needsOrdinary)
        var next = journal.record
        if needsOrdinary {
            let fields = try accountCleanupObject(accountCleanupDocument(bytes), fields: ["version", "request_id", "preparation"])
            guard try accountCleanupString(fields["version"]) == "CLEANUP-API@1", let original = fields["preparation"] else { throw CleanupFailure.invalidResponse }
            if case .null = original { return .notObserved }
            let prepared = try AccountCleanupPreparation(original, expectedBindingID: next.device().bindingID, fromQuery: true)
            next.prepared = bytes; next.preparedFromQuery = true
            try save(next, ordinary: true)
            return .prepared(prepared)
        }
        let progress = try AccountCleanupProgress(accountCleanupDocument(bytes), originalOperationID: next.original().operationID)
        if let previous = try next.currentProgress() {
            guard !previous.businessRevoked || progress.businessRevoked else { throw CleanupFailure.invalidResponse }
            if let before = previous.revision, let after = progress.revision, after < before { throw CleanupFailure.invalidResponse }
        }
        next.progress = bytes
        try save(next, ordinary: false)
        return .progress(progress)
    }
    private func ordinaryBearer(expected: Data?) async throws -> String {
        guard let ordinary else { throw CleanupFailure.unavailable }
        let bearer: String?
        do { bearer = try await ordinary.credentials() }
        catch { try check(expected, ordinary: true); throw CleanupFailure.unavailable }
        try check(expected, ordinary: true)
        guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw CleanupFailure.unavailable }
        return bearer
    }
    private func exchange(_ work: AccountCleanupWork, authorization: String, expected: Data?, ordinary required: Bool) async throws -> Data {
        do { return try await sendOriginal(work, authorization: authorization, expected: expected, ordinary: required) }
        catch {
            try check(expected, ordinary: required)
            if let safe = error as? CleanupFailure { throw safe }
            if error is CancellationError { throw CancellationError() }
            if error is DecodingError { throw CleanupFailure.invalidResponse }
            // Never let a transport error carrying request headers/body escape.
            throw CleanupFailure.exchangeUnknown
        }
    }
    private func sendOriginal(_ work: AccountCleanupWork, authorization: String, expected: Data?, ordinary required: Bool) async throws -> Data {
        let validate: @MainActor @Sendable () throws -> Void = { [self] in try check(expected, ordinary: required) }
        try validate()
        var request = HTTPRequest(method: work.body == nil ? .get : .post, scheme: nil, authority: nil, path: work.path)
        request.headerFields[.authorization] = authorization; request.headerFields[.cacheControl] = "no-store"
        if work.body != nil { request.headerFields[.contentType] = "application/octet-stream" }
        let transport = try transportFactory(validate)
        try validate()
        let (response, body) = try await transport.send(request, body: work.body.map(HTTPBody.init), baseURL: endpoint.url, operationID: work.operation)
        try validate()
        guard !(300..<400).contains(response.status.code), let body else { throw CleanupFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: min(65536, endpoint.maximumResponseBytes))
        try validate()
        let media = response.headerFields.filter { $0.name == .contentType }
        let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let cache = response.headerFields.filter { $0.name == .cacheControl }
        guard media.count == 1, ["application/json", "application/json; charset=utf-8"].contains(media.first?.value.lowercased()),
              cache.count == 1, cache.first?.value.lowercased() == "no-store", traces.count == 1,
              let trace = traces.first?.value, UUID(uuidString: trace) != nil else { throw CleanupFailure.invalidResponse }
        let fields = try accountCleanupObject(accountCleanupDocument(bytes))
        guard try accountCleanupString(fields["request_id"]) == trace else { throw CleanupFailure.invalidResponse }
        guard response.status.code == 200 else {
            _ = try JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: bytes)
            throw response.status.code == 503 ? CleanupFailure.exchangeUnknown : CleanupFailure.rejected(response.status.code)
        }
        try validate()
        return bytes
    }
}
