import Foundation
import Testing
import CJMessageClient
@testable import CJMessageHTTP

struct OriginalTravelMessageTests {
    func raw(context: String = "null",needs: String = "null",intent: String = "none",sequence: String = "0") -> Data {
        Data((" {\"version\":\"MESSAGE-send.2\",\"conversation_id\":\"chat\",\"message_id\":\"original\",\"text\":\"  e\\u0301 / 原文  \",\"trip_id\":null,\"creation_intent\":\""+intent+"\",\"expected_generation\":\"g1\",\"expected_sequence\":"+sequence+",\"travel_context\":"+context+",\"needs_reference\":"+needs+"} \n").utf8)
    }
    @Test func explicitNonePreservesOriginalBytesAndNeverUsesConversationAsTravel() throws {
        let bytes = raw();let original = try OriginalTravelMessageSend(raw: bytes,maximumBytes: 10000,expectedMessageID: "original")
        #expect(original.originalUTF8 == bytes && original.travelContext == nil && original.needsReference == nil)
        #expect(original.head.conversation_id == "chat" && original.head.last_sequence == 0)
        #expect(Data(original.text.utf8) == Data("  e\u{301} / 原文  ".utf8))
        #expect(throws: (any Error).self) { try OriginalMessageSend(raw: bytes,maximumBytes: 10000) }
    }
    @Test func travelAndNeedsVersionsAreDistinctFromMessageSequence() throws {
        let original = try OriginalTravelMessageSend(raw: raw(context: "{\"id\":\"0123456789abcdef0123456789abcdef\",\"expected_version\":9}",needs: "{\"id\":\"needs:one\",\"expected_version\":7}",intent: "consider_trip",sequence: "4"),maximumBytes: 10000)
        #expect(original.travelContext?.expectedVersion == 9 && original.needsReference?.expectedVersion == 7 && original.head.last_sequence == 4)
    }
    @Test(arguments: ["true", "1.0", "1e0", "0", "-1", "9223372036854775808", "null", "\"1\""])
    func nestedTravelVersionRejectsCoercion(token: String) {
        #expect(throws: (any Error).self) {
            try OriginalTravelMessageSend(raw: raw(context: "{\"id\":\"0123456789abcdef0123456789abcdef\",\"expected_version\":"+token+"}"),maximumBytes: 10000)
        }
    }
    @Test(arguments: ["true", "1.0", "1e0", "0", "-1"])
    func needsVersionRejectsCoercion(token: String) {
        #expect(throws: (any Error).self) {
            try OriginalTravelMessageSend(raw: raw(needs: "{\"id\":\"needs:one\",\"expected_version\":"+token+"}",intent: "consider_trip"),maximumBytes: 10000)
        }
    }
    @Test func absentUnknownOrDuplicateContextNeverBecomesNone() {
        let text = String(decoding: raw(),as: UTF8.self)
        for changed in [text.replacingOccurrences(of: ",\"travel_context\":null",with: ""),
                        text.replacingOccurrences(of: "\"travel_context\":null",with: "\"travel_context\":null,\"travel_context\":null"),
                        text.replacingOccurrences(of: "MESSAGE-send.2",with: "MESSAGE-send.3"),
                        text.replacingOccurrences(of: "\"travel_context\":null",with: "\"travel_context\":{\"id\":\"0123456789abcdef0123456789abcdef\",\"expected_version\":1,\"owner_scope\":\"caller\"}") ] {
            #expect(throws: (any Error).self) { try OriginalTravelMessageSend(raw: Data(changed.utf8),maximumBytes: 10000) }
        }
    }
    @Test func intentAndTripIdentityStayClosed() {
        #expect(throws: (any Error).self) { try OriginalTravelMessageSend(raw: raw(intent: "consider_trip"),maximumBytes: 10000) }
        #expect(throws: (any Error).self) { try OriginalTravelMessageSend(raw: raw(needs: "{\"id\":\"n\",\"expected_version\":1}"),maximumBytes: 10000) }
        #expect(throws: (any Error).self) { try OriginalTravelMessageSend(raw: raw(),maximumBytes: 1) }
        #expect(throws: (any Error).self) { try OriginalTravelMessageSend(raw: raw(),maximumBytes: 10000,expectedMessageID: "different") }
    }
}
