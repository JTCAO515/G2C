import Foundation
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

/// Implemented by the actual App root with captured store/key descriptors. No
/// response path/ID becomes a filesystem selector. Reconcile must inspect only
/// this original durable execution, never rerun an unknown erase.
@MainActor public protocol DeviceCleanupNativeExecuting: AnyObject {
    var scope: AccountCleanupScope { get }
    var stateRef: String { get }
    func executeOriginal(_ invocation: DeviceCleanupInvocation, intentID: UUID) throws -> DeviceCleanupNativeOutcome
    func reconcileOriginal(_ invocation: DeviceCleanupInvocation, intentID: UUID) throws -> DeviceCleanupNativeOutcome
}
public struct DeviceCleanupAccountAuthorization: Sendable {
    public let operationID: String
    let version: CleanupDeviceVersion
    let scope: AccountCleanupScope
    let bindingID: String
    let stateRef: String
    init(operationID: String, scope: AccountCleanupScope, bindingID: String, stateRef: String, version: CleanupDeviceVersion = .v3) {
        self.operationID = operationID; self.scope = scope; self.bindingID = bindingID; self.stateRef = stateRef
        self.version = version
    }
}
public enum DeviceCleanupClientState: Sendable {
    case ready, registrationUnknown, enrolled(DeviceCleanupEnrollment), callUnknown
    case invocation(DeviceCleanupInvocation, local: DeviceCleanupNativeOutcome?), unavailable
}
public enum DeviceCleanupReadResult: Sendable {
    case notObserved, enrolled(DeviceCleanupEnrollment), invocation(DeviceCleanupInvocation), identityAllowed, identityRefused
    case completion(DeviceCleanupCompletion)
}
fileprivate enum DeviceCleanupWorkKind: Equatable { case registration, registrationQuery, identity, call, actionQuery, invocationQuery, receipt, completion }
@MainActor public final class DeviceCleanupWork {
    fileprivate let owner: UUID
    fileprivate let kind: DeviceCleanupWorkKind
    fileprivate let record: Data
    fileprivate let path: String
    fileprivate let operation: String
    fileprivate let body: Data?
    fileprivate var used = false
    fileprivate init(owner: UUID, kind: DeviceCleanupWorkKind, record: Data, path: String, operation: String, body: Data?) {
        self.owner = owner; self.kind = kind; self.record = record; self.path = path; self.operation = operation; self.body = body
    }
}

@MainActor public final class DeviceCleanupClient {
    private struct Ordinary {
        let session: SessionLifecycle
        let operation: SessionOperation
        let credentials: @MainActor () async throws -> String?
    }
    private let owner = UUID()
    private let lifetime: AccountCleanupLifetime
    private let journal: DeviceCleanupJournal
    private let endpoint: MessageEndpoint
    private let ordinary: Ordinary?
    private let transportFactory: @MainActor (DeviceCleanupWorkKind, @escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    private var active = true
    private var busy = false
    public var capturedScope: AccountCleanupScope { journal.record.scope }
    public var version: CleanupDeviceVersion { journal.record.wire }

    public init(development endpoint: MessageEndpoint, lifetime: AccountCleanupLifetime, securePersistence: any SessionPersistence,
        session: SessionLifecycle, sessionOperation: SessionOperation, credentials: @escaping @MainActor () async throws -> String?,
        requestTimeout: TimeInterval, resourceTimeout: TimeInterval, version: CleanupDeviceVersion = .v3) throws {
        #if DEBUG && (targetEnvironment(simulator) || (os(iOS) && G2C_M4_DEVICE_ACCEPTANCE))
        try Self.configuration(endpoint, requestTimeout, resourceTimeout)
        self.endpoint = endpoint; self.lifetime = lifetime
        journal = try DeviceCleanupJournal(persistence: securePersistence, scope: lifetime.scope, newVersion: version)
        ordinary = Ordinary(session: session, operation: sessionOperation, credentials: credentials)
        let wire = journal.record.wire
        transportFactory = { kind, validate in
            if kind == .completion { return try NoRedirectTransport.developmentDeviceCompletion(endpoint: endpoint, requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: validate, version: wire) }
            return try NoRedirectTransport.developmentDeviceCleanup(endpoint: endpoint, requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: validate, version: wire)
        }
        try checkLifetime(ordinary: true)
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }
    public init(developmentOriginalDevice endpoint: MessageEndpoint, lifetime: AccountCleanupLifetime, securePersistence: any SessionPersistence,
        requestTimeout: TimeInterval, resourceTimeout: TimeInterval) throws {
        #if DEBUG && (targetEnvironment(simulator) || (os(iOS) && G2C_M4_DEVICE_ACCEPTANCE))
        try Self.configuration(endpoint, requestTimeout, resourceTimeout)
        self.endpoint = endpoint; self.lifetime = lifetime; ordinary = nil
        journal = try DeviceCleanupJournal(persistence: securePersistence, scope: lifetime.scope)
        _ = try journal.record.enrollment()
        let wire = journal.record.wire
        transportFactory = { kind, validate in
            if kind == .completion { return try NoRedirectTransport.developmentDeviceCompletion(endpoint: endpoint, requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: validate, version: wire) }
            return try NoRedirectTransport.developmentDeviceCleanup(endpoint: endpoint, requestTimeout: requestTimeout, resourceTimeout: resourceTimeout, validate: validate, version: wire)
        }
        try checkLifetime(ordinary: false)
        #else
        throw MessageHTTPFailure.productionActivationUnavailable
        #endif
    }
    init(endpoint: MessageEndpoint, lifetime: AccountCleanupLifetime, securePersistence: any SessionPersistence,
        session: SessionLifecycle? = nil, sessionOperation: SessionOperation? = nil, credentials: (@MainActor () async throws -> String?)? = nil,
        interceptedTransport: any ClientTransport, version: CleanupDeviceVersion = .v3) throws {
        self.endpoint = endpoint; self.lifetime = lifetime
        journal = try DeviceCleanupJournal(persistence: securePersistence, scope: lifetime.scope, newVersion: version)
        if let session, let sessionOperation, let credentials {
            ordinary = Ordinary(session: session, operation: sessionOperation, credentials: credentials)
        } else {
            guard session == nil, sessionOperation == nil, credentials == nil else { throw CleanupFailure.unavailable }
            ordinary = nil; _ = try journal.record.enrollment()
        }
        transportFactory = { _, _ in interceptedTransport }
        try checkLifetime(ordinary: ordinary != nil)
    }
    private static func configuration(_ endpoint: MessageEndpoint, _ request: TimeInterval, _ resource: TimeInterval) throws {
        guard endpoint.allowsDevelopmentActivation,
              endpoint.maximumRequestBytes <= 16384, endpoint.maximumResponseBytes <= 65536,
              request > 0, request.isFinite, resource > 0, resource.isFinite else { throw CleanupFailure.unavailable }
    }
    public func invalidate() { active = false }
    private func checkLifetime(ordinary required: Bool) throws {
        guard active, lifetime.active else { throw CleanupFailure.stale }
        if required { guard let ordinary, ordinary.session.isCurrent(ordinary.operation) else { throw CleanupFailure.stale } }
        try Task.checkCancellation()
    }
    private func check(_ expected: Data?, ordinary required: Bool) throws {
        try checkLifetime(ordinary: required); try journal.requireOriginal(expected); try checkLifetime(ordinary: required)
    }
    private func save(_ record: DeviceCleanupRecord, ordinary required: Bool = false) throws {
        try journal.save(record) { try self.checkLifetime(ordinary: required) }
        try check(journal.bytes, ordinary: required)
    }
    public var state: DeviceCleanupClientState {
        do {
            try check(journal.bytes, ordinary: false)
            let record = journal.record
            if record.invocationReply != nil { return .invocation(try record.invocation(), local: record.nativeOutcome) }
            if record.action != nil { return .callUnknown }
            if record.enrollmentReply != nil { return .enrolled(try record.enrollment()) }
            return record.registration == nil ? .ready : .registrationUnknown
        } catch { return .unavailable }
    }
    public func acceptedEnrollment() throws -> DeviceCleanupEnrollment {
        try check(journal.bytes, ordinary: false); return try journal.record.enrollment()
    }
    private func encode(_ fields: [String: String]) throws -> Data {
        let data = try JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys, .withoutEscapingSlashes])
        guard data.count <= 16384 else { throw CleanupFailure.unavailable }; return data
    }
    private func work(_ kind: DeviceCleanupWorkKind, _ path: String, _ operation: String, _ body: Data? = nil) throws -> DeviceCleanupWork {
        guard let bytes = journal.bytes else { throw CleanupFailure.unavailable }
        return .init(owner: owner, kind: kind, record: bytes, path: path, operation: operation, body: body)
    }
    private func query(_ path: String, action: String, hash: String) throws -> String {
        var parts = URLComponents(); parts.path = path
        parts.queryItems = [.init(name: "action_id", value: action), .init(name: "input_sha256", value: hash)]
        guard let value = parts.string else { throw CleanupFailure.unavailable }; return value
    }
    public func prepareRegistration(stateRef: String) throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; busy = true; defer { busy = false }
        try check(journal.bytes, ordinary: true)
        guard journal.record.registration == nil else { throw CleanupFailure.unavailable }
        _ = try accountCleanupDigest(.string(stateRef))
        var next = journal.record
        next.registration = try encode(["version":journal.record.wire.rawValue, "action_id":UUID().uuidString, "device_id":UUID().uuidString, "state_ref":stateRef])
        try save(next, ordinary: true)
        return try work(.registration, "/" + journal.record.wire.route + "/cleanup-devices", "registerCleanupDevice" + journal.record.wire.operationSuffix, next.registration)
    }
    public func prepareRegistrationQuery() throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; try check(journal.bytes, ordinary: true)
        guard let raw = journal.record.registration else { throw CleanupFailure.unavailable }
        let fields = try accountCleanupObject(accountCleanupDocument(raw))
        return try work(.registrationQuery, query("/" + journal.record.wire.route + "/cleanup-device-registrations", action: accountCleanupID(fields["action_id"]), hash: deviceCleanupSHA(raw)), "queryCleanupDeviceRegistration" + journal.record.wire.operationSuffix)
    }
    public func prepareIdentityVerification() throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; try check(journal.bytes, ordinary: true)
        _ = try journal.record.enrollment()
        return try work(.identity, "/v1/message-receipts?message_id=cleanup-check-" + UUID().uuidString, "verifyDeviceCleanupIdentity" + journal.record.wire.operationSuffix)
    }
    public var hasVerifiedIdentityRefusal: Bool {
        get throws {
            try check(journal.bytes, ordinary: false)
            return journal.record.refusalStatus != nil && journal.record.refusalResponse != nil
        }
    }
    public func prepareSessionInvalidation() throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; busy = true; defer { busy = false }
        try check(journal.bytes, ordinary: false)
        guard let status = journal.record.refusalStatus, [401,403].contains(status), journal.record.refusalResponse != nil else { throw CleanupFailure.unavailable }
        return try stageCall(expectedAccount: nil)
    }
    public func prepareAccountCleanup(_ authorization: DeviceCleanupAccountAuthorization) throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; busy = true; defer { busy = false }
        try check(journal.bytes, ordinary: false)
        let enrollment = try journal.record.enrollment()
        guard authorization.scope == journal.record.scope, authorization.version == enrollment.version, authorization.bindingID == enrollment.bindingID,
              authorization.stateRef == enrollment.stateRef else { throw CleanupFailure.stale }
        return try stageCall(expectedAccount: authorization.operationID)
    }
    private func stageCall(expectedAccount: String?) throws -> DeviceCleanupWork {
        guard journal.record.action == nil else { throw CleanupFailure.unavailable }
        var record = journal.record; record.expectedAccountOperationID = expectedAccount
        record.action = try encode(["version":journal.record.wire.rawValue, "action_id":UUID().uuidString,
            "binding_id":record.enrollment().bindingID, "reason":"session_invalid"])
        try save(record)
        return try work(.call, "/" + journal.record.wire.route + "/cleanup-device-calls", "createCleanupDeviceCall" + journal.record.wire.operationSuffix, record.action)
    }
    public func prepareOriginalCallQuery() throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; try check(journal.bytes, ordinary: false)
        let action = try journal.record.originalAction()
        return try work(.actionQuery, query("/" + journal.record.wire.route + "/cleanup-device-call-actions", action: action.id, hash: action.hash), "queryCleanupDeviceCallAction" + journal.record.wire.operationSuffix)
    }
    public func prepareOriginalInvocationQuery() throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; try check(journal.bytes, ordinary: false)
        let invocation = try journal.record.invocation()
        guard let encoded = invocation.invocationID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/%?#"))) else { throw CleanupFailure.invalidResponse }
        return try work(.invocationQuery, "/" + journal.record.wire.route + "/cleanup-device-calls/" + encoded, "queryCleanupDeviceInvocation" + journal.record.wire.operationSuffix)
    }
    public func prepareCompletionQuery() throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; try check(journal.bytes, ordinary: false)
        let invocation = try journal.record.invocation()
        guard let encoded = invocation.invocationID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/%?#"))) else { throw CleanupFailure.invalidResponse }
        var parts = URLComponents(); parts.percentEncodedPath = "/" + journal.record.wire.completionRoute + "/cleanup-device-completions/" + encoded
        parts.queryItems = [.init(name: "request_digest", value: invocation.requestDigest)]
        guard let path = parts.string else { throw CleanupFailure.invalidResponse }
        return try work(.completion, path, journal.record.wire.completionOperation)
    }
    /// Intent is durable before the executor receives a call. An existing intent
    /// always enters reconcileOriginal, even when its previous result was unknown.
    public func executeNative(using executor: any DeviceCleanupNativeExecuting) throws -> DeviceCleanupNativeOutcome {
        guard !busy else { throw CleanupFailure.stale }; busy = true; defer { busy = false }
        try check(journal.bytes, ordinary: false)
        let invocation = try journal.record.invocation(), enrollment = try journal.record.enrollment()
        guard executor.scope == journal.record.scope, executor.stateRef == enrollment.stateRef else { throw CleanupFailure.stale }
        var next = journal.record
        let outcome: DeviceCleanupNativeOutcome
        if let intent = next.nativeIntentID {
            do { outcome = try executor.reconcileOriginal(invocation, intentID: intent) }
            catch { try check(journal.bytes, ordinary: false); next = journal.record; next.nativeOutcome = .unknown; try save(next); throw CleanupFailure.exchangeUnknown }
        } else {
            guard invocation.state == .pending else { throw CleanupFailure.unavailable }
            let intent = UUID(); next.nativeIntentID = intent
            try save(next)
            do { outcome = try executor.executeOriginal(invocation, intentID: intent) }
            catch { try check(journal.bytes, ordinary: false); next = journal.record; next.nativeOutcome = .unknown; try save(next); throw CleanupFailure.exchangeUnknown }
        }
        try check(journal.bytes, ordinary: false)
        next = journal.record; next.nativeOutcome = outcome; try save(next)
        return outcome
    }
    /// Whether a new original receipt may be staged. An existing unacknowledged
    /// receipt never grants another POST, including after process reconstruction.
    public var canPrepareReceipt: Bool { get throws { try receiptOutcome() != nil } }
    private func receiptOutcome() throws -> DeviceCleanupNativeOutcome? {
        try check(journal.bytes, ordinary: false)
        guard let outcome = journal.record.nativeOutcome, journal.record.nativeIntentID != nil else { return nil }
        if let previous = journal.record.receipts.last {
            let fields = try accountCleanupObject(accountCleanupDocument(previous.originalUTF8))
            let old = try accountCleanupString(fields["outcome"])
            guard previous.acknowledged, old == "unknown", outcome != .unknown else { return nil }
        }
        return outcome
    }
    public func prepareReceipt() throws -> DeviceCleanupWork {
        guard !busy else { throw CleanupFailure.stale }; busy = true; defer { busy = false }
        try check(journal.bytes, ordinary: false)
        let invocation = try journal.record.invocation()
        guard let outcome = try receiptOutcome() else { throw CleanupFailure.unavailable }
        var next = journal.record
        let raw = try encode(["version":journal.record.wire.rawValue, "action_id":UUID().uuidString, "operation_id":invocation.operationID,
            "invocation_id":invocation.invocationID, "binding_id":invocation.bindingID, "request_digest":invocation.requestDigest, "outcome":outcome.rawValue])
        next.receipts.append(.init(originalUTF8: raw, acknowledged: false)); try save(next)
        return try work(.receipt, "/" + journal.record.wire.route + "/cleanup-device-receipts", "reportCleanupDeviceReceipt" + journal.record.wire.operationSuffix, raw)
    }
    public func perform(_ work: DeviceCleanupWork) async throws -> DeviceCleanupReadResult {
        let needsOrdinary = [.registration, .registrationQuery, .identity].contains(work.kind)
        try checkLifetime(ordinary: needsOrdinary)
        guard work.owner == owner, !work.used, !busy else { throw CleanupFailure.stale }
        work.used = true; busy = true; defer { busy = false }
        try check(work.record, ordinary: needsOrdinary)
        let authorization: String
        if needsOrdinary {
            guard let ordinary else { throw CleanupFailure.unavailable }
            let bearer: String?
            do { bearer = try await ordinary.credentials() } catch { try check(work.record, ordinary: true); throw CleanupFailure.unavailable }
            try check(work.record, ordinary: true)
            guard let bearer, !bearer.isEmpty, bearer.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw CleanupFailure.unavailable }
            authorization = "Bearer " + bearer
        } else if work.kind == .receipt { authorization = try "Cleanup " + journal.record.invocation().receiptCredential }
        else { authorization = try "Device " + journal.record.enrollment().deviceCredential }
        let (status, raw) = try await exchange(work, authorization: authorization, ordinary: needsOrdinary)
        var next = journal.record
        let root = try accountCleanupObject(accountCleanupDocument(raw))
        if work.kind == .identity {
            if status == 200 {
                _ = try JSONDecoder().decode(Components.Schemas.MessageReceiptQueryResponse.self, from: raw)
                return .identityAllowed // Does not renew any offline read policy.
            }
            guard [401,403].contains(status) else { throw CleanupFailure.exchangeUnknown }
            _ = try JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: raw)
            next.refusalStatus = status; next.refusalResponse = raw; try save(next, ordinary: true)
            return .identityRefused
        }
        guard status == 200 else {
            _ = try JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: raw)
            throw status == 503 ? CleanupFailure.exchangeUnknown : CleanupFailure.rejected(status)
        }
        switch work.kind {
        case .completion:
            let invocation = try next.invocation()
            var acknowledged: String?
            if next.nativeOutcome == .confirmed, next.nativeIntentID != nil, let receipt = next.receipts.last, receipt.acknowledged {
                let fields = try accountCleanupObject(accountCleanupDocument(receipt.originalUTF8))
                if try accountCleanupString(fields["outcome"]) == "confirmed" {
                    let digest = deviceCleanupSHA(receipt.originalUTF8)
                    guard invocation.state == .confirmed, invocation.receiptDigest == digest else { throw CleanupFailure.invalidResponse }
                    acknowledged = digest
                }
            }
            let completion = try DeviceCleanupCompletion(reply: raw, invocation: invocation, scope: next.scope,
                acknowledgedConfirmedReceipt: acknowledged, journalSHA256: deviceCleanupSHA(work.record))
            try check(work.record, ordinary: false)
            return .completion(completion) // GET does not rewrite the original journal.
        case .registration, .registrationQuery:
            if work.kind == .registrationQuery {
                try accountCleanupKeys(root, fields: ["version", "request_id", "action_id", "input_sha256", "registration"])
                guard let original = next.registration else { throw CleanupFailure.stale }
                let fields = try accountCleanupObject(accountCleanupDocument(original))
                guard try accountCleanupString(root["version"]) == journal.record.wire.rawValue,
                      try accountCleanupID(root["action_id"]) == accountCleanupID(fields["action_id"]),
                      try accountCleanupDigest(root["input_sha256"]) == deviceCleanupSHA(original) else { throw CleanupFailure.invalidResponse }
                if case .null = root["registration"] { return .notObserved }
            }
            next.enrollmentReply = raw; next.enrollmentFromQuery = work.kind == .registrationQuery
            try save(next, ordinary: true); return .enrolled(try next.enrollment())
        case .call, .actionQuery:
            try accountCleanupKeys(root, fields: ["version", "request_id", "action_id", "input_sha256", "invocation"])
            let original = try next.originalAction()
            guard try accountCleanupString(root["version"]) == journal.record.wire.rawValue,
                  try accountCleanupID(root["action_id"]) == original.id,
                  try accountCleanupDigest(root["input_sha256"]) == original.hash else { throw CleanupFailure.invalidResponse }
            if case .null = root["invocation"] {
                guard work.kind == .actionQuery else { throw CleanupFailure.invalidResponse }
                return .notObserved
            }
            // A second read may update state, never retarget the original call.
            let priorInvocation = next.invocationReply == nil ? nil : try next.invocation()
            next.invocationReply = raw; next.invocationFromActionQuery = work.kind == .actionQuery
            let observed = try next.invocation()
            if let priorInvocation {
                guard priorInvocation.invocationID == observed.invocationID,
                      priorInvocation.canonicalCallUTF8 == observed.canonicalCallUTF8 else { throw CleanupFailure.invalidResponse }
            }
            try save(next); return .invocation(observed)
        case .invocationQuery, .receipt:
            let original = try next.invocation()
            let observed = try DeviceCleanupInvocation(result: accountCleanupDocument(raw), enrollment: next.enrollment(), directQuery: true, expectedOperationID: original.operationID)
            guard observed.invocationID == original.invocationID, observed.canonicalCallUTF8 == original.canonicalCallUTF8 else { throw CleanupFailure.invalidResponse }
            if let last = next.receipts.last {
                let expected = deviceCleanupSHA(last.originalUTF8)
                if work.kind == .receipt { guard observed.receiptDigest == expected else { throw CleanupFailure.invalidResponse } }
                if observed.receiptDigest == expected { next.receipts[next.receipts.count - 1].acknowledged = true }
            }
            next.directInvocation = raw; try save(next); return .invocation(try next.invocation())
        case .identity: throw CleanupFailure.stale
        }
    }
    private func exchange(_ work: DeviceCleanupWork, authorization: String, ordinary required: Bool) async throws -> (Int, Data) {
        do {
            let validate: @MainActor @Sendable () throws -> Void = { [self] in try check(work.record, ordinary: required) }
            try validate()
            var request = HTTPRequest(method: work.body == nil ? .get : .post, scheme: nil, authority: nil, path: work.path)
            request.headerFields[.authorization] = authorization; request.headerFields[.cacheControl] = "no-store"
            if work.body != nil { request.headerFields[.contentType] = "application/octet-stream" }
            let transport = try transportFactory(work.kind, validate); try validate()
            let (response, body) = try await transport.send(request, body: work.body.map(HTTPBody.init), baseURL: endpoint.url, operationID: work.operation)
            try validate()
            guard !(300..<400).contains(response.status.code), let body else { throw CleanupFailure.invalidResponse }
            let bytes = try await Data(collecting: body, upTo: min(endpoint.maximumResponseBytes, work.kind == .completion ? 4096 : 65536)); try validate()
            let media = response.headerFields.filter { $0.name == .contentType }, cache = response.headerFields.filter { $0.name == .cacheControl }
            let traces = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
            guard media.count == 1, ["application/json", "application/json; charset=utf-8"].contains(media.first?.value.lowercased()),
                  cache.count == 1, cache.first?.value.lowercased() == "no-store", traces.count == 1,
                  let trace = traces.first?.value, UUID(uuidString: trace) != nil else { throw CleanupFailure.invalidResponse }
            let root = try accountCleanupObject(accountCleanupDocument(bytes))
            guard try accountCleanupString(root["request_id"]) == trace else { throw CleanupFailure.invalidResponse }
            try validate(); return (response.status.code, bytes)
        } catch {
            try check(work.record, ordinary: required)
            if let safe = error as? CleanupFailure { throw safe }
            if error is CancellationError { throw CancellationError() }
            if error is DecodingError { throw CleanupFailure.invalidResponse }
            throw CleanupFailure.exchangeUnknown
        }
    }
}
