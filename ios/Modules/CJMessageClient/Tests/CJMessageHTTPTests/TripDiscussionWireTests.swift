import Foundation
import Testing
import CryptoKit
@testable import CJMessageHTTP

struct TripDiscussionWireTests {
    let selection: [String: Any] = ["id": "trip-a", "expected_version": Int64(9), "day": ["date": "2026-10-31", "timezone": "Asia/Shanghai"], "item_id": "item-a"]
    func original(_ change: (inout [String: Any]) -> Void = { _ in }) throws -> Data {
        var value: [String: Any] = ["version": "MESSAGE-send.3", "conversation_id": "chat", "message_id": "m1", "text": " e\u{301} 原文 ", "trip_id": NSNull(), "creation_intent": "none", "expected_generation": "g", "expected_sequence": Int64(4), "travel_context": NSNull(), "needs_reference": NSNull(), "trip_context": selection]
        change(&value)
        return try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }
    func acceptance(original: OriginalTripDiscussion, trace: String, change: (inout [String: Any]) -> Void = { _ in }) throws -> Data {
        let hash = SHA256.hash(data: original.originalUTF8).map { String(format: "%02x", $0) }.joined()
        let receipt: [String: Any] = ["message_id": "m1", "conversation_id": "chat", "generation": "g", "sequence": original.head.last_sequence + 1, "run_id": "run1", "input_sha256": hash]
        var reference = receipt
        reference.merge(["version": "MESSAGE-trip-reference.1", "message_version": "MESSAGE-send.3", "selection_epoch": Int64(2), "context_kind": "trip", "context_id": "trip-a", "context_version": Int64(9), "trip_context": selection, "content_version": "structured.2", "content_sha256": String(repeating: "a", count: 64)], uniquingKeysWith: { _, new in new })
        var value: [String: Any] = ["version": "MESSAGE-accept.3", "request_id": trace, "receipt": receipt, "reference": reference]
        change(&value)
        return try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }
    @Test func frozenPositiveExamplesAreConsumedWithoutDefaultSelection() throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let bytes = try Data(contentsOf: root.appendingPathComponent("contracts/message/trip-send-examples.1.json"))
        let examples = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let cases = try #require(examples["positive"] as? [[String: Any]])
        #expect(cases.count == 4)
        for example in cases {
            let expected = try #require(example["selection"])
            let parsed = try OriginalTripDiscussion(raw: original { $0["trip_context"] = expected }, maximumBytes: 10000)
            if expected is NSNull { #expect(parsed.trip == nil && parsed.travel == nil) }
            else {
                let value = try #require(parsed.trip)
                #expect(value.id == "trip-a" && value.expectedVersion == 1)
                #expect(NSDictionary(dictionary: value.object).isEqual(to: try #require(expected as? [String: Any])))
            }
        }
    }
    @Test func originalBytesUnicodeAndVersionsAreIndependent() throws {
        let raw = try original { $0["trip_context"] = ["id": "trip-a", "expected_version": Int64.max, "day": NSNull(), "item_id": "item-a"] }
        let decorated = Data(" \n".utf8) + raw + Data("\t".utf8)
        let parsed = try OriginalTripDiscussion(raw: decorated, maximumBytes: 10000, expectedMessageID: "m1")
        #expect(parsed.originalUTF8 == decorated && parsed.trip?.expectedVersion == Int64.max && parsed.head.last_sequence == 4)
        #expect(Data(parsed.text.utf8) == Data(" e\u{301} 原文 ".utf8))
        #expect(throws: (any Error).self) { try OriginalTravelMessageSend(raw: decorated, maximumBytes: 10000) }
        #expect(throws: (any Error).self) { try OriginalMessageSend(raw: decorated, maximumBytes: 10000) }
    }
    @Test(arguments: ["true", "1.0", "1e0", "0", "-1", "9223372036854775808", "null", "\"1\""])
    func nestedVersionCannotBeCoerced(token: String) throws {
        let raw = try original()
        let text = String(decoding: raw, as: UTF8.self).replacingOccurrences(of: "\"expected_version\":9", with: "\"expected_version\":" + token)
        #expect(throws: (any Error).self) { try OriginalTripDiscussion(raw: Data(text.utf8), maximumBytes: 10000) }
    }
    @Test func absentDuplicateUnknownAndCreationFieldsAreRejected() throws {
        let raw = try original(), text = String(decoding: raw, as: UTF8.self)
        let invalid = [
            try original { $0.removeValue(forKey: "trip_context") },
            try original { $0["version"] = "MESSAGE-send.4" },
            try original { $0["creation_intent"] = "consider_trip" },
            try original { $0["needs_reference"] = ["id": "n", "expected_version": 1] },
            try original { $0["travel_context"] = ["id": String(repeating: "a", count: 32), "expected_version": 1] },
            try original { $0["owner_scope"] = "caller" },
            try original { $0["trip_id"] = "trip-a" },
            Data(text.replacingOccurrences(of: "\"expected_version\":9", with: "\"expected_version\":9,\"expected_version\":9").utf8),
            try original { $0["trip_context"] = ["id": "trip-a", "expected_version": 9, "day": NSNull()] },
            try original { $0["trip_context"] = ["id": "trip-a", "expected_version": 9, "day": NSNull(), "item_id": NSNull(), "owner": "caller"] }
        ]
        for value in invalid { #expect(throws: (any Error).self) { try OriginalTripDiscussion(raw: value, maximumBytes: 10000) } }
        #expect(throws: (any Error).self) { try OriginalTripDiscussion(raw: raw, maximumBytes: raw.count - 1) }
        #expect(throws: (any Error).self) { try OriginalTripDiscussion(raw: raw, maximumBytes: 10000, expectedMessageID: "other") }
    }
    @Test func localDateAndZoneRemainExplicit() throws {
        _ = try MessageTripSelection.Day(date: "2000-02-29", timezone: "Asia/Shanghai")
        for date in ["1900-02-29", "2026-02-30", "0000-01-01", "2026-13-01", "2026-1-01", "2026-10-31T00:00:00Z"] {
            #expect(throws: (any Error).self) { try MessageTripSelection.Day(date: date, timezone: "Asia/Shanghai") }
        }
        for zone in ["", "localtime", "Factory", "GMT+0800", "device", "Asia/NoSuchZone"] {
            #expect(throws: (any Error).self) { try MessageTripSelection.Day(date: "2026-10-31", timezone: zone) }
        }
        for id in ["", "-trip", "中文", String(repeating: "a", count: 129), "trip/id"] {
            #expect(throws: (any Error).self) { try MessageTripSelection(id: id, expectedVersion: 1, day: nil, itemID: nil) }
        }
    }
    @Test func originalReceiptPinsCompleteReferenceAndExactRawHash() throws {
        let original = try OriginalTripDiscussion(raw: original(), maximumBytes: 10000)
        let trace = UUID().uuidString
        let bytes = try acceptance(original: original, trace: trace)
        let result = try TripDiscussionAcceptance(raw: bytes, maximumBytes: 10000, requestID: trace, original: original)
        #expect(result.reference.trip == original.trip && result.reference.sequence == 5 && result.reference.selectionEpoch == 2)
        #expect(result.reference.contentVersion == "structured.2" && result.reference.contentSHA256 == String(repeating: "a", count: 64))
        let altered = try OriginalTripDiscussion(raw: Data(" ".utf8) + original.originalUTF8, maximumBytes: 10000)
        #expect(throws: (any Error).self) { try TripDiscussionAcceptance(raw: bytes, maximumBytes: 10000, requestID: trace, original: altered) }
        #expect(throws: (any Error).self) { try TripDiscussionAcceptance(raw: bytes, maximumBytes: 10000, requestID: UUID().uuidString, original: original) }
    }
    @Test func mismatchedOrUpgradedReferenceNeverRebindsOriginal() throws {
        let source = try OriginalTripDiscussion(raw: original(), maximumBytes: 10000), trace = UUID().uuidString
        let changes: [(String, Any)] = [
            ("context_version", 10), ("context_id", "other"), ("selection_epoch", 6), ("selection_epoch", 0),
            ("message_id", "other"), ("run_id", "other"), ("conversation_id", "other"), ("generation", "other"),
            ("sequence", 6), ("input_sha256", String(repeating: "b", count: 64)), ("content_version", "structured.3"),
            ("content_sha256", NSNull()), ("context_kind", "none"), ("message_version", "MESSAGE-send.4"),
            ("trip_context", ["id": "trip-a", "expected_version": 9, "day": NSNull(), "item_id": "item-a"]), ("owner_scope", "caller")
        ]
        for (field, value) in changes {
            let bytes = try acceptance(original: source, trace: trace) {
                var reference = $0["reference"] as! [String: Any]; reference[field] = value; $0["reference"] = reference
            }
            #expect(throws: (any Error).self) { try TripDiscussionAcceptance(raw: bytes, maximumBytes: 10000, requestID: trace, original: source) }
        }
    }
    @Test func receiptSequenceRetainsBigIntAndRejectsBooleanOrDecimal() throws {
        let source = try OriginalTripDiscussion(raw: original { $0["expected_sequence"] = Int64(9_007_199_254_740_992) }, maximumBytes: 10000), trace = UUID().uuidString
        let bytes = try acceptance(original: source, trace: trace)
        let accepted = try TripDiscussionAcceptance(raw: bytes, maximumBytes: 10000, requestID: trace, original: source)
        #expect(accepted.reference.sequence == 9_007_199_254_740_993 && accepted.receipt.sequence == 9_007_199_254_740_993)
        for token in ["true", "9007199254740993.0", "9.007199254740993e15"] {
            let changed = String(decoding: bytes, as: UTF8.self).replacingOccurrences(of: "\"sequence\":9007199254740993", with: "\"sequence\":" + token)
            #expect(throws: (any Error).self) { try TripDiscussionAcceptance(raw: Data(changed.utf8), maximumBytes: 10000, requestID: trace, original: source) }
        }
    }
}
