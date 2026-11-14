import Foundation
import Testing
@testable import CJMessageHTTP

struct LioCalendarWireTests {
    private let conversation = "lio-dialogue-00000000000000000000000000000000"
    private func example(_ name: String) throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let data = try Data(contentsOf: root.appendingPathComponent("contracts/message/trip-send-examples.2.json"))
        let file = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let rows = try #require(file["positive"] as? [[String: Any]])
        return try #require(rows.first { $0["name"] as? String == name }?["value"] as? [String: Any])
    }
    private func bytes(_ value: [String: Any], pretty: Bool = false) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: pretty ? [.sortedKeys, .prettyPrinted] : [.sortedKeys])
    }

    @Test func timelineThreeCarriesCalendarAndPreservesInputWithoutRetaggingOldReaders() throws {
        let value = try example("timeline3")
        let data = try bytes(value)
        let page = try LioTimelineWire.decodePage(data, for: conversation, version: .v3)
        let summary = try #require(page.messages[0].trip?.calendarSummary)
        #expect(summary.calendar == .dated(startDate: "2026-12-01"))
        #expect(summary.days.map(\.index) == [1, 2, 3])
        #expect(summary.inputUTF8 == data)
        #expect(throws: MessageHTTPFailure.self) { try LioTimelineWire.decodePage(data, version: .v1) }
        #expect(throws: MessageHTTPFailure.self) { try LioTimelineWire.decodePage(data, version: .v2) }
        let reformatted = try LioTimelineWire.decodePage(bytes(value, pretty: true), for: conversation, version: .v3)
        #expect(reformatted == page)
    }

    @Test func oldTimelineDecoderDoesNotAdmitCalendarMetadataFromAddedFields() throws {
        var value = try example("timeline3")
        value["version"] = "LIO-timeline.2"
        let page = try LioTimelineWire.decodePage(bytes(value), for: conversation, version: .v2)
        #expect(page.messages[0].trip?.calendarSummary == nil)
        #expect(throws: MessageHTTPFailure.self) { try LioTimelineWire.decodePage(bytes(value), version: .v3) }
    }

    @Test func calendarTimelineRejectsMissingNullableAndUnknownFields() throws {
        for mutation in 0..<3 {
            var value = try example("timeline3")
            var rows = try #require(value["messages"] as? [[String: Any]])
            switch mutation {
            case 0: rows[0].removeValue(forKey: "memory")
            case 1: rows[0]["internal_debug"] = "private"
            default: rows[0]["sources"] = [["title": "Source", "url": NSNull()]]
            }
            value["messages"] = rows
            #expect(throws: Error.self) { try LioTimelineWire.decodePage(bytes(value), version: .v3) }
        }
    }

    @Test func scopedSendThreeUsesItsOwnReceiptAndRestoresExactFirstBytes() throws {
        let original = try LioTimelineWire.Send(messageID: "calendar-first", text: "A three-day idea", locale: .english,
                                               destination: .newChat, version: .v3)
        let restored = try #require(try LioTimelineWire.Send.recordedFirst(original.originalUTF8, messageID: original.messageID))
        #expect(restored.original.version == .v3)
        #expect(restored.original.originalUTF8 == original.originalUTF8)
        var receipt = try example("message receipt3")
        receipt["message_id"] = original.messageID
        #expect(try original.confirm(bytes(receipt)) == conversation)
        receipt["version"] = "LIO-message-receipt.2"
        #expect(throws: MessageHTTPFailure.self) { try original.confirm(bytes(receipt)) }
        var recorded = try #require(JSONSerialization.jsonObject(with: original.originalUTF8) as? [String: Any])
        recorded["selected_options"] = []
        #expect(throws: MessageHTTPFailure.self) { try LioTimelineWire.Send.recordedFirst(bytes(recorded), messageID: original.messageID) }
    }

    @Test func lookupThreeKeepsTheNestedReceiptBytesAndRejectsVersionTwo() throws {
        let original = try LioTimelineWire.Send(messageID: "lookup-three", text: "Plan", locale: .english,
                                               destination: .newChat, version: .v3)
        let receipt = #"{"conversation_id":"lio-dialogue-00000000000000000000000000000000", "message_id":"lookup-three", "version":"LIO-message-receipt.3"}"#
        let data = Data((#"{"version":"LIO-message-lookup.3","receipt":"# + receipt + "}").utf8)
        let result = try #require(try original.confirmLookup(data))
        #expect(result.id == conversation)
        #expect(result.receipt == Data(receipt.utf8))
        let wrong = Data(String(decoding: data, as: UTF8.self).replacingOccurrences(of: "LIO-message-lookup.3", with: "LIO-message-lookup.2").utf8)
        #expect(throws: MessageHTTPFailure.self) { try original.confirmLookup(wrong) }
    }

    @Test func calendarHistoryKeepsUndatedVersionAndUndoThreeOriginal() throws {
        let value = try example("history")
        let page = try LioTripHistoryWire.decodePage(bytes(value), conversationID: conversation, version: .v3)
        #expect(page.current?.calendarSummary?.calendar == .dated(startDate: "2026-12-01"))
        #expect(page.history[0].calendarSummary?.calendar == .undated)
        #expect(page.history[0].days.count == 3)
        let target = try #require(page.undoTarget)
        let undo = try LioTripHistoryWire.Undo(target: target)
        #expect(undo.version == 3)
        let restored = try LioTripHistoryWire.Undo(originalUTF8: undo.originalUTF8, expectedActionID: undo.actionID)
        #expect(restored.version == 3)
        #expect(restored.originalUTF8 == undo.originalUTF8)
        var receipt = try example("undo receipt3")
        receipt["action_id"] = undo.actionID
        #expect(try restored.committed(bytes(receipt)))
        receipt["version"] = "LIO-trip-undo-receipt.2"
        #expect(throws: MessageHTTPFailure.self) { try restored.committed(bytes(receipt)) }
        #expect(throws: MessageHTTPFailure.self) { try LioTripHistoryWire.decodePage(bytes(value), conversationID: conversation) }
    }
}
