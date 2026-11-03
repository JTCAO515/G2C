import Foundation
import CJStrictJSON

public enum MemoryCandidateReadWire: Sendable { case producerJobsV1, canonicalProjectionV2 }

public struct MemoryCandidateProjectionItem: Sendable {
    public let candidate: MemoryCandidate
    public let producer: MemoryCandidateJob
    init(_ value: StrictJSONValue) throws {
        guard case .object(var fields) = value, let review = fields.removeValue(forKey: "review") else { throw MemoryFailure.invalidResponse }
        candidate = try MemoryCandidate(.object(fields)); producer = try MemoryCandidateJob(review)
        guard candidate.status == .candidate else { throw MemoryFailure.invalidResponse }
    }
}
/// Direct canonical projection: its review references remain valid even when an
/// earlier item deletion erased a shared job payload. Not historical receipts.
public struct MemoryCandidateProjectionPage: Sendable {
    public let conversationID: String
    public let memoryEpoch: Int64
    public let items: [MemoryCandidateProjectionItem]
    public let nextAfterCandidateID: String?
    init(response: Data, trace: String, conversationID: String) throws {
        let value = try candidateEnvelope(response, trace: trace, version: "MEMORY-CANDIDATE-projection@2")
        let fields = try historyObject(value, fields: ["conversation_id", "memory_epoch", "candidates", "next_after_candidate_id"])
        self.conversationID = try historyString(fields["conversation_id"], limit: 256)
        memoryEpoch = try historyInteger(fields["memory_epoch"])
        guard same(self.conversationID, conversationID), case .array(let raw) = fields["candidates"], raw.count <= 50 else { throw MemoryFailure.invalidResponse }
        items = try raw.map(MemoryCandidateProjectionItem.init)
        guard Set(items.map { Data($0.candidate.id.utf8) }).count == items.count,
              items.isEmpty || memoryEpoch > 0 else { throw MemoryFailure.invalidResponse }
        if case .null = fields["next_after_candidate_id"] { nextAfterCandidateID = nil }
        else {
            let next = try candidateItemIdentity(fields["next_after_candidate_id"])
            guard items.count == 50, let last = items.last, same(last.candidate.id, next) else { throw MemoryFailure.invalidResponse }
            nextAfterCandidateID = next
        }
    }
}

func candidateItemIdentity(_ value: StrictJSONValue?) throws -> String {
    let string = try historyString(value, limit: 16384)
    guard string.unicodeScalars.count <= 4096 else { throw MemoryFailure.invalidResponse }
    return string
}
