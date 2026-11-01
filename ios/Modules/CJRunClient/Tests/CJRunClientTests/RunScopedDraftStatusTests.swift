import Foundation
import Testing
import CJMessageHTTP
@testable import CJRunClient

struct RunScopedDraftStatusTests {
    func examples() throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        return try #require(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("contracts/message/edit-result-examples.1.json"))) as? [String: Any])
    }
    func raw(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) }
    func statuses(_ key: String = "read_positive") throws -> [[String: Any]] {
        let rows = try #require(examples()[key] as? [[String: Any]])
        return try rows.filter { $0["schema"] as? String == "RunDraftStatus6" }.map { try #require($0["value"] as? [String: Any]) }
    }
    func reference(_ value: [String: Any]) throws -> MessageEditReference {
        try MessageEditReference.decodeResponseReference(raw(value), maximumBytes: 65536)
    }
    @Test func frozenKindsStayDistinctFromAProposalAndRetainBilingualMeaning() throws {
        let rows = try statuses(); #expect(rows.count == 2)
        for value in rows {
            let ref = try reference(value), status = try decodeScopedDraftStatus(raw(value), reference: ref).0
            #expect(status.draftOutcome.rawValue == value["draft_outcome"] as? String)
            #expect(status.scopedResult?.messageID == ref.messageID && status.scopedResult?.runID == ref.runID)
            #expect(status.runStatus == .completed && status.budgetStage == .none)
            #expect(RunDraftReadState.loadedScoped(status).label(.chinese).contains("尚未修改正式行程"))
        }
        for value in try statuses("read_negative") {
            let ref = try reference(value)
            #expect(throws: (any Error).self) { try decodeScopedDraftStatus(raw(value), reference: ref) }
        }
    }
    @Test(arguments: ["missingPointer", "oldOutcome", "wrongKind", "nonterminal", "budgetDenied"])
    func semanticContradictionsNeverBecomeRecordedSuccess(change: String) throws {
        var value = try #require(statuses().first); let ref = try reference(value)
        switch change {
        case "missingPointer": value["scoped_result"] = NSNull()
        case "oldOutcome": value["draft_outcome"] = "published"
        case "wrongKind":
            var pointer = try #require(value["scoped_result"] as? [String: Any]); pointer["kind"] = "expansion_required"; value["scoped_result"] = pointer
        case "nonterminal": value["run_status"] = "running"
        default: value["budget_exhausted_stage"] = "draft"
        }
        #expect(throws: (any Error).self) { try decodeScopedDraftStatus(raw(value), reference: ref) }
    }
    @Test func oldVersionFiveRemainsClosedToTheNewOutcomes() throws {
        var value = try #require(statuses().first); let ref = try reference(value)
        #expect(throws: (any Error).self) { try decodeEditDraftStatus(raw(value), reference: ref) }
        value["version"] = "RUN-draft-status.5"; value.removeValue(forKey: "scoped_result")
        #expect(throws: (any Error).self) { try decodeEditDraftStatus(raw(value), reference: ref) }
    }
    @Test func ordinaryOutcomesInVersionSixRequireTheExplicitNullPointer() throws {
        var value = try #require(statuses().first); let ref = try reference(value)
        value["draft_outcome"] = "published"; value["scoped_result"] = NSNull()
        let status = try decodeScopedDraftStatus(raw(value), reference: ref).0
        #expect(status.scopedResult == nil && status.draftOutcome.rawValue == "published")
        value["run_status"] = "running"; value["draft_outcome"] = "not_recorded"
        #expect(try decodeScopedDraftStatus(raw(value), reference: ref).0.scopedResult == nil)
        value.removeValue(forKey: "scoped_result")
        #expect(throws: (any Error).self) { try decodeScopedDraftStatus(raw(value), reference: ref) }
    }
    @Test(arguments: ["true", "1.0", "1e0", "9223372036854775808", "null"])
    func sourceAndRunIntegerLexemesAreNotCoerced(token: String) throws {
        let value = try #require(statuses().first), ref = try reference(value)
        let bytes = Data(String(decoding: try raw(value), as: UTF8.self).replacingOccurrences(of: "\"message_sequence\":1", with: "\"message_sequence\":" + token).utf8)
        #expect(throws: (any Error).self) { try decodeScopedDraftStatus(bytes, reference: ref) }
    }
}
