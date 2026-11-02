import Foundation
import CJSession
import CJStrictJSON

struct DeviceCleanupReceiptAttempt: Codable {
    let originalUTF8: Data
    var acknowledged: Bool
}
struct DeviceCleanupRecord: Codable {
    let version: String
    let scope: AccountCleanupScope
    var registration: Data?
    var enrollmentReply: Data?
    var enrollmentFromQuery: Bool
    var action: Data?
    var invocationReply: Data?
    var invocationFromActionQuery: Bool
    var directInvocation: Data?
    var expectedAccountOperationID: String?
    var nativeIntentID: UUID?
    var nativeOutcome: DeviceCleanupNativeOutcome?
    var receipts: [DeviceCleanupReceiptAttempt]
    init(scope: AccountCleanupScope) {
        version = "DeviceCleanup.Native@1"; self.scope = scope
        enrollmentFromQuery = false; invocationFromActionQuery = false; receipts = []
    }
    func enrollment() throws -> DeviceCleanupEnrollment {
        guard let registration, let enrollmentReply else { throw CleanupFailure.unavailable }
        return try DeviceCleanupEnrollment(originalUTF8: registration, replyUTF8: enrollmentReply, fromQuery: enrollmentFromQuery, scope: scope)
    }
    func originalAction() throws -> (id: String, hash: String, reason: String) {
        guard let action, !action.isEmpty, action.count <= 16384 else { throw CleanupFailure.unavailable }
        let fields = try accountCleanupObject(accountCleanupDocument(action), fields: ["version", "action_id", "binding_id", "reason"])
        guard try accountCleanupString(fields["version"]) == "CLEANUP-DEVICE@3",
              try accountCleanupID(fields["binding_id"]) == enrollment().bindingID else { throw CleanupFailure.invalidResponse }
        let reason = try accountCleanupString(fields["reason"])
        guard ["session_invalid", "offline_expired"].contains(reason) else { throw CleanupFailure.invalidResponse }
        return (try accountCleanupID(fields["action_id"]), deviceCleanupSHA(action), reason)
    }
    func invocation() throws -> DeviceCleanupInvocation {
        let enrollment = try enrollment(), action = try originalAction()
        let original: DeviceCleanupInvocation
        guard let invocationReply else { throw CleanupFailure.unavailable }
        let root = try accountCleanupObject(accountCleanupDocument(invocationReply), fields: ["version", "request_id", "action_id", "input_sha256", "invocation"])
        try deviceCleanupTrace(root)
        guard try accountCleanupString(root["version"]) == "CLEANUP-DEVICE@3",
              try accountCleanupID(root["action_id"]) == action.id,
              try accountCleanupDigest(root["input_sha256"]) == action.hash,
              let payload = root["invocation"] else { throw CleanupFailure.invalidResponse }
        original = try DeviceCleanupInvocation(result: payload, enrollment: enrollment, directQuery: false, expectedOperationID: expectedAccountOperationID)
        guard original.reason == .accountCleanup || original.reason.rawValue == action.reason else { throw CleanupFailure.invalidResponse }
        if let expectedAccountOperationID {
            guard original.operationID == expectedAccountOperationID, original.reason == .accountCleanup else { throw CleanupFailure.invalidResponse }
        }
        guard let directInvocation else { return original }
        let current = try DeviceCleanupInvocation(result: accountCleanupDocument(directInvocation), enrollment: enrollment,
            directQuery: true, expectedOperationID: original.operationID)
        guard current.invocationID == original.invocationID, current.requestDigest == original.requestDigest,
              current.canonicalCallUTF8 == original.canonicalCallUTF8 else { throw CleanupFailure.invalidResponse }
        return current
    }
    func validate(expectedScope: AccountCleanupScope) throws {
        guard version == "DeviceCleanup.Native@1", scope.environment == expectedScope.environment, scope.account == expectedScope.account,
              registration != nil || (enrollmentReply == nil && action == nil && invocationReply == nil && directInvocation == nil && nativeIntentID == nil && nativeOutcome == nil && receipts.isEmpty),
              enrollmentReply != nil || (action == nil && invocationReply == nil && directInvocation == nil && nativeIntentID == nil && nativeOutcome == nil && receipts.isEmpty),
              action != nil || (invocationReply == nil && directInvocation == nil && nativeIntentID == nil && nativeOutcome == nil && receipts.isEmpty),
              invocationReply != nil || (directInvocation == nil && nativeIntentID == nil && nativeOutcome == nil && receipts.isEmpty),
              nativeIntentID != nil || (nativeOutcome == nil && receipts.isEmpty),
              nativeOutcome != nil || receipts.isEmpty,
              receipts.count <= 32 else { throw CleanupFailure.invalidResponse }
        if let registration {
            guard !registration.isEmpty, registration.count <= 16384 else { throw CleanupFailure.invalidResponse }
            let fields = try accountCleanupObject(accountCleanupDocument(registration), fields: ["version", "action_id", "device_id", "state_ref"])
            guard try accountCleanupString(fields["version"]) == "CLEANUP-DEVICE@3" else { throw CleanupFailure.invalidResponse }
            _ = try accountCleanupID(fields["action_id"]); _ = try accountCleanupID(fields["device_id"]); _ = try accountCleanupDigest(fields["state_ref"])
        }
        if enrollmentReply != nil { _ = try enrollment() }
        if action != nil { _ = try originalAction() }
        if let expectedAccountOperationID { _ = try accountCleanupID(.string(expectedAccountOperationID)) }
        if invocationReply != nil {
            let invocation = try invocation()
            for receipt in receipts {
                guard !receipt.originalUTF8.isEmpty, receipt.originalUTF8.count <= 16384 else { throw CleanupFailure.invalidResponse }
                let fields = try accountCleanupObject(accountCleanupDocument(receipt.originalUTF8), fields: ["version", "action_id", "operation_id", "invocation_id", "binding_id", "request_digest", "outcome"])
                guard try accountCleanupString(fields["version"]) == "CLEANUP-DEVICE@3",
                      try accountCleanupID(fields["operation_id"]) == invocation.operationID,
                      try accountCleanupID(fields["invocation_id"]) == invocation.invocationID,
                      try accountCleanupID(fields["binding_id"]) == invocation.bindingID,
                      try accountCleanupDigest(fields["request_digest"]) == invocation.requestDigest,
                      DeviceCleanupNativeOutcome(rawValue: try accountCleanupString(fields["outcome"])) != nil else { throw CleanupFailure.invalidResponse }
                _ = try accountCleanupID(fields["action_id"])
            }
        }
    }
}

/// Separate host-owned protected slot. No raw-path storage or ordinary credential.
@MainActor final class DeviceCleanupJournal {
    private let persistence: any SessionPersistence
    private let scope: AccountCleanupScope
    private(set) var record: DeviceCleanupRecord
    private(set) var bytes: Data?
    private var usable = true
    private var writing = false
    init(persistence: any SessionPersistence, scope: AccountCleanupScope) throws {
        self.persistence = persistence; self.scope = scope
        do { bytes = try persistence.load()?.withBytes { $0 } } catch { throw CleanupFailure.unavailable }
        if let bytes {
            guard bytes.count <= 1048576 else { throw CleanupFailure.invalidResponse }
            let fields = try accountCleanupObject(accountCleanupDocumentForJournal(bytes))
            try accountCleanupKeys(fields, fields: ["version", "scope", "enrollmentFromQuery", "invocationFromActionQuery", "receipts"],
                optional: ["registration", "enrollmentReply", "action", "invocationReply", "directInvocation", "expectedAccountOperationID", "nativeIntentID", "nativeOutcome"])
            do { record = try JSONDecoder().decode(DeviceCleanupRecord.self, from: bytes) } catch { throw CleanupFailure.invalidResponse }
            try record.validate(expectedScope: scope)
        } else { record = DeviceCleanupRecord(scope: scope) }
    }
    func requireOriginal(_ expected: Data?) throws {
        guard usable, !writing, bytes == expected else { throw CleanupFailure.stale }
        let observed: Data?
        do { observed = try persistence.load()?.withBytes { $0 } } catch { throw CleanupFailure.unavailable }
        guard usable, !writing, bytes == expected, observed == expected else { throw CleanupFailure.stale }
    }
    func save(_ next: DeviceCleanupRecord, validate: () throws -> Void) throws {
        guard usable, !writing else { throw CleanupFailure.stale }
        try next.validate(expectedScope: scope)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let nextBytes = try encoder.encode(next)
        guard nextBytes.count <= 1048576 else { throw CleanupFailure.unavailable }
        try validate(); try requireOriginal(bytes)
        writing = true; defer { writing = false }
        do {
            try persistence.save(SessionMaterial(trustedSDKBytes: nextBytes))
            guard try persistence.load()?.withBytes({ $0 }) == nextBytes else { throw CleanupFailure.unavailable }
            try validate()
            guard try persistence.load()?.withBytes({ $0 }) == nextBytes else { throw CleanupFailure.stale }
            record = next; bytes = nextBytes
        } catch {
            usable = false
            if let safe = error as? CleanupFailure { throw safe }
            if error is CancellationError { throw CancellationError() }
            throw CleanupFailure.unavailable
        }
    }
}
private func accountCleanupDocumentForJournal(_ bytes: Data) throws -> CJStrictJSON.StrictJSONValue {
    var parser = StrictCleanupJSON(bytes: Array(bytes))
    do { return try parser.document() } catch { throw CleanupFailure.invalidResponse }
}
