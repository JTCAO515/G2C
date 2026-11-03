import Foundation
import CJAPI
import CJStrictJSON

public enum MemoryCandidateReview: Sendable {
    case reject
    case confirm(kind: Components.Schemas.MemoryManualSaveCommand.kindPayload, text: String, occurredAt: String, travel: MemoryTravelSelection?)
}

/// One original explicit review. No model-supplied source/owner/confirmation or
/// caller-supplied backend operation is encoded. Persistence precedes dispatch.
struct MemoryCandidateAction: Sendable {
    let actionID: String
    let producer: MemoryCandidateJob
    let candidateID: String
    let expectedCandidateVersion: Int64
    let expectedMemoryEpoch: Int64
    let operation: String
    let originalUTF8: Data
    var inputSHA256: String { digest(originalUTF8) }

    init(page: MemoryCandidatePage, candidateID: String, review: MemoryCandidateReview) throws {
        guard let candidate = page.candidates.first(where: { same($0.id, candidateID) }), candidate.status == .candidate else { throw MemoryFailure.invalidInput }
        try self.init(candidate: candidate, producer: page.producer, memoryEpoch: page.memoryEpoch, review: review)
    }
    init(candidate: MemoryCandidate, producer: MemoryCandidateJob, memoryEpoch: Int64, review: MemoryCandidateReview) throws {
        guard candidate.status == .candidate else { throw MemoryFailure.invalidInput }
        actionID = UUID().uuidString; self.producer = producer; candidateID = candidate.id
        expectedCandidateVersion = candidate.version; expectedMemoryEpoch = memoryEpoch
        var fields: [String: Any] = ["version": "MEMORY-CANDIDATE@1", "action_id": actionID,
            "job_id": producer.jobID, "attempt_id": producer.attemptID, "candidate_id": candidate.id,
            "expected_candidate_version": candidate.version, "expected_memory_epoch": memoryEpoch]
        switch review {
        case .reject: operation = "reject"
        case .confirm(let kind, let text, let occurredAt, let travel):
            guard kind != .inference, validCandidateEdit(text), validCandidateEdit(occurredAt) else { throw MemoryFailure.invalidInput }
            let context: Any
            if let original = candidate.travel {
                guard let travel, same(original.id, travel.id) else { throw MemoryFailure.invalidInput }
                context = ["kind": "travel", "id": travel.id, "expected_version": travel.expectedVersion]
            } else {
                guard travel == nil else { throw MemoryFailure.invalidInput }; context = NSNull()
            }
            operation = "confirm"
            fields.merge(["kind": kind.rawValue, "text": text, "occurred_at": occurredAt,
                          "extent": candidate.extent.rawValue, "context": context]) { _, new in new }
        }
        fields["operation"] = operation
        originalUTF8 = try JSONSerialization.data(withJSONObject: fields, options: [.sortedKeys, .withoutEscapingSlashes])
        guard originalUTF8.count <= 32768 else { throw MemoryFailure.invalidInput }
    }
    /// Persisted-data boundary. Original whitespace, escapes and UTF8 remain exact.
    init(originalUTF8 raw: Data) throws {
        guard !raw.isEmpty, raw.count <= 32768 else { throw MemoryFailure.invalidResponse }
        var parser = StrictMemoryJSON(bytes: Array(raw))
        guard case .object(let fields) = try parser.document(),
              try historyString(fields["version"], limit: 64) == "MEMORY-CANDIDATE@1" else { throw MemoryFailure.invalidResponse }
        operation = try historyString(fields["operation"], limit: 16)
        let base: Set<String> = ["version", "action_id", "job_id", "attempt_id", "candidate_id", "expected_candidate_version", "expected_memory_epoch", "operation"]
        switch operation {
        case "reject": guard Set(fields.keys) == base else { throw MemoryFailure.invalidResponse }
        case "confirm":
            guard Set(fields.keys) == base.union(["kind", "text", "occurred_at", "extent", "context"]),
                  let kind = Components.Schemas.MemoryManualSaveCommand.kindPayload(rawValue: try historyString(fields["kind"], limit: 32)), kind != .inference else { throw MemoryFailure.invalidResponse }
            _ = try candidateText(fields["text"]); _ = try candidateText(fields["occurred_at"])
            let extent = try historyString(fields["extent"], limit: 32)
            if extent == "long_term" { guard case .null = fields["context"] else { throw MemoryFailure.invalidResponse } }
            else {
                guard extent == "current", let value = fields["context"] else { throw MemoryFailure.invalidResponse }
                let context = try historyObject(value, fields: ["kind", "id", "expected_version"])
                guard try historyString(context["kind"], limit: 16) == "travel" else { throw MemoryFailure.invalidResponse }
                do { _ = try MemoryTravelSelection(id: historyString(context["id"], limit: 32), expectedVersion: historyInteger(context["expected_version"])) }
                catch { throw MemoryFailure.invalidResponse }
            }
        default: throw MemoryFailure.invalidResponse
        }
        actionID = try candidateIdentity(fields["action_id"])
        producer = try MemoryCandidateJob(.object(["job_id": fields["job_id"]!, "attempt_id": fields["attempt_id"]!]))
        candidateID = try candidateItemIdentity(fields["candidate_id"])
        expectedCandidateVersion = try historyInteger(fields["expected_candidate_version"])
        expectedMemoryEpoch = try historyInteger(fields["expected_memory_epoch"])
        guard expectedCandidateVersion > 0, expectedMemoryEpoch > 0 else { throw MemoryFailure.invalidResponse }
        originalUTF8 = raw
    }
}
private func validCandidateEdit(_ value: String) -> Bool {
    !value.contains("\0") && !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        && value.unicodeScalars.count <= 4096 && value.utf8.count <= 16384
}

/// Immutable result of the original review, not a current active-Memory grant.
public struct MemoryCandidateReceipt: Sendable {
    public let actionID: String
    public let candidateID: String
    public let inputSHA256: String
    public let itemVersion: Int64
    public let active: Bool
    public let sourceID: String?
    public let sourceVersion: Int64?
    init(_ value: StrictJSONValue, original: MemoryCandidateAction) throws {
        let fields = try historyObject(value, fields: ["version", "action_id", "candidate_id", "input_sha256", "receipt"])
        guard try historyString(fields["version"], limit: 64) == "MEMORY-CANDIDATE-result@1" else { throw MemoryFailure.invalidResponse }
        actionID = try candidateIdentity(fields["action_id"]); candidateID = try candidateItemIdentity(fields["candidate_id"])
        inputSHA256 = try historyString(fields["input_sha256"], limit: 64)
        guard same(actionID, original.actionID), same(candidateID, original.candidateID),
              same(inputSHA256, original.inputSHA256), let value = fields["receipt"], case .object(let receipt) = value else { throw MemoryFailure.invalidResponse }
        let status = try historyString(receipt["status"], limit: 16)
        active = status == "active"
        guard (original.operation == "confirm" && active) || (original.operation == "reject" && status == "rejected"),
              Set(receipt.keys) == (active ? ["item_id", "version", "status", "source_id", "source_version"] : ["item_id", "version", "status"]),
              same(try candidateItemIdentity(receipt["item_id"]), candidateID) else { throw MemoryFailure.invalidResponse }
        itemVersion = try historyInteger(receipt["version"])
        let (expected, overflow) = original.expectedCandidateVersion.addingReportingOverflow(1)
        guard !overflow, itemVersion == expected else { throw MemoryFailure.invalidResponse }
        if active {
            sourceID = try candidateText(receipt["source_id"]); sourceVersion = try historyInteger(receipt["source_version"])
            guard let sourceVersion, sourceVersion > 0 else { throw MemoryFailure.invalidResponse }
        } else { sourceID = nil; sourceVersion = nil }
    }
}
