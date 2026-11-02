import Foundation
import Testing
@testable import CJMemoryClient

private let candidateTrace = "11111111-1111-4111-8111-111111111460"
private func candidateWire(_ version: String, _ result: [String: Any]) throws -> Data {
    try JSONSerialization.data(withJSONObject: ["version": version, "request_id": candidateTrace, "result": result], options: [.sortedKeys, .withoutEscapingSlashes])
}
private func candidateProducer(_ job: String = "job-真实", _ attempt: String = "attempt-原始") throws -> MemoryCandidateJob {
    try MemoryCandidateJob(.object(["job_id": .string(job), "attempt_id": .string(attempt)]))
}
private func candidateItem() -> [String: Any] {
    ["candidate_id": "history-item-v1:偏好", "version": 1, "status": "candidate", "subject": "traveler", "slot": "food",
     "kind": "inference", "text": "不吃辣 / no spicy food", "extent": "long_term", "occurred_at": "date unknown", "context": NSNull()]
}
@Test func discoveryPreservesOriginalUnicodeReferencesAndDoesNotNormalizeIDs() throws {
    let composed = "é", decomposed = "e\u{301}"
    let raw = try candidateWire("MEMORY-CANDIDATE-JOBS@1", ["conversation_id": "会话甲", "jobs": [
        ["job_id": composed, "attempt_id": "原attempt"], ["job_id": decomposed, "attempt_id": "原attempt"]], "next_after_job_id": NSNull()])
    let page = try MemoryCandidateJobPage(response: raw, trace: candidateTrace, conversationID: "会话甲")
    #expect(page.jobs.count == 2 && Set(page.jobs).count == 2)
    #expect(Data(page.jobs[0].jobID.utf8) != Data(page.jobs[1].jobID.utf8))
    #expect(page.nextAfterJobID == nil)
    let maxScalarJob = String(repeating: "𠀀", count: 256)
    _ = try candidateProducer(maxScalarJob)
    #expect(throws: MemoryFailure.invalidResponse) { try candidateProducer(maxScalarJob + "a") }
    #expect(throws: MemoryFailure.invalidResponse) { try candidateProducer(String(repeating: "e\u{301}", count: 129)) }
}
@Test func discoveryUsesTheRealLastReferenceAsBoundedCursor() throws {
    let jobs = (0..<50).map { ["job_id": "job-\($0)", "attempt_id": "attempt"] }
    let page = try MemoryCandidateJobPage(response: candidateWire("MEMORY-CANDIDATE-JOBS@1", ["conversation_id": "chat", "jobs": jobs, "next_after_job_id": "job-49"]), trace: candidateTrace, conversationID: "chat")
    #expect(page.jobs.count == 50 && page.nextAfterJobID == "job-49")
    for next in ["job-48", "", "invented"] {
        #expect(throws: MemoryFailure.invalidResponse) {
            try MemoryCandidateJobPage(response: candidateWire("MEMORY-CANDIDATE-JOBS@1", ["conversation_id": "chat", "jobs": jobs, "next_after_job_id": next]), trace: candidateTrace, conversationID: "chat")
        }
    }
    #expect(throws: MemoryFailure.invalidResponse) {
        try MemoryCandidateJobPage(response: candidateWire("MEMORY-CANDIDATE-JOBS@1", ["conversation_id": "chat", "jobs": Array(jobs.prefix(1)), "next_after_job_id": "job-0"]), trace: candidateTrace, conversationID: "chat")
    }
}
@Test func currentProjectionKeepsUnconfirmedInferenceAndRedactsDebugContent() throws {
    let job = try candidateProducer()
    let response = try candidateWire("MEMORY-CANDIDATE-list@1", ["job_id": job.jobID, "attempt_id": job.attemptID, "memory_epoch": 2, "candidates": [candidateItem()]])
    let page = try MemoryCandidatePage(response: response, trace: candidateTrace, producer: job)
    let item = try #require(page.candidates.first)
    #expect(item.kind == .inference && item.status == .candidate && item.travel == nil)
    #expect(item.text == "不吃辣 / no spicy food")
    #expect(!String(reflecting: item).contains("不吃辣") && Mirror(reflecting: item).children.isEmpty)
    #expect(throws: MemoryFailure.invalidResponse) {
        try MemoryCandidatePage(response: response, trace: candidateTrace, producer: candidateProducer("other-job"))
    }
}
@Test(arguments: ["active-inference", "long-term-context", "missing-current-context", "wrong-travel-kind", "bad-travel-id", "zero-travel-version", "unknown-status", "duplicate-item", "extra-owner", "zero-epoch"])
func candidateBoundaryRejectsInvalidCurrentProjection(change: String) throws {
    let job = try candidateProducer()
    var item = candidateItem()
    var epoch = 2
    switch change {
    case "active-inference": item["status"] = "active"
    case "long-term-context": item["context"] = ["kind": "travel", "id": String(repeating: "a", count: 32), "expected_version": 1]
    case "missing-current-context": item["extent"] = "current"
    case "wrong-travel-kind": item["extent"] = "current"; item["context"] = ["kind": "conversation", "id": String(repeating: "a", count: 32), "expected_version": 1]
    case "bad-travel-id": item["extent"] = "current"; item["context"] = ["kind": "travel", "id": String(repeating: "A", count: 32), "expected_version": 1]
    case "zero-travel-version": item["extent"] = "current"; item["context"] = ["kind": "travel", "id": String(repeating: "a", count: 32), "expected_version": 0]
    case "unknown-status": item["status"] = "complete"
    case "extra-owner": item["owner"] = "other"
    case "zero-epoch": epoch = 0
    default: break
    }
    #expect(throws: MemoryFailure.invalidResponse) {
        try MemoryCandidatePage(response: candidateWire("MEMORY-CANDIDATE-list@1", ["job_id": job.jobID, "attempt_id": job.attemptID, "memory_epoch": epoch, "candidates": change == "duplicate-item" ? [item, item] : [item]]), trace: candidateTrace, producer: job)
    }
}
@Test func travelProjectionIsSelectionDataAndRequiresPositiveOriginalVersion() throws {
    let job = try candidateProducer()
    var item = candidateItem(); item["extent"] = "current"
    item["context"] = ["kind": "travel", "id": String(repeating: "a", count: 32), "expected_version": 3]
    let page = try MemoryCandidatePage(response: candidateWire("MEMORY-CANDIDATE-list@1", ["job_id": job.jobID, "attempt_id": job.attemptID, "memory_epoch": 2, "candidates": [item]]), trace: candidateTrace, producer: job)
    #expect(page.candidates.first?.travel?.expectedVersion == 3)
}
@Test(arguments: ["true", "1.0", "1e0", "9223372036854775808"])
func candidateCountersNeverCoerceBoolFloatOrOverflow(token: String) throws {
    let raw = Data("{\"version\":\"MEMORY-CANDIDATE-list@1\",\"request_id\":\"\(candidateTrace)\",\"result\":{\"job_id\":\"job-真实\",\"attempt_id\":\"attempt-原始\",\"memory_epoch\":\(token),\"candidates\":[]}}".utf8)
    #expect(throws: MemoryFailure.invalidResponse) { try MemoryCandidatePage(response: raw, trace: candidateTrace, producer: candidateProducer()) }
}
@Test func duplicateEnvelopeKeysAndForeignConversationAreNotAnEmptySuccess() throws {
    let duplicate = Data("{\"version\":\"MEMORY-CANDIDATE-JOBS@1\",\"version\":\"MEMORY-CANDIDATE-JOBS@1\",\"request_id\":\"\(candidateTrace)\",\"result\":{\"conversation_id\":\"chat\",\"jobs\":[],\"next_after_job_id\":null}}".utf8)
    #expect(throws: MemoryFailure.invalidResponse) { try MemoryCandidateJobPage(response: duplicate, trace: candidateTrace, conversationID: "chat") }
    let raw = try candidateWire("MEMORY-CANDIDATE-JOBS@1", ["conversation_id": "foreign", "jobs": [], "next_after_job_id": NSNull()])
    #expect(throws: MemoryFailure.invalidResponse) { try MemoryCandidateJobPage(response: raw, trace: candidateTrace, conversationID: "chat") }
    #expect(throws: MemoryFailure.invalidResponse) { try MemoryCandidateJobPage(response: raw, trace: UUID().uuidString, conversationID: "foreign") }
}

private func candidatePage(_ item: [String: Any] = candidateItem()) throws -> MemoryCandidatePage {
    let job = try candidateProducer()
    return try MemoryCandidatePage(response: candidateWire("MEMORY-CANDIDATE-list@1", ["job_id": job.jobID, "attempt_id": job.attemptID, "memory_epoch": 2, "candidates": [item]]), trace: candidateTrace, producer: job)
}
@Test func explicitReviewEncodesOnlyOriginalAssociationAndRejectOmitsEditFields() throws {
    let page = try candidatePage(), id = try #require(page.candidates.first?.id)
    let review = try MemoryCandidateAction(page: page, candidateID: id, review: .confirm(kind: .preference, text: "少辣\n保留原话 \"引号\"", occurredAt: "时间不详", travel: nil))
    let fields = try #require(JSONSerialization.jsonObject(with: review.originalUTF8) as? [String: Any])
    #expect(Set(fields.keys) == ["version", "action_id", "job_id", "attempt_id", "candidate_id", "expected_candidate_version", "expected_memory_epoch", "operation", "kind", "text", "occurred_at", "extent", "context"])
    #expect(fields["context"] is NSNull && fields["extent"] as? String == "long_term")
    #expect(fields["text"] as? String == "少辣\n保留原话 \"引号\"")
    let reject = try MemoryCandidateAction(page: page, candidateID: id, review: .reject)
    let rejected = try #require(JSONSerialization.jsonObject(with: reject.originalUTF8) as? [String: Any])
    #expect(Set(rejected.keys) == ["version", "action_id", "job_id", "attempt_id", "candidate_id", "expected_candidate_version", "expected_memory_epoch", "operation"])
    #expect(rejected["operation"] as? String == "reject")
}
@Test func currentCandidateCannotBecomeLongTermOrSwitchTravelAndInferenceCannotConfirmItself() throws {
    var item = candidateItem(); item["extent"] = "current"
    item["context"] = ["kind": "travel", "id": String(repeating: "a", count: 32), "expected_version": 2]
    let page = try candidatePage(item), id = try #require(page.candidates.first?.id)
    #expect(throws: MemoryFailure.invalidInput) { try MemoryCandidateAction(page: page, candidateID: id, review: .confirm(kind: .preference, text: "少辣", occurredAt: "时间不详", travel: nil)) }
    #expect(throws: MemoryFailure.invalidInput) { try MemoryCandidateAction(page: page, candidateID: id, review: .confirm(kind: .preference, text: "少辣", occurredAt: "时间不详", travel: MemoryTravelSelection(id: String(repeating: "b", count: 32), expectedVersion: 3))) }
    #expect(throws: MemoryFailure.invalidInput) { try MemoryCandidateAction(page: page, candidateID: id, review: .confirm(kind: .inference, text: "少辣", occurredAt: "时间不详", travel: MemoryTravelSelection(id: String(repeating: "a", count: 32), expectedVersion: 3))) }
    let action = try MemoryCandidateAction(page: page, candidateID: id, review: .confirm(kind: .preference, text: "少辣", occurredAt: "时间不详", travel: MemoryTravelSelection(id: String(repeating: "a", count: 32), expectedVersion: 3)))
    let fields = try #require(JSONSerialization.jsonObject(with: action.originalUTF8) as? [String: Any])
    #expect(fields["extent"] as? String == "current")
    #expect((fields["context"] as? [String: Any])?["expected_version"] as? Int == 3)
}
@Test func persistedReviewKeepsExactWhitespaceUnicodeEscapesAndHash() throws {
    let raw = Data("{ \"version\":\"MEMORY-CANDIDATE@1\", \"action_id\":\"原动作\",\"job_id\":\"job-真实\",\"attempt_id\":\"attempt-原始\",\"candidate_id\":\"history-item-v1:偏好\",\"expected_candidate_version\":1,\"expected_memory_epoch\":2,\"operation\":\"confirm\",\"kind\":\"preference\",\"text\":\"\\u4e0d吃辣\",\"extent\":\"long_term\",\"context\":null,\"occurred_at\":\"时间不详\" }".utf8)
    let action = try MemoryCandidateAction(originalUTF8: raw)
    #expect(action.originalUTF8 == raw && action.inputSHA256 == digest(raw))
    var fields = try #require(JSONSerialization.jsonObject(with: raw) as? [String: Any])
    fields["owner"] = "foreign"
    #expect(throws: MemoryFailure.invalidResponse) { try MemoryCandidateAction(originalUTF8: JSONSerialization.data(withJSONObject: fields)) }
}
@Test(arguments: ["active", "withdrawn", "disabled"])
func aCurrentNoncandidateProjectionCannotCreateAnotherReview(status: String) throws {
    var item = candidateItem(); item["kind"] = "preference"; item["status"] = status
    let page = try candidatePage(item)
    #expect(throws: MemoryFailure.invalidInput) { try MemoryCandidateAction(page: page, candidateID: "history-item-v1:偏好", review: .reject) }
}
@Test func historicalReceiptBindsExactOriginalBytesAndCannotClaimAnotherOutcome() throws {
    let page = try candidatePage()
    let action = try MemoryCandidateAction(page: page, candidateID: "history-item-v1:偏好", review: .confirm(kind: .preference, text: "少辣", occurredAt: "时间不详", travel: nil))
    var value: [String: Any] = ["version": "MEMORY-CANDIDATE-result@1", "action_id": action.actionID, "candidate_id": action.candidateID, "input_sha256": action.inputSHA256,
        "receipt": ["item_id": action.candidateID, "version": 2, "status": "active", "source_id": "candidate-confirm-v1:actual", "source_version": 1]]
    func parse(_ fields: [String: Any]) throws -> MemoryCandidateReceipt {
        let raw = try JSONSerialization.data(withJSONObject: fields)
        var parser = StrictMemoryJSON(bytes: Array(raw)); return try MemoryCandidateReceipt(parser.document(), original: action)
    }
    let receipt = try parse(value)
    #expect(receipt.active && receipt.itemVersion == 2 && receipt.sourceVersion == 1)
    value["input_sha256"] = String(repeating: "0", count: 64)
    #expect(throws: MemoryFailure.invalidResponse) { try parse(value) }
    value["input_sha256"] = action.inputSHA256
    value["receipt"] = ["item_id": action.candidateID, "version": 2, "status": "rejected"]
    #expect(throws: MemoryFailure.invalidResponse) { try parse(value) }
}
