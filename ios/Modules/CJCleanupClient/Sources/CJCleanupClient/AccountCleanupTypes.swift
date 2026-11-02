import Foundation
import CJStrictJSON

public struct AccountCleanupScope: Equatable, Codable, Sendable {
    public let environment: UUID
    public let account: UUID
    public let generation: UUID
    public init(environment: UUID, account: UUID, generation: UUID) {
        self.environment = environment; self.account = account; self.generation = generation
    }
}
public enum AccountCleanupStatus: String, Sendable {
    case awaitingConfirmation = "awaiting_confirmation", blocked, inProgress = "in_progress", unknown, failed, complete
}
public enum AccountCleanupStepState: String, Sendable { case pending, inProgress = "in_progress", unknown, failed, confirmed }
public struct AccountCleanupStep: Sendable {
    public let target: String
    public let state: AccountCleanupStepState
}
public struct AccountCleanupDeviceProgress: Sendable {
    public let bindingID: String
    public let invocationID: String
    public let state: AccountCleanupStepState
}
/// Safe projection only. Online completion never claims backups/other devices erased.
public struct AccountCleanupProgress: Sendable {
    public let operationID: String
    public let status: AccountCleanupStatus
    public let revision: Int64?
    public let onlineStatus: AccountCleanupStatus?
    public let steps: [AccountCleanupStep]
    public let devices: [AccountCleanupDeviceProgress]
    public let businessRevoked: Bool
    public let reason: String?
    public var allDevicesAndBackupsVerified: Bool { false }
    init(_ value: StrictJSONValue, originalOperationID: String) throws {
        let object = try accountCleanupObject(value)
        guard try accountCleanupString(object["version"]) == "CLEANUP-API@1",
              try accountCleanupID(object["operation_id"]) == originalOperationID else { throw CleanupFailure.invalidResponse }
        operationID = originalOperationID
        let phase = try accountCleanupString(object["phase"])
        let rawStatus = try accountCleanupString(object["status"])
        guard let status = AccountCleanupStatus(rawValue: rawStatus) else { throw CleanupFailure.invalidResponse }
        self.status = status
        guard case .array(let rows) = object["steps"], rows.count <= 128 else { throw CleanupFailure.invalidResponse }
        steps = try rows.map { value in
            let step = try accountCleanupObject(value, fields: ["target", "state"])
            guard let state = AccountCleanupStepState(rawValue: try accountCleanupString(step["state"])) else { throw CleanupFailure.invalidResponse }
            return AccountCleanupStep(target: try accountCleanupID(step["target"]), state: state)
        }
        guard Set(steps.map(\.target)).count == steps.count else { throw CleanupFailure.invalidResponse }
        if phase == "prepared", status == .awaitingConfirmation {
            try accountCleanupKeys(object, fields: ["version", "request_id", "operation_id", "phase", "status", "revision", "steps"])
            guard steps.isEmpty else { throw CleanupFailure.invalidResponse }
            revision = try accountCleanupUInt(object["revision"]); onlineStatus = nil; devices = []; businessRevoked = false; reason = nil
        } else if phase == "prepared", status == .blocked {
            try accountCleanupKeys(object, fields: ["version", "request_id", "operation_id", "phase", "status", "steps", "reason", "business_access"])
            guard try accountCleanupString(object["business_access"]) == "unchanged",
                  try accountCleanupString(object["reason"]) == "domain_hooks_unavailable" else { throw CleanupFailure.invalidResponse }
            revision = nil; onlineStatus = nil; devices = []; businessRevoked = false; reason = "domain_hooks_unavailable"
        } else {
            try accountCleanupKeys(object, fields: ["version", "request_id", "operation_id", "phase", "status", "online_status", "revision", "steps", "devices", "obligations", "complete_scope", "business_access"], optional: ["reason"])
            guard phase == "confirmed", [.blocked, .unknown, .failed, .inProgress].contains(status),
                  let online = AccountCleanupStatus(rawValue: try accountCleanupString(object["online_status"])), online != .awaitingConfirmation,
                  try accountCleanupString(object["complete_scope"]) == "frozen_online_domains_only",
                  try accountCleanupString(object["business_access"]) == "revoked" else { throw CleanupFailure.invalidResponse }
            let obligations = try accountCleanupObject(object["obligations"], fields: ["backups", "other_devices", "external"])
            guard try accountCleanupString(obligations["backups"]) == "unverified_30_day_rolling",
                  try accountCleanupString(obligations["other_devices"]) == "pending_actual_receipts",
                  try accountCleanupString(obligations["external"]) == "unverified" else { throw CleanupFailure.invalidResponse }
            guard case .array(let entries) = object["devices"], entries.count <= 128 else { throw CleanupFailure.invalidResponse }
            devices = try entries.map { value in
                let entry = try accountCleanupObject(value, fields: ["binding_id", "invocation_id", "state", "provenance"])
                guard try accountCleanupString(entry["provenance"]) == "authenticated_current_device_report",
                      let state = AccountCleanupStepState(rawValue: try accountCleanupString(entry["state"])) else { throw CleanupFailure.invalidResponse }
                return AccountCleanupDeviceProgress(bindingID: try accountCleanupID(entry["binding_id"]), invocationID: try accountCleanupID(entry["invocation_id"]), state: state)
            }
            guard Set(devices.map(\.invocationID)).count == devices.count,
                  online != .complete || (!steps.isEmpty && steps.allSatisfy { $0.state == .confirmed }) else { throw CleanupFailure.invalidResponse }
            revision = try accountCleanupUInt(object["revision"]); onlineStatus = online; businessRevoked = true
            reason = try object["reason"].map { try accountCleanupString($0) }
        }
    }
}
/// Constructor is sealed to checked original service responses; contains no public credential.
public struct AccountCleanupPreparation: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public var description: String { "<private cleanup preparation>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
    public let operationID: String
    public let registryDigest: String
    public let planDigest: String
    public let bindingID: String
    public let revision: Int64
    let progressToken: String
    let phase: String
    init(_ value: StrictJSONValue, expectedBindingID: String, fromQuery: Bool) throws {
        let fields: Set<String> = ["operation_id", "phase", "registry_digest", "plan_digest", "binding_id", "revision", "progress_token"]
        let object = try accountCleanupObject(value, fields: fromQuery ? fields : fields.union(["version", "request_id", "confirmation"]))
        if !fromQuery {
            guard try accountCleanupString(object["version"]) == "CLEANUP-API@1",
                  try accountCleanupString(object["confirmation"]) == "DELETE_ACCOUNT" else { throw CleanupFailure.invalidResponse }
        }
        operationID = try accountCleanupID(object["operation_id"]); bindingID = try accountCleanupID(object["binding_id"])
        guard bindingID == expectedBindingID else { throw CleanupFailure.invalidResponse }
        registryDigest = try accountCleanupDigest(object["registry_digest"]); planDigest = try accountCleanupDigest(object["plan_digest"])
        revision = try accountCleanupUInt(object["revision"]); progressToken = try accountCleanupToken(object["progress_token"])
        phase = try accountCleanupString(object["phase"])
        guard ["prepared", "confirmed"].contains(phase) else { throw CleanupFailure.invalidResponse }
    }
}
struct AccountCleanupDeviceBinding: CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    var description: String { "<private cleanup device binding>" }
    var debugDescription: String { description }
    var customMirror: Mirror { Mirror(self, children: [:]) }
    let bindingID: String
    let deviceID: String
    let stateRef: String
    let scopeDigest: String
    let deviceToken: String
    init(_ value: StrictJSONValue, deviceID: String, stateRef: String) throws {
        let object = try accountCleanupObject(value, fields: ["version", "request_id", "binding_id", "device_id", "state_ref", "scope_digest", "device_token", "server_time", "business_access"])
        guard try accountCleanupString(object["version"]) == "CLEANUP-DEVICE@1",
              try accountCleanupID(object["device_id"]) == deviceID,
              try accountCleanupDigest(object["state_ref"]) == stateRef,
              try accountCleanupString(object["business_access"]) == "not_granted" else { throw CleanupFailure.invalidResponse }
        bindingID = try accountCleanupID(object["binding_id"]); self.deviceID = deviceID; self.stateRef = stateRef
        scopeDigest = try accountCleanupDigest(object["scope_digest"]); deviceToken = try accountCleanupToken(object["device_token"])
        _ = try accountCleanupUInt(object["server_time"])
    }
}
func accountCleanupObject(_ value: StrictJSONValue?, fields: Set<String>? = nil) throws -> [String: StrictJSONValue] {
    guard case .object(let object) = value else { throw CleanupFailure.invalidResponse }
    if let fields { try accountCleanupKeys(object, fields: fields) }
    return object
}
func accountCleanupKeys(_ object: [String: StrictJSONValue], fields: Set<String>, optional: Set<String> = []) throws {
    guard fields.isSubset(of: Set(object.keys)), Set(object.keys).isSubset(of: fields.union(optional)) else { throw CleanupFailure.invalidResponse }
}
func accountCleanupString(_ value: StrictJSONValue?) throws -> String {
    guard case .string(let string) = value, !string.isEmpty, string.utf8.count <= 4096, !string.contains("\0") else { throw CleanupFailure.invalidResponse }
    return string
}
func accountCleanupID(_ value: StrictJSONValue?) throws -> String {
    let string = try accountCleanupString(value)
    guard cleanupIdentifier(string, maximum: 160) else { throw CleanupFailure.invalidResponse }
    return string
}
func accountCleanupToken(_ value: StrictJSONValue?) throws -> String {
    let string = try accountCleanupString(value)
    guard string.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { throw CleanupFailure.invalidResponse }
    return string
}
func accountCleanupDigest(_ value: StrictJSONValue?) throws -> String {
    let string = try accountCleanupString(value)
    guard string.utf8.count == 64, string.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { throw CleanupFailure.invalidResponse }
    return string
}
func accountCleanupUInt(_ value: StrictJSONValue?) throws -> Int64 {
    guard case .number(let token) = value, !token.isEmpty, token.utf8.allSatisfy({ (48...57).contains($0) }), let number = Int64(token) else { throw CleanupFailure.invalidResponse }
    return number
}
func accountCleanupDocument(_ bytes: Data) throws -> StrictJSONValue {
    guard !bytes.isEmpty, bytes.count <= 65536 else { throw CleanupFailure.invalidResponse }
    var parser = StrictCleanupJSON(bytes: Array(bytes))
    do { return try parser.document() } catch { throw CleanupFailure.invalidResponse }
}
