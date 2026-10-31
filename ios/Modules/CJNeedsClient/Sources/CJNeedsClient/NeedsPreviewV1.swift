import Foundation
import CryptoKit
import CJAPI
import CJMessageHTTP

/// NEEDS-PREVIEW@1 is unconfirmed extraction data from one protected original
/// MESSAGE/RUN. Neither its fields nor hashes grant save/Memory/Trip authority.
public struct NeedsPreviewV1: Sendable {
    public struct Question: Sendable {
        public let field: String
        public let reason: String
        public let originalText: String
        public let chinese: String
        public let english: String
    }
    public let originalUTF8: Data
    public let messageID: String
    public let runID: String
    public let sourceTextUTF8: Data
    public let fields: NeedsSchema.NeedsFields
    public let questions: [Question]
    public let deferredMemoryRequests: [String]
    public let chinese: String
    public let english: String
    public var sourceText: String { String(decoding: sourceTextUTF8, as: UTF8.self) }

    private static let clarification: [String: (String, String)] = [
        "budget_basis/missing_basis": ("预算金额是总计还是每人？", "Is the budget amount total or per person?"),
        "budget_paid/currency_mismatch": ("已付金额与预算的币种口径尚未明确，请核对。", "Confirm the currency basis of the paid amount and budget."),
        "temporary_conditions/unclear_lifetime": ("这条条件只用于本次旅行，还是需要另行确认长期保存？", "Does this condition apply to this trip, or need separate confirmation for long-term memory?"),
        "fixed_items/missing_subject": ("这项固定安排适用于本人、全体还是哪位同伴？", "Does this fixed arrangement apply to you, the party, or a specific companion?")
    ]
    public static func decode(_ bytes: Data, messageID: String, runID: String, sourceTextUTF8: Data) throws -> Self {
        guard !bytes.isEmpty, bytes.count <= 131072, !messageID.isEmpty, !runID.isEmpty,
              String(data: sourceTextUTF8, encoding: .utf8) != nil else { throw NeedsFailure.invalidResponse }
        let line = bytes.last == 10 ? Data(bytes.dropLast()) : bytes
        guard !line.contains(10) else { throw NeedsFailure.invalidResponse }
        let integers = try validateUnambiguousJSON(line)
        let node = try JSONSerialization.jsonObject(with: line)
        var nodes = 0
        func bounds(_ value: Any, depth: Int) throws {
            nodes += 1
            guard nodes <= 16384, depth < 24, !(value is NSNull) else { throw NeedsFailure.invalidResponse }
            if let fields = value as? [String: Any] {
                nodes += fields.count
                for value in fields.values { try bounds(value, depth: depth + 1) }
            } else if let values = value as? [Any] {
                for value in values { try bounds(value, depth: depth + 1) }
            }
        }
        try bounds(node, depth: 0)
        func object(_ value: Any, keys: String) throws -> [String: Any] {
            guard let result = value as? [String: Any], Set(result.keys) == Set(keys.split(separator: " ").map(String.init)) else {
                throw NeedsFailure.invalidResponse
            }
            return result
        }
        func text(_ value: Any?) throws -> String {
            guard let result = value as? String else { throw NeedsFailure.invalidResponse }
            return result
        }
        let root = try object(node, keys: "version data_origin confirmation source_kind source fields unresolved questions deferred_memory_requests text_zh text_en")
        guard try text(root["version"]) == "NEEDS-preview.1", try text(root["data_origin"]) == "synthetic",
              try text(root["confirmation"]) == "unconfirmed", try text(root["source_kind"]) == "unconfirmed_extraction" else {
            throw NeedsFailure.invalidResponse
        }
        let source = try object(root["source"]!, keys: "message_id run_id text_utf8_base64 text_sha256")
        let base64 = try text(source["text_utf8_base64"])
        let digest = SHA256.hash(data: sourceTextUTF8).map { String(format: "%02x", $0) }.joined()
        guard try same(text(source["message_id"]), messageID), try same(text(source["run_id"]), runID),
              let original = Data(base64Encoded: base64), original.base64EncodedString() == base64,
              original == sourceTextUTF8, try same(text(source["text_sha256"]), digest) else { throw NeedsFailure.invalidResponse }
        let fieldsBytes = try JSONSerialization.data(withJSONObject: root["fields"]!)
        let fields = try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: fieldsBytes)
        try validateFields(fields, complete: true)
        if case .NeedsPartySizeObservationKnown(let value) = fields.party_size {
            guard integers[["fields", "party_size", "value"]] == Int64(value.value) else { throw NeedsFailure.invalidResponse }
        }
        guard let unresolved = root["unresolved"] as? [Any], unresolved.count <= 8,
              let wireQuestions = root["questions"] as? [Any], wireQuestions.count == unresolved.count,
              let deferred = root["deferred_memory_requests"] as? [String], deferred.count <= 8 else { throw NeedsFailure.invalidResponse }
        func fragment(_ value: String) throws {
            guard validText(value), original.range(of: Data(value.utf8)) != nil else { throw NeedsFailure.invalidResponse }
        }
        let questions = try zip(unresolved, wireQuestions).map { item, supplied -> Question in
            let item = try object(item, keys: "field reason original_text")
            let field = try text(item["field"]), reason = try text(item["reason"]), originalText = try text(item["original_text"])
            try fragment(originalText)
            guard let pair = clarification[field + "/" + reason] else { throw NeedsFailure.invalidResponse }
            if field == "budget_basis", reason == "missing_basis", NeedsObservationInput(fields.budget_basis).state == .known {
                throw NeedsFailure.invalidResponse
            }
            let question = try object(supplied, keys: "field reason text_zh text_en")
            guard try same(text(question["field"]), field), try same(text(question["reason"]), reason),
                  try same(text(question["text_zh"]), pair.0), try same(text(question["text_en"]), pair.1) else { throw NeedsFailure.invalidResponse }
            return Question(field: field, reason: reason, originalText: originalText, chinese: pair.0, english: pair.1)
        }
        for request in deferred { try fragment(request) }
        let zh = "请核对提取值；这些改动尚未保存到本次需求或长期记忆。"
        let en = "Check the extracted values. These changes have not been saved to your trip requirements or long-term memory."
        guard try same(text(root["text_zh"]), zh), try same(text(root["text_en"]), en) else { throw NeedsFailure.invalidResponse }
        return Self(originalUTF8: bytes, messageID: messageID, runID: runID, sourceTextUTF8: original,
                    fields: fields, questions: questions, deferredMemoryRequests: deferred, chinese: zh, english: en)
    }
}
