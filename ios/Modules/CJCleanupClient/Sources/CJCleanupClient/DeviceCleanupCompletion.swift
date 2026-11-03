import Foundation

public enum DeviceCleanupContentStatus: String, Sendable {
    case notApplicable = "not_applicable", inProgress = "in_progress", unknown, failed, blocked, complete
}
/// Sealed original-call observation, never a filesystem selector or ordinary
/// authorization. The Root must additionally retire/verify its exact records.
public struct DeviceCleanupCompletion: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let scope: AccountCleanupScope
    public let operationID: String
    public let bindingID: String
    public let invocationID: String
    public let requestDigest: String
    public let reason: DeviceCleanupReason
    public let deviceState: DeviceCleanupResultState
    public let receiptDigest: String?
    public let contentStatus: DeviceCleanupContentStatus
    public let registryDigest: String?
    public let controlRecordProtocol: String?
    public let journalSHA256: String
    public let permitsAccountRecordFinalization: Bool
    public var description: String { "<private original device completion>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }

    init(reply: Data, invocation: DeviceCleanupInvocation, scope: AccountCleanupScope,
         acknowledgedConfirmedReceipt: String?, journalSHA256: String) throws {
        guard !reply.isEmpty, reply.count <= 4096 else { throw CleanupFailure.invalidResponse }
        let fields = try accountCleanupObject(accountCleanupDocument(reply), fields: ["version", "request_id", "operation_id", "binding_id",
            "invocation_id", "request_digest", "reason", "device_state", "receipt_digest", "content_status", "registry_digest",
            "control_record_protocol", "complete_scope", "business_access"])
        try deviceCleanupTrace(fields)
        guard try accountCleanupString(fields["version"]) == "CLEANUP-DEVICE-COMPLETION@1",
              try accountCleanupID(fields["operation_id"]) == invocation.operationID,
              try accountCleanupID(fields["binding_id"]) == invocation.bindingID,
              try accountCleanupID(fields["invocation_id"]) == invocation.invocationID,
              try accountCleanupDigest(fields["request_digest"]) == invocation.requestDigest,
              try accountCleanupString(fields["reason"]) == invocation.reason.rawValue,
              try accountCleanupString(fields["business_access"]) == "not_granted",
              let state = DeviceCleanupResultState(rawValue: try accountCleanupString(fields["device_state"])),
              let content = DeviceCleanupContentStatus(rawValue: try accountCleanupString(fields["content_status"])) else { throw CleanupFailure.invalidResponse }
        self.scope = scope; operationID = invocation.operationID; bindingID = invocation.bindingID
        invocationID = invocation.invocationID; requestDigest = invocation.requestDigest; reason = invocation.reason
        deviceState = state; contentStatus = content; self.journalSHA256 = journalSHA256
        if case .null = fields["receipt_digest"] { receiptDigest = nil }
        else { receiptDigest = try accountCleanupDigest(fields["receipt_digest"]) }
        guard ![.confirmed, .failed].contains(state) || receiptDigest != nil else { throw CleanupFailure.invalidResponse }
        if case .null = fields["registry_digest"] { registryDigest = nil }
        else { registryDigest = try accountCleanupDigest(fields["registry_digest"]) }
        if case .null = fields["control_record_protocol"] { controlRecordProtocol = nil }
        else {
            let policy = try accountCleanupString(fields["control_record_protocol"])
            guard policy == "CLEANUP-CONTROL-RECORDS@1" else { throw CleanupFailure.invalidResponse }
            controlRecordProtocol = policy
        }
        if reason == .accountCleanup {
            guard content != .notApplicable,
                  try accountCleanupString(fields["complete_scope"]) == "frozen_online_domains_only",
                  controlRecordProtocol == nil || registryDigest != nil else { throw CleanupFailure.invalidResponse }
        } else {
            guard content == .notApplicable, registryDigest == nil, controlRecordProtocol == nil,
                  try accountCleanupString(fields["complete_scope"]) == "original_device_action_only" else { throw CleanupFailure.invalidResponse }
        }
        if let acknowledgedConfirmedReceipt {
            // A received representation cannot retarget this client's own ACK.
            guard state == .confirmed, receiptDigest == acknowledgedConfirmedReceipt else { throw CleanupFailure.invalidResponse }
        }
        permitsAccountRecordFinalization = reason == .accountCleanup && content == .complete && state == .confirmed
            && acknowledgedConfirmedReceipt != nil && receiptDigest == acknowledgedConfirmedReceipt
            && registryDigest != nil && controlRecordProtocol == "CLEANUP-CONTROL-RECORDS@1"
    }
}
