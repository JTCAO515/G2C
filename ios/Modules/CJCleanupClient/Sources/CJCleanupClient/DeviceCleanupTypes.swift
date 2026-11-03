import Foundation
import CryptoKit
import CJStrictJSON
import CJMessageHTTP

public enum DeviceCleanupTarget: String, CaseIterable, Sendable {
    case encryptedMessage = "device-cache/encrypted-message-file"
    case sdkSession = "device-cache/sdk-session-keychain"
    case messageKey = "device-cache/message-key-keychain"
    case tripPending = "device-cache/trip-pending-file"
    case offlineTrip = "device-cache/offline-trip"
    case feedbackPending = "device-cache/feedback-pending"
    case feedbackKey = "device-cache/feedback-key-keychain"
    case memoryManual = "device-cache/memory-manual-pending"
    case memoryLifecycle = "device-cache/memory-lifecycle-pending"
    case memoryTyped = "device-cache/memory-typed-pending"
    case memoryKey = "device-cache/memory-key-keychain"
    case needsPending = "device-cache/needs-pending"
    case needsKey = "device-cache/needs-key-keychain"
    case memoryHistory = "device-cache/memory-history-pending"
    case tripScoped = "device-cache/trip-scoped-pending"
    case needsPlanning = "device-cache/needs-planning-pending"
    case tripKey = "device-cache/trip-key-keychain"
    case offlineKey = "device-cache/offline-key-keychain"
    case offlineWriteResidue = "device-cache/offline-write-residue"
    case memoryErasure = "device-cache/memory-erasure-pending"
    case memoryCandidate = "device-cache/memory-candidate-pending"
}
extension CleanupDeviceVersion {
    public var nativeTargets: [DeviceCleanupTarget] {
        let original: [DeviceCleanupTarget] = [.encryptedMessage, .sdkSession, .messageKey, .tripPending, .offlineTrip,
            .feedbackPending, .feedbackKey, .memoryManual, .memoryLifecycle, .memoryTyped, .memoryKey,
            .needsPending, .needsKey, .memoryHistory, .tripScoped, .needsPlanning, .tripKey, .offlineKey, .offlineWriteResidue]
        return self == .v3 ? original : original + [.memoryErasure, .memoryCandidate]
    }
    var nativeRecordVersion: String { self == .v3 ? "DeviceCleanup.Native@1" : "DeviceCleanup.Native@2" }
}
public enum DeviceCleanupReason: String, Sendable { case accountCleanup = "account_cleanup", sessionInvalid = "session_invalid", offlineExpired = "offline_expired" }
public enum DeviceCleanupResultState: String, Sendable { case pending, unknown, failed, confirmed }
public enum DeviceCleanupNativeOutcome: String, Codable, Sendable { case unknown, failed, confirmed }

/// A checked actual V3 reply bound to the exact original enrollment request.
/// It is not a business/read grant. Neither token nor raw response is public UI data.
public struct DeviceCleanupEnrollment: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let version: CleanupDeviceVersion
    public let scope: AccountCleanupScope
    public let bindingID: String
    public let deviceID: String
    public let stateRef: String
    public let scopeDigest: String
    let deviceCredential: String
    let originalUTF8: Data
    let replyUTF8: Data
    let replyFromQuery: Bool
    public var description: String { "<private device cleanup enrollment>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
    init(originalUTF8: Data, replyUTF8: Data, fromQuery: Bool, scope: AccountCleanupScope) throws {
        guard !originalUTF8.isEmpty, originalUTF8.count <= 16384 else { throw CleanupFailure.invalidResponse }
        let original = try accountCleanupObject(accountCleanupDocument(originalUTF8), fields: ["version", "action_id", "device_id", "state_ref"])
        guard let version = CleanupDeviceVersion(rawValue: try accountCleanupString(original["version"])) else { throw CleanupFailure.invalidResponse }
        self.version = version
        let actionID = try accountCleanupID(original["action_id"])
        deviceID = try accountCleanupID(original["device_id"]); stateRef = try accountCleanupDigest(original["state_ref"])
        let root = try accountCleanupObject(accountCleanupDocument(replyUTF8))
        try deviceCleanupTrace(root)
        let payload: [String: StrictJSONValue]
        if fromQuery {
            try accountCleanupKeys(root, fields: ["version", "request_id", "action_id", "input_sha256", "registration"])
            guard try accountCleanupString(root["version"]) == version.rawValue,
                  try accountCleanupID(root["action_id"]) == actionID,
                  try accountCleanupDigest(root["input_sha256"]) == deviceCleanupSHA(originalUTF8) else { throw CleanupFailure.invalidResponse }
            payload = try accountCleanupObject(root["registration"], fields: ["version", "binding_id", "device_id", "state_ref", "scope_digest", "device_token", "server_time", "business_access"])
        } else {
            try accountCleanupKeys(root, fields: ["version", "request_id", "binding_id", "device_id", "state_ref", "scope_digest", "device_token", "server_time", "business_access"])
            payload = root
        }
        guard try accountCleanupString(payload["version"]) == version.rawValue,
              try accountCleanupID(payload["device_id"]) == deviceID,
              try accountCleanupDigest(payload["state_ref"]) == stateRef,
              try accountCleanupString(payload["business_access"]) == "not_granted" else { throw CleanupFailure.invalidResponse }
        bindingID = try accountCleanupID(payload["binding_id"]); scopeDigest = try accountCleanupDigest(payload["scope_digest"])
        deviceCredential = try accountCleanupToken(payload["device_token"])
        _ = try accountCleanupUInt(payload["server_time"])
        self.scope = scope; self.originalUTF8 = originalUTF8; self.replyUTF8 = replyUTF8; replyFromQuery = fromQuery
    }
}

private struct DeviceCleanupCanonicalCall: Encodable {
    let version: String
    let operation_id: String
    let invocation_id: String
    let binding_id: String
    let scope_digest: String
    let state_ref: String
    let reason: String
    let targets: [String]
    let business_access = "not_granted"
}
/// Sealed actual server invocation. Physical dispatch still requires the host's
/// recorded/current native manifest to match scope/state and every listed target.
public struct DeviceCleanupInvocation: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let version: CleanupDeviceVersion
    public let operationID: String
    public let invocationID: String
    public let bindingID: String
    public let scopeDigest: String
    public let stateRef: String
    public let reason: DeviceCleanupReason
    public let targets: [DeviceCleanupTarget]
    public let requestDigest: String
    public let state: DeviceCleanupResultState
    public let receiptDigest: String?
    let receiptCredential: String
    let canonicalCallUTF8: Data
    public var description: String { "<private original device cleanup invocation>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
    init(result: StrictJSONValue, enrollment: DeviceCleanupEnrollment, directQuery: Bool,
         expectedOperationID: String? = nil) throws {
        let fields: Set<String> = ["call", "request_digest", "state", "receipt_digest", "receipt_token"]
        let root = try accountCleanupObject(result, fields: directQuery ? fields.union(["request_id"]) : fields)
        if directQuery { try deviceCleanupTrace(root) }
        let call = try accountCleanupObject(root["call"], fields: ["version", "operation_id", "invocation_id", "binding_id", "scope_digest", "state_ref", "reason", "targets", "business_access"])
        guard try accountCleanupString(call["version"]) == enrollment.version.rawValue,
              try accountCleanupID(call["binding_id"]) == enrollment.bindingID,
              try accountCleanupDigest(call["scope_digest"]) == enrollment.scopeDigest,
              try accountCleanupDigest(call["state_ref"]) == enrollment.stateRef,
              try accountCleanupString(call["business_access"]) == "not_granted",
              let reason = DeviceCleanupReason(rawValue: try accountCleanupString(call["reason"])),
              case .array(let values) = call["targets"] else { throw CleanupFailure.invalidResponse }
        operationID = try accountCleanupID(call["operation_id"]); invocationID = try accountCleanupID(call["invocation_id"])
        version = enrollment.version
        if let expectedOperationID { guard operationID == expectedOperationID else { throw CleanupFailure.invalidResponse } }
        bindingID = enrollment.bindingID; scopeDigest = enrollment.scopeDigest; stateRef = enrollment.stateRef; self.reason = reason
        targets = try values.map { value in
            guard let target = DeviceCleanupTarget(rawValue: try accountCleanupString(value)) else { throw CleanupFailure.invalidResponse }
            return target
        }
        let expected: Set<DeviceCleanupTarget> = reason == .offlineExpired ? [.offlineTrip, .offlineKey, .offlineWriteResidue] : Set(version.nativeTargets)
        guard targets.count == expected.count, Set(targets) == expected else { throw CleanupFailure.invalidResponse }
        let canonical = DeviceCleanupCanonicalCall(version: version.rawValue, operation_id: operationID, invocation_id: invocationID, binding_id: bindingID,
            scope_digest: scopeDigest, state_ref: stateRef, reason: reason.rawValue, targets: targets.map(\.rawValue))
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        // All allowed call values are ASCII identifiers/fixed literals. This is the
        // protocol's canonical server-call digest, not a reencoding of a client POST.
        canonicalCallUTF8 = try encoder.encode(canonical)
        requestDigest = try accountCleanupDigest(root["request_digest"])
        guard deviceCleanupSHA(canonicalCallUTF8) == requestDigest,
              let state = DeviceCleanupResultState(rawValue: try accountCleanupString(root["state"])) else { throw CleanupFailure.invalidResponse }
        self.state = state
        if case .null = root["receipt_digest"] { receiptDigest = nil }
        else { receiptDigest = try accountCleanupDigest(root["receipt_digest"]) }
        guard state == .pending ? receiptDigest == nil : receiptDigest != nil else { throw CleanupFailure.invalidResponse }
        receiptCredential = try accountCleanupToken(root["receipt_token"])
    }
}
func deviceCleanupTrace(_ fields: [String: StrictJSONValue]) throws {
    guard UUID(uuidString: try accountCleanupString(fields["request_id"])) != nil else { throw CleanupFailure.invalidResponse }
}
func deviceCleanupSHA(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
