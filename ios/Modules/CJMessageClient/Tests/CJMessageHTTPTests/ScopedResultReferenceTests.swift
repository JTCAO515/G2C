import Foundation
import Testing
@testable import CJMessageHTTP

/// Frozen B wire examples are metadata only, never accepted source authority.
struct ScopedResultReferenceTests {
    func examples() throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        return try #require(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("contracts/message/edit-result-examples.1.json"))) as? [String: Any])
    }
    func raw(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) }
    func status() throws -> [String: Any] {
        let rows = try #require(examples()["read_positive"] as? [[String: Any]])
        return try #require(rows.first { $0["schema"] as? String == "RunDraftStatus6" }?["value"] as? [String: Any])
    }
    func reference(_ value: [String: Any]) throws -> MessageEditReference {
        try MessageEditReference.decodeResponseReference(raw(value), maximumBytes: 65536)
    }
    @Test func bothFrozenResultKindsBindTheExactOriginal() throws {
        let rows = try #require(examples()["read_positive"] as? [[String: Any]])
        let statuses = try rows.filter { $0["schema"] as? String == "RunDraftStatus6" }.map { try #require($0["value"] as? [String: Any]) }
        #expect(statuses.count == 2)
        for value in statuses {
            let original = try reference(value)
            let decoded = try RunScopedResultReference.decodeResponseReference(raw(value), maximumBytes: 65536, matching: original)
            let result = try #require(decoded)
            #expect(result.messageID.utf8.elementsEqual(original.messageID.utf8))
            #expect(result.runID.utf8.elementsEqual(original.runID.utf8))
            #expect(result.inputSHA256 == original.inputSHA256)
            #expect(result.kind.rawValue == value["draft_outcome"] as? String)
        }
    }
    @Test func frozenNegativePointersFailWithoutInventingAProposal() throws {
        var value = try status(), ref = try #require(value["reference"] as? [String: Any])
        ref["message_id"] = "message-original"; ref["run_id"] = "run-original"; ref["input_sha256"] = String(repeating: "a", count: 64)
        value["reference"] = ref
        let original = try reference(value)
        for pointer in try #require(examples()["negative"] as? [[String: Any]]) {
            value["scoped_result"] = pointer
            #expect(throws: MessageHTTPFailure.invalidResponse) { try RunScopedResultReference.decodeResponseReference(raw(value), maximumBytes: 65536, matching: original) }
        }
    }
    @Test(arguments: ["message_id", "run_id", "input_sha256", "version", "kind", "result_id", "owner"])
    func wrongAssociationVersionKindOrExtraFieldIsNotAccepted(field: String) throws {
        var value = try status(); let original = try reference(value)
        var pointer = try #require(value["scoped_result"] as? [String: Any])
        pointer[field] = field == "input_sha256" ? String(repeating: "b", count: 64) : "foreign/or/unsupported"
        value["scoped_result"] = pointer
        #expect(throws: MessageHTTPFailure.invalidResponse) { try RunScopedResultReference.decodeResponseReference(raw(value), maximumBytes: 65536, matching: original) }
    }
    @Test func missingDuplicateAndOversizedMetadataNeverBecomeEmptySuccess() throws {
        var value = try status(); let original = try reference(value)
        let bytes = try raw(value)
        #expect(throws: (any Error).self) { try RunScopedResultReference.decodeResponseReference(bytes, maximumBytes: bytes.count - 1, matching: original) }
        let duplicate = Data("{\"scoped_result\":null,".utf8) + bytes.dropFirst()
        #expect(throws: (any Error).self) { try RunScopedResultReference.decodeResponseReference(duplicate, maximumBytes: 65536, matching: original) }
        value.removeValue(forKey: "scoped_result")
        #expect(throws: MessageHTTPFailure.invalidResponse) { try RunScopedResultReference.decodeResponseReference(raw(value), maximumBytes: 65536, matching: original) }
        value["scoped_result"] = NSNull()
        #expect(try RunScopedResultReference.decodeResponseReference(raw(value), maximumBytes: 65536, matching: original) == nil)
    }
    @Test func discussionIntentCannotCarryAResult() throws {
        var value = try status(), ref = try #require(value["reference"] as? [String: Any])
        ref["modification_intent"] = "none"; ref["needs_reference"] = NSNull(); value["reference"] = ref
        let original = try reference(value)
        #expect(throws: MessageHTTPFailure.invalidResponse) { try RunScopedResultReference.decodeResponseReference(raw(value), maximumBytes: 65536, matching: original) }
    }
}
