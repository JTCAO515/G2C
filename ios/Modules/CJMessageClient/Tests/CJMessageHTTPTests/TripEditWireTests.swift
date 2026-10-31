import Foundation
import Testing
import CryptoKit
@testable import CJMessageHTTP

struct TripEditWireTests {
    let trace = "00000000-0000-4000-8000-000000000337"
    func examples() throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        return try #require(JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("contracts/message/edit-examples.1.json"))) as? [String: Any])
    }
    func raw(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) }
    func original() throws -> OriginalTripEdit {
        let rows = try #require(examples()["positive"] as? [[String: Any]])
        return try OriginalTripEdit(raw: raw(rows[1]), maximumBytes: 16384)
    }
    func accepted(_ original: OriginalTripEdit, change: (inout [String: Any]) -> Void = { _ in }) throws -> Data {
        let hash = SHA256.hash(data: original.originalUTF8).map { String(format: "%02x", $0) }.joined()
        let receipt: [String: Any] = ["message_id": original.messageID, "conversation_id": original.head.conversation_id,
            "generation": original.head.generation, "sequence": original.head.last_sequence + 1, "run_id": "run-original", "input_sha256": hash]
        var reference = receipt
        reference.merge(["version": "MESSAGE-edit-reference.1", "message_version": "MESSAGE-send.4",
            "modification_intent": original.intent.rawValue, "trip_context": original.trip.object,
            "resolved_item_ids": original.trip.itemIDs, "content_version": "structured.2",
            "namespace": ["kind": "travel", "id": original.namespace.id, "version": original.namespace.expectedVersion],
            "needs_reference": original.needs.map { ["id": $0.id, "expected_version": $0.expectedVersion] as Any } ?? NSNull(), "selection_epoch": 1], uniquingKeysWith: { _, b in b })
        var value: [String: Any] = ["request_id": trace, "version": "MESSAGE-accept.4", "receipt": receipt, "reference": reference]
        change(&value); return try raw(value)
    }
    @Test func frozenPositiveAndNegativeCommandsKeepOriginalBytes() throws {
        let examples = try examples()
        let positives = try #require(examples["positive"] as? [[String: Any]])
        let negatives = try #require(examples["negative"] as? [[String: Any]])
        #expect(positives.count == 3 && negatives.count == 8)
        for input in positives {
            let bytes = Data(" \n".utf8) + (try raw(input)) + Data("\t".utf8)
            let original = try OriginalTripEdit(raw: bytes, maximumBytes: 16384)
            #expect(original.originalUTF8 == bytes && original.namespace.id == String(repeating: "b", count: 32))
            #expect(original.trip.id == "formal-trip" && original.trip.expectedVersion == 3)
            #expect(NSDictionary(dictionary: original.trip.object).isEqual(to: try #require(input["trip_context"] as? [String: Any])))
            #expect(throws: (any Error).self) { try OriginalTripDiscussion(raw: bytes, maximumBytes: 16384) }
            #expect(throws: (any Error).self) { try OriginalTravelMessageSend(raw: bytes, maximumBytes: 16384) }
        }
        for row in negatives {
            let input = try #require(row["input"] as? [String: Any])
            let name = try #require(row["name"] as? String)
            #expect(throws: (any Error).self, Comment(rawValue: name)) {
                try OriginalTripEdit(raw: raw(input), maximumBytes: 16384)
            }
        }
    }
    @Test(arguments: ["true", "1.0", "1e0", "0", "-1", "9223372036854775808", "null", "\"3\""])
    func nestedVersionsNeverCoerce(token: String) throws {
        let original = try original()
        let text = String(decoding: original.originalUTF8, as: UTF8.self).replacingOccurrences(of: "\"expected_version\":3", with: "\"expected_version\":" + token)
        #expect(throws: (any Error).self) { try OriginalTripEdit(raw: Data(text.utf8), maximumBytes: 16384) }
    }
    @Test func unknownDuplicateAndBlankFieldsFailClosed() throws {
        let original = try original(); let bytes = original.originalUTF8
        let duplicate = Data("{\"version\":\"MESSAGE-send.4\",".utf8) + bytes.dropFirst()
        #expect(throws: (any Error).self) { try OriginalTripEdit(raw: duplicate, maximumBytes: 16384) }
        var value = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        value["owner"] = "caller"
        #expect(throws: (any Error).self) { try OriginalTripEdit(raw: raw(value), maximumBytes: 16384) }
        value.removeValue(forKey: "owner"); value["message_id"] = " "
        #expect(throws: (any Error).self) { try OriginalTripEdit(raw: raw(value), maximumBytes: 16384) }
        #expect(throws: (any Error).self) { try OriginalTripEdit(raw: bytes, maximumBytes: bytes.count - 1) }
    }
    @Test func exactAcceptanceAndOriginalReferenceAreRetained() throws {
        let original = try original(); let bytes = try accepted(original)
        let value = try TripEditAcceptance(raw: bytes, maximumBytes: 16384, requestID: trace, original: original)
        #expect(value.reference.trip == original.trip && value.reference.namespace == original.namespace)
        #expect(value.reference.needs == original.needs && value.reference.intent == .proposeScopedEdit)
        #expect(value.reference.resolvedItemIDs == ["item-a", "item-b"] && value.reference.selectionEpoch == 1)
        #expect(try MessageEditReference.decodeResponseReference(bytes, maximumBytes: 16384) == value.reference)
        #expect(throws: (any Error).self) { try MessageTripReference.decodeResponseReference(bytes, maximumBytes: 16384) }
    }
    @Test(arguments: ["trip_context", "namespace", "needs_reference", "input_sha256", "resolved_item_ids", "message_id"])
    func changedOriginalAssociationIsRefused(field: String) throws {
        let original = try original()
        let bytes = try accepted(original) { root in
            var reference = root["reference"] as! [String: Any]
            switch field {
            case "trip_context": var v = reference[field] as! [String: Any]; v["content_sha256"] = String(repeating: "b", count: 64); reference[field] = v
            case "namespace": reference[field] = ["kind": "travel", "id": String(repeating: "c", count: 32), "version": 1]
            case "needs_reference": reference[field] = ["id": "needs", "expected_version": 3]
            case "input_sha256": reference[field] = String(repeating: "b", count: 64)
            case "resolved_item_ids": reference[field] = ["item-b", "item-a"]
            default: reference[field] = "another-original"
            }
            root["reference"] = reference
        }
        #expect(throws: (any Error).self) { try TripEditAcceptance(raw: bytes, maximumBytes: 16384, requestID: trace, original: original) }
    }
    @Test func statusCannotTurnNullOrDifferentVersionIntoAcceptance() throws {
        let original = try original()
        var value = try #require(JSONSerialization.jsonObject(with: accepted(original)) as? [String: Any])
        value["version"] = "MESSAGE-send-status.4"
        value["head"] = ["conversation_id": "chat", "generation": "g", "last_sequence": 1]
        let status = try TripEditStatus(raw: raw(value), maximumBytes: 16384, requestID: trace, conversationID: "chat", original: original)
        #expect(status.head?.last_sequence == 1 && status.acceptedUTF8 != nil)
        let roundtrip = try TripEditAcceptance(raw: #require(status.acceptedUTF8), maximumBytes: 16384, requestID: trace, original: original)
        #expect(roundtrip.reference == status.acceptance?.reference)
        value["receipt"] = NSNull()
        #expect(throws: (any Error).self) { try TripEditStatus(raw: raw(value), maximumBytes: 16384, requestID: trace, conversationID: "chat", original: original) }
        value["reference"] = NSNull()
        let missing = try TripEditStatus(raw: raw(value), maximumBytes: 16384, requestID: trace, conversationID: "chat", original: original)
        #expect(missing.acceptance == nil && missing.acceptedUTF8 == nil)
        value["version"] = "MESSAGE-send-status.3"
        #expect(throws: (any Error).self) { try TripEditStatus(raw: raw(value), maximumBytes: 16384, requestID: trace, conversationID: "chat", original: original) }
    }
    @Test func referenceEqualityUsesOriginalIdentityBytes() throws {
        let original = try original()
        let a = try MessageEditReference.decodeResponseReference(accepted(original) { value in
            var ref = value["reference"] as! [String: Any]; ref["message_id"] = "é"; value["reference"] = ref
        }, maximumBytes: 16384)
        let b = try MessageEditReference.decodeResponseReference(accepted(original) { value in
            var ref = value["reference"] as! [String: Any]; ref["message_id"] = "e\u{301}"; value["reference"] = ref
        }, maximumBytes: 16384)
        #expect(a != b)
    }
}
