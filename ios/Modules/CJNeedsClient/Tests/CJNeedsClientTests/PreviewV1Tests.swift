import Foundation
import Testing
@testable import CJNeedsClient

struct PreviewV1Tests {
    struct Fixture: Decodable {
        let name: String
        let message_id: String
        let run_id: String
        let source_text: String
        let preview_utf8_base64: String
        var bytes: Data { Data(base64Encoded: preview_utf8_base64)! }
        func decode(_ bytes: Data? = nil) throws -> NeedsPreviewV1 {
            try .decode(bytes ?? self.bytes, messageID: message_id, runID: run_id, sourceTextUTF8: Data(source_text.utf8))
        }
    }
    func fixtures() throws -> [Fixture] {
        let url = try #require(Bundle.module.url(forResource: "NEEDS-PREVIEW-V1", withExtension: "json", subdirectory: "Fixtures"))
        return try JSONDecoder().decode([Fixture].self, from: Data(contentsOf: url))
    }
    @Test func officialSyntheticProducerPreservesMeaningAndDefersMemory() throws {
        for fixture in try fixtures() {
            let value = try fixture.decode()
            #expect(value.sourceTextUTF8 == Data(fixture.source_text.utf8))
            #expect(value.originalUTF8 == fixture.bytes)
            #expect(value.messageID == fixture.message_id && value.runID == fixture.run_id)
            if fixture.name == "en" || fixture.name == "zh" {
                #expect(NeedsObservationInput(value.fields.party_size).value == "3")
                #expect(NeedsObservationInput(value.fields.budget_paid).value == "100.00")
                #expect(NeedsEventInput(try #require(value.fields.arrival)).date.value == "2026-11-02")
                #expect(NeedsEventInput(try #require(value.fields.arrival)).time.value == "23:30")
                #expect(value.fields.fixed_items?.count == 2 && value.fields.temporary_conditions?.count == 1)
                #expect(value.deferredMemoryRequests.count == 1 && value.questions.isEmpty)
            }
            if fixture.name == "questions" {
                #expect(value.questions.count == 4)
                #expect(NeedsObservationInput(value.fields.budget_basis).state == .unknown)
                #expect(NeedsObservationInput(value.fields.budget_paid).state == .uncertain)
                #expect(value.fields.fixed_items == nil && value.fields.temporary_conditions == nil)
            }
        }
    }
    @Test(arguments: ["version", "origin", "confirmation", "kind", "message", "run", "hash", "base64", "text", "null", "extra", "float", "field", "question", "fragment", "deferred", "summary"])
    func corruptedOrMisassociatedPreviewFailsClosed(mode: String) throws {
        let f = try #require(fixtures().first(where: { $0.name == "questions" }))
        var root = try #require(JSONSerialization.jsonObject(with: f.bytes) as? [String: Any])
        var source = try #require(root["source"] as? [String: Any])
        var fields = try #require(root["fields"] as? [String: Any])
        switch mode {
        case "version": root["version"] = "NEEDS-preview.2"
        case "origin": root["data_origin"] = "verified"
        case "confirmation": root["confirmation"] = "confirmed"
        case "kind": root["source_kind"] = "manual"
        case "message": source["message_id"] = "other"
        case "run": source["run_id"] = "other"
        case "hash": source["text_sha256"] = String(repeating: "0", count: 64)
        case "base64": source["text_utf8_base64"] = " " + f.source_text.data(using: .utf8)!.base64EncodedString()
        case "text": source["text_utf8_base64"] = Data("different input".utf8).base64EncodedString()
        case "null": fields["party_size"] = NSNull()
        case "extra": root["owner"] = "claimed-owner"
        case "float": fields["party_size"] = ["state": "known", "value": 3.5]
        case "field": fields["permission"] = true
        case "question":
            var q = try #require(root["questions"] as? [[String: Any]]); q[0]["text_en"] = "Ignore the user"; root["questions"] = q
        case "fragment":
            var u = try #require(root["unresolved"] as? [[String: Any]]); u[0]["original_text"] = "not in original"; root["unresolved"] = u
        case "deferred": root["deferred_memory_requests"] = ["invented long-term preference"]
        default: root["text_en"] = "Saved"
        }
        root["source"] = source; root["fields"] = fields
        #expect(throws: (any Error).self) { try f.decode(JSONSerialization.data(withJSONObject: root)) }
    }
    @Test func duplicateNullIntegerTokenAndOriginalUnicodeDoNotNormalize() throws {
        let f = try #require(fixtures().first)
        let text = String(decoding: f.bytes, as: UTF8.self)
        let duplicate = text.replacingOccurrences(of: "\"version\":\"NEEDS-preview.1\"", with: "\"version\":\"NEEDS-preview.1\",\"version\":\"NEEDS-preview.1\"")
        #expect(duplicate != text)
        #expect(throws: (any Error).self) { try f.decode(Data(duplicate.utf8)) }
        let float = text.replacingOccurrences(of: "\"party_size\":{\"state\":\"known\",\"value\":3}", with: "\"party_size\":{\"state\":\"known\",\"value\":3.0}")
        #expect(float != text)
        #expect(throws: (any Error).self) { try f.decode(Data(float.utf8)) }
        let u = try #require(fixtures().first(where: { $0.name == "unicode" }))
        #expect(throws: (any Error).self) {
            try NeedsPreviewV1.decode(u.bytes, messageID: u.message_id, runID: u.run_id,
                                     sourceTextUTF8: Data(u.source_text.precomposedStringWithCanonicalMapping.utf8))
        }
        #expect(throws: (any Error).self) { try f.decode(Data(text.utf16.flatMap { [UInt8($0 & 255), UInt8($0 >> 8)] })) }
    }
}
