import Foundation
import CJSession
import CJStrictJSON

/// Trusted host owns this exact secure slot, separate from the ordinary SDK slot.
/// Raw request/response bytes (including restricted credentials) never go to files.
struct AccountCleanupRecord: Codable {
    var version: String
    let environment: UUID
    let account: UUID
    var deviceV3Scope: AccountCleanupScope?
    var deviceV3FromQuery: Bool?
    var registration: Data?
    var registered: Data?
    var preparation: Data?
    var prepared: Data?
    var preparedFromQuery: Bool
    var confirmation: Data?
    var confirmationDispatched: Bool
    var confirmationResponse: Data?
    var progress: Data?
    init(scope: AccountCleanupScope) {
        version = "AccountCleanup.Native@1"; environment = scope.environment; account = scope.account
        preparedFromQuery = false; confirmationDispatched = false
    }
    func registrationFields() throws -> (deviceID: String, stateRef: String) {
        guard let registration else { throw CleanupFailure.unavailable }
        let fields = try accountCleanupObject(accountCleanupDocument(registration), fields: ["version", "action_id", "device_id", "state_ref"])
        let wire = version == "AccountCleanup.Native@2" ? "CLEANUP-DEVICE@3" : "CLEANUP-DEVICE@1"
        guard try accountCleanupString(fields["version"]) == wire else { throw CleanupFailure.invalidResponse }
        _ = try accountCleanupID(fields["action_id"])
        return (try accountCleanupID(fields["device_id"]), try accountCleanupDigest(fields["state_ref"]))
    }
    func device() throws -> AccountCleanupDeviceBinding {
        let fields = try registrationFields()
        guard let registered else { throw CleanupFailure.unavailable }
        if version == "AccountCleanup.Native@2" {
            guard let deviceV3Scope, let deviceV3FromQuery, let registration else { throw CleanupFailure.invalidResponse }
            return try AccountCleanupDeviceBinding(v3: DeviceCleanupEnrollment(originalUTF8: registration, replyUTF8: registered,
                fromQuery: deviceV3FromQuery, scope: deviceV3Scope))
        }
        return try AccountCleanupDeviceBinding(accountCleanupDocument(registered), deviceID: fields.deviceID, stateRef: fields.stateRef)
    }
    func preparationActionID() throws -> String {
        guard let preparation else { throw CleanupFailure.unavailable }
        let fields = try accountCleanupObject(accountCleanupDocument(preparation), fields: ["version", "action_id", "binding_id"])
        guard try accountCleanupString(fields["version"]) == "CLEANUP-API@1",
              try accountCleanupID(fields["binding_id"]) == device().bindingID else { throw CleanupFailure.invalidResponse }
        return try accountCleanupID(fields["action_id"])
    }
    func original() throws -> AccountCleanupPreparation {
        _ = try preparationActionID()
        guard let prepared else { throw CleanupFailure.unavailable }
        let value = try accountCleanupDocument(prepared)
        let original: StrictJSONValue
        if preparedFromQuery {
            let fields = try accountCleanupObject(value, fields: ["version", "request_id", "preparation"])
            guard try accountCleanupString(fields["version"]) == "CLEANUP-API@1", let observed = fields["preparation"] else { throw CleanupFailure.invalidResponse }
            original = observed
        } else { original = value }
        return try AccountCleanupPreparation(original, expectedBindingID: device().bindingID, fromQuery: preparedFromQuery)
    }
    func currentProgress() throws -> AccountCleanupProgress? {
        guard let progress = progress ?? confirmationResponse else { return nil }
        return try AccountCleanupProgress(accountCleanupDocument(progress), originalOperationID: original().operationID)
    }
    func validate(scope: AccountCleanupScope) throws {
        guard ["AccountCleanup.Native@1", "AccountCleanup.Native@2"].contains(version), environment == scope.environment, account == scope.account,
              registration != nil || (registered == nil && preparation == nil && prepared == nil && confirmation == nil && confirmationResponse == nil && progress == nil),
              registered != nil || (preparation == nil && prepared == nil && confirmation == nil && confirmationResponse == nil && progress == nil),
              preparation != nil || (prepared == nil && confirmation == nil && confirmationResponse == nil && progress == nil),
              prepared != nil || (confirmation == nil && confirmationResponse == nil && progress == nil),
              confirmation != nil || (!confirmationDispatched && confirmationResponse == nil),
              confirmationResponse == nil || confirmationDispatched,
              !preparedFromQuery || prepared != nil else { throw CleanupFailure.invalidResponse }
        if version == "AccountCleanup.Native@1" {
            guard deviceV3Scope == nil, deviceV3FromQuery == nil else { throw CleanupFailure.invalidResponse }
        } else {
            guard let deviceV3Scope, deviceV3Scope.environment == environment, deviceV3Scope.account == account,
                  deviceV3FromQuery != nil, registration != nil, registered != nil else { throw CleanupFailure.invalidResponse }
        }
        guard [registration, preparation, confirmation].compactMap({ $0 }).allSatisfy({ !$0.isEmpty && $0.count <= 16384 }) else { throw CleanupFailure.invalidResponse }
        if registration != nil { _ = try registrationFields() }
        if registered != nil { _ = try device() }
        if preparation != nil { _ = try preparationActionID() }
        if prepared != nil { _ = try original() }
        if let confirmation {
            let fields = try accountCleanupObject(accountCleanupDocument(confirmation), fields: ["version", "registry_digest", "confirmation"])
            guard try accountCleanupString(fields["version"]) == "CLEANUP-API@1",
                  try accountCleanupString(fields["confirmation"]) == "DELETE_ACCOUNT",
                  try accountCleanupDigest(fields["registry_digest"]) == original().registryDigest else { throw CleanupFailure.invalidResponse }
        }
        _ = try currentProgress()
        if let confirmationResponse { _ = try AccountCleanupProgress(accountCleanupDocument(confirmationResponse), originalOperationID: original().operationID) }
        for bytes in [registered, prepared, confirmationResponse, progress].compactMap({ $0 }) {
            let fields = try accountCleanupObject(accountCleanupDocument(bytes))
            guard let trace = fields["request_id"], UUID(uuidString: try accountCleanupString(trace)) != nil else { throw CleanupFailure.invalidResponse }
        }
    }
}

@MainActor final class AccountCleanupJournal {
    private let persistence: any SessionPersistence
    private let scope: AccountCleanupScope
    private(set) var bytes: Data?
    private(set) var record: AccountCleanupRecord
    private var writing = false
    private var usable = true
    init(persistence: any SessionPersistence, scope: AccountCleanupScope) throws {
        self.persistence = persistence; self.scope = scope
        do { bytes = try persistence.load()?.withBytes { $0 } } catch { throw CleanupFailure.unavailable }
        record = try bytes.map { try Self.decode($0, scope: scope) } ?? AccountCleanupRecord(scope: scope)
    }
    private static func decode(_ bytes: Data, scope: AccountCleanupScope) throws -> AccountCleanupRecord {
        guard bytes.count <= 524288 else { throw CleanupFailure.invalidResponse }
        var parser = StrictCleanupJSON(bytes: Array(bytes))
        let object = try accountCleanupObject(parser.document())
        try accountCleanupKeys(object, fields: ["version", "environment", "account", "preparedFromQuery", "confirmationDispatched"],
            optional: ["deviceV3Scope", "deviceV3FromQuery", "registration", "registered", "preparation", "prepared", "confirmation", "confirmationResponse", "progress"])
        let record: AccountCleanupRecord
        do { record = try JSONDecoder().decode(AccountCleanupRecord.self, from: bytes) } catch { throw CleanupFailure.invalidResponse }
        try record.validate(scope: scope)
        return record
    }
    /// Final secure-record equality fence; no host scope/credential callback follows.
    func requireOriginal(_ expected: Data?) throws {
        guard usable, !writing, bytes == expected else { throw CleanupFailure.stale }
        let observed: Data?
        do { observed = try persistence.load()?.withBytes { $0 } } catch { throw CleanupFailure.unavailable }
        guard usable, !writing, bytes == expected, observed == expected else { throw CleanupFailure.stale }
    }
    func save(_ next: AccountCleanupRecord, validate: () throws -> Void) throws {
        guard usable, !writing else { throw CleanupFailure.stale }
        try next.validate(scope: scope)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let data = try encoder.encode(next)
        guard data.count <= 524288 else { throw CleanupFailure.unavailable }
        try validate()
        try requireOriginal(bytes)
        writing = true
        defer { writing = false }
        do {
            try persistence.save(SessionMaterial(trustedSDKBytes: data))
            let observed = try persistence.load()?.withBytes { $0 }
            guard observed == data else { throw CleanupFailure.unavailable }
            try validate()
            // A source callback may replace the secure slot. Do not publish or send
            // from a record which is no longer the exact original durable intent.
            let final = try persistence.load()?.withBytes { $0 }
            guard final == data else { throw CleanupFailure.stale }
            bytes = data; record = next
        } catch {
            usable = false // never dispatch/retry against uncertain secure persistence
            if let safe = error as? CleanupFailure { throw safe }
            if error is CancellationError { throw CancellationError() }
            throw CleanupFailure.unavailable
        }
    }
}
