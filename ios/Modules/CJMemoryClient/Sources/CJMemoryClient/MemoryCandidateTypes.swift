import Foundation
import CJAPI
import CJStrictJSON

/// Data returned by the protected producer discovery, never an extraction grant.
/// Equality uses original UTF8 rather than Swift's canonical Unicode equivalence.
public struct MemoryCandidateJob: Sendable, Hashable {
    public let jobID: String
    public let attemptID: String
    init(_ value: StrictJSONValue) throws {
        let fields = try historyObject(value, fields: ["job_id", "attempt_id"])
        jobID = try candidateIdentity(fields["job_id"])
        attemptID = try candidateIdentity(fields["attempt_id"])
    }
    public static func == (lhs: Self, rhs: Self) -> Bool {
        same(lhs.jobID, rhs.jobID) && same(lhs.attemptID, rhs.attemptID)
    }
    public func hash(into hasher: inout Hasher) {
        hasher.combine(Data(jobID.utf8)); hasher.combine(Data(attemptID.utf8))
    }
}

public struct MemoryCandidateJobPage: Sendable {
    public let conversationID: String
    public let jobs: [MemoryCandidateJob]
    public let nextAfterJobID: String?
    init(response: Data, trace: String, conversationID expected: String) throws {
        let result = try candidateEnvelope(response, trace: trace, version: "MEMORY-CANDIDATE-JOBS@1")
        let fields = try historyObject(result, fields: ["conversation_id", "jobs", "next_after_job_id"])
        conversationID = try historyString(fields["conversation_id"], limit: 256)
        guard same(conversationID, expected), case .array(let values) = fields["jobs"], values.count <= 50 else { throw MemoryFailure.invalidResponse }
        jobs = try values.map(MemoryCandidateJob.init)
        guard Set(jobs).count == jobs.count else { throw MemoryFailure.invalidResponse }
        if case .null = fields["next_after_job_id"] { nextAfterJobID = nil }
        else {
            let next = try candidateIdentity(fields["next_after_job_id"])
            guard jobs.count == 50, let last = jobs.last, same(next, last.jobID) else { throw MemoryFailure.invalidResponse }
            nextAfterJobID = next
        }
    }
}

/// Current Memory projection associated with an actual original producer.
/// The client separately binds this data to its session/read/selection lifetime.
public struct MemoryCandidate: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let id: String
    public let version: Int64
    public let status: Components.Schemas.MemoryItemV2.statusPayload
    public let subject: String
    public let slot: String
    public let kind: Components.Schemas.MemoryManualSaveCommand.kindPayload
    public let text: String
    public let occurredAt: String
    public let extent: Components.Schemas.MemoryManualSaveCommand.extentPayload
    public let travel: MemoryTravelSelection?
    public var description: String { "<private current memory candidate projection>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
    init(_ value: StrictJSONValue) throws {
        let fields = try historyObject(value, fields: ["candidate_id", "version", "status", "subject", "slot", "kind", "text", "extent", "occurred_at", "context"])
        id = try historyString(fields["candidate_id"], limit: 4096)
        version = try historyInteger(fields["version"])
        guard version > 0,
              let status = Components.Schemas.MemoryItemV2.statusPayload(rawValue: try historyString(fields["status"], limit: 32)),
              let kind = Components.Schemas.MemoryManualSaveCommand.kindPayload(rawValue: try historyString(fields["kind"], limit: 32)),
              let extent = Components.Schemas.MemoryManualSaveCommand.extentPayload(rawValue: try historyString(fields["extent"], limit: 32)),
              kind != .inference || status != .active else { throw MemoryFailure.invalidResponse }
        self.status = status; self.kind = kind; self.extent = extent
        subject = try candidateText(fields["subject"])
        slot = try candidateText(fields["slot"])
        text = try candidateText(fields["text"])
        occurredAt = try candidateText(fields["occurred_at"])
        if extent == .long_term {
            guard case .null = fields["context"] else { throw MemoryFailure.invalidResponse }
            travel = nil
        } else {
            guard let context = fields["context"] else { throw MemoryFailure.invalidResponse }
            let selection = try historyObject(context, fields: ["kind", "id", "expected_version"])
            guard try historyString(selection["kind"], limit: 16) == "travel" else { throw MemoryFailure.invalidResponse }
            let id = try historyString(selection["id"], limit: 32)
            let version = try historyInteger(selection["expected_version"])
            do { travel = try MemoryTravelSelection(id: id, expectedVersion: version) }
            catch { throw MemoryFailure.invalidResponse }
        }
    }
}

public struct MemoryCandidatePage: Sendable {
    public let producer: MemoryCandidateJob
    public let memoryEpoch: Int64
    public let candidates: [MemoryCandidate]
    init(response: Data, trace: String, producer expected: MemoryCandidateJob) throws {
        let result = try candidateEnvelope(response, trace: trace, version: "MEMORY-CANDIDATE-list@1")
        let fields = try historyObject(result, fields: ["job_id", "attempt_id", "memory_epoch", "candidates"])
        producer = try MemoryCandidateJob(.object(["job_id": fields["job_id"]!, "attempt_id": fields["attempt_id"]!]))
        memoryEpoch = try historyInteger(fields["memory_epoch"])
        guard producer == expected, memoryEpoch > 0,
              case .array(let values) = fields["candidates"], values.count <= 100 else { throw MemoryFailure.invalidResponse }
        candidates = try values.map(MemoryCandidate.init)
        guard Set(candidates.map { Data($0.id.utf8) }).count == candidates.count else { throw MemoryFailure.invalidResponse }
    }
}

func candidateIdentity(_ value: StrictJSONValue?) throws -> String {
    let string = try historyString(value, limit: 1024)
    guard string.unicodeScalars.count <= 256 else { throw MemoryFailure.invalidResponse }
    return string
}
func candidateText(_ value: StrictJSONValue?) throws -> String {
    let string = try historyString(value, limit: 16384)
    guard string.unicodeScalars.count <= 4096 else { throw MemoryFailure.invalidResponse }
    return string
}
func candidateEnvelope(_ bytes: Data, trace: String, version: String) throws -> StrictJSONValue {
    guard !bytes.isEmpty, bytes.count <= 524288, UUID(uuidString: trace) != nil else { throw MemoryFailure.invalidResponse }
    var parser = StrictMemoryJSON(bytes: Array(bytes))
    let fields = try historyObject(parser.document(), fields: ["version", "request_id", "result"])
    guard try historyString(fields["version"], limit: 64) == version,
          same(try historyString(fields["request_id"], limit: 64), trace), let result = fields["result"] else { throw MemoryFailure.invalidResponse }
    return result
}
