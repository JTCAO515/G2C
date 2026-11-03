import Foundation
import CJStrictJSON

/// Mandatory explicit acknowledgement of C's broad derived-result scope.
/// It is neither account deletion nor a grant to organize history.
public enum MemoryErasureRangeAcknowledgement: Sendable { case ownedTripDerivedScope }

struct MemoryErasureAction: Sendable {
    let actionID: String
    let itemID: String
    let expectedVersion: Int64
    let originalUTF8: Data
    var inputSHA256: String { digest(originalUTF8) }

    init(itemID: String, expectedVersion: Int64, acknowledgement: MemoryErasureRangeAcknowledgement) throws {
        guard erasureIdentifier(itemID), expectedVersion > 0 else { throw MemoryFailure.invalidInput }
        actionID = UUID().uuidString; self.itemID = itemID; self.expectedVersion = expectedVersion
        originalUTF8 = try JSONSerialization.data(withJSONObject: [
            "version": "MEMORY-ERASURE@1", "action_id": actionID, "item_id": itemID,
            "expected_version": expectedVersion, "derived_range": "owned_trip_derived_scope"
        ], options: [.sortedKeys, .withoutEscapingSlashes])
        guard originalUTF8.count <= 32768 else { throw MemoryFailure.invalidInput }
    }
    /// Persisted-data boundary. Never reconstruct a retry from the decoded fields.
    init(originalUTF8: Data) throws {
        guard !originalUTF8.isEmpty, originalUTF8.count <= 32768 else { throw MemoryFailure.invalidResponse }
        var parser = StrictMemoryJSON(bytes: Array(originalUTF8))
        let fields = try historyObject(parser.document(), fields: ["version", "action_id", "item_id", "expected_version", "derived_range"])
        guard try historyString(fields["version"], limit: 64) == "MEMORY-ERASURE@1",
              try historyString(fields["derived_range"], limit: 64) == "owned_trip_derived_scope" else { throw MemoryFailure.invalidResponse }
        actionID = try erasureIdentifier(fields["action_id"])
        itemID = try erasureIdentifier(fields["item_id"])
        expectedVersion = try historyInteger(fields["expected_version"])
        guard expectedVersion > 0 else { throw MemoryFailure.invalidResponse }
        self.originalUTF8 = originalUTF8
    }
}

public enum MemoryErasurePhase: String, Sendable { case inProgress = "in_progress", unknown, blocked, failed, complete }
public enum MemoryErasureStepState: String, Sendable { case pending, inProgress = "in_progress", unknown, failed, confirmed }
public enum MemoryErasureTarget: String, CaseIterable, Sendable {
    case message = "business/message", run = "checkpoints/run", usage = "business/usage"
    case derived = "memory-derived", management = "business/memory-management-actions"
    case trip = "business/trip-authoritative", memory = "business/memory-authoritative", metadata = "business/cleanup-metadata"
}
public struct MemoryErasureStep: Sendable {
    public let target: MemoryErasureTarget
    public let state: MemoryErasureStepState
}

/// The original operation's last protected projection. A known stop is distinct
/// from online completion; an unavailable GET cannot create either result.
public struct MemoryErasureProgress: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let actionID: String
    public let operationID: String
    public let stoppedItemVersion: Int64
    public let scopeEpoch: Int64
    public let phase: MemoryErasurePhase
    public let steps: [MemoryErasureStep]
    public var stopped: Bool { true }
    public var onlineComplete: Bool { phase == .complete }
    public var description: String { "<private original memory erasure progress>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }

    init(response: Data, trace: String, original: MemoryErasureAction, post: Bool) throws {
        let value = try candidateEnvelope(response, trace: trace, version: "MEMORY-ERASURE-response@1")
        var names: Set<String> = ["action_id", "operation_id", "item_version", "scope_epoch", "stop_use", "online_status", "steps"]
        if post { names.formUnion(["item_id", "derived_range", "precise_item_match", "retained", "limits"]) }
        let fields = try historyObject(value, fields: names)
        actionID = try erasureIdentifier(fields["action_id"])
        operationID = try historyString(fields["operation_id"], limit: 128)
        stoppedItemVersion = try historyInteger(fields["item_version"])
        scopeEpoch = try historyInteger(fields["scope_epoch"])
        let (next, overflow) = original.expectedVersion.addingReportingOverflow(1)
        guard same(actionID, original.actionID), validErasureOperationID(operationID), !overflow,
              stoppedItemVersion == next, scopeEpoch > 0,
              try historyString(fields["stop_use"], limit: 32) == "stopped",
              let phase = MemoryErasurePhase(rawValue: try historyString(fields["online_status"], limit: 32)),
              case .array(let rawSteps) = fields["steps"] else { throw MemoryFailure.invalidResponse }
        self.phase = phase
        steps = try rawSteps.map { value in
            let step = try historyObject(value, fields: ["target", "state"])
            guard let target = MemoryErasureTarget(rawValue: try historyString(step["target"], limit: 128)),
                  let state = MemoryErasureStepState(rawValue: try historyString(step["state"], limit: 32)) else { throw MemoryFailure.invalidResponse }
            return .init(target: target, state: state)
        }
        let targets = Set(steps.map(\.target))
        guard steps.count == targets.count,
              (phase == .unknown && steps.isEmpty) || targets == Set(MemoryErasureTarget.allCases),
              phase != .complete || steps.allSatisfy({ $0.state == .confirmed }) else { throw MemoryFailure.invalidResponse }
        if post {
            guard same(try erasureIdentifier(fields["item_id"]), original.itemID),
                  try historyString(fields["derived_range"], limit: 64) == "owned_trip_derived_scope",
                  case .boolean(false) = fields["precise_item_match"] else { throw MemoryFailure.invalidResponse }
            try erasureStringSet(fields["retained"], expected: ["original_chat", "accepted_formal_trip", "minimum_hashed_barriers"])
            try erasureStringSet(fields["limits"], expected: ["already_sent_model_requests", "already_displayed_history", "external_provider_retention"])
        }
    }
}

func validErasureOperationID(_ value: String) -> Bool {
    let prefix = "memory-erasure-v1:"
    guard value.hasPrefix(prefix) else { return false }
    let suffix = value.dropFirst(prefix.count)
    return suffix.utf8.count == 64 && suffix.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
}
func erasureIdentifier(_ value: String) -> Bool {
    !value.contains("\0") && !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        && value.unicodeScalars.count <= 4096 && value.utf8.count <= 16384
}
func erasureIdentifier(_ value: StrictJSONValue?) throws -> String {
    let text = try historyString(value, limit: 16384)
    guard erasureIdentifier(text) else { throw MemoryFailure.invalidResponse }; return text
}
private func erasureStringSet(_ value: StrictJSONValue?, expected: Set<String>) throws {
    guard case .array(let raw) = value else { throw MemoryFailure.invalidResponse }
    let values = try raw.map { try historyString($0, limit: 128) }
    guard values.count == expected.count, Set(values) == expected else { throw MemoryFailure.invalidResponse }
}
