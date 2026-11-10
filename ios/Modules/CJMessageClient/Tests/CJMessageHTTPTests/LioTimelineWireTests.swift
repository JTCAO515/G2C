import Foundation
import Testing
import CJMessageHTTP

struct LioTimelineWireTests {
    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"

    @Test func preservesQuestionBytesAndRejectsAnUnrelatedAcceptance() throws {
        let send = try LioTimelineWire.Send(messageID: "question-1", text: " 在上海怎么坐地铁？ ",
                                           locale: .chinese, conversationID: conversation)
        let body = try #require(JSONSerialization.jsonObject(with: send.originalUTF8) as? [String: String])
        #expect(body["text"] == " 在上海怎么坐地铁？ ")
        #expect(body["version"] == "LIO-message.1")
        #expect(body["locale"] == "zh")
        let reply = Data("""
            {"version":"LIO-message-receipt.1","message_id":"question-1","conversation_id":"\(conversation)"}
            """.utf8)
        #expect(try send.confirm(reply) == conversation)
        let wrong = Data("""
            {"version":"LIO-message-receipt.1","message_id":"different","conversation_id":"\(conversation)"}
            """.utf8)
        #expect(throws: MessageHTTPFailure.self) { try send.confirm(wrong) }
    }

    @Test func projectsCommittedTextAndOnlySafeLinks() throws {
        let data = page("""
            {"message_id":"one","text":"Where?","answer":"Take the ","status":"answering","failure":null,"sources":[
              {"title":"Metro map","url":"https://example.com/map","observed_at":null},
              {"title":"Station details","url":"javascript:alert(1)","observed_at":null}
            ],"trip":null,"memory":null},
            {"message_id":"two","text":"When?","answer":"","status":"failed","failure":"unavailable","sources":[],"trip":null,"memory":null}
            """)
        let snapshot = try LioTimelineWire.decodePage(data, for: conversation)
        #expect(snapshot.messages.map(\.id) == ["one", "two"])
        #expect(snapshot.messages.map(\.state) == [.answering, .unavailable])
        let first = try #require(snapshot.messages.first)
        #expect(first.answer == "Take the ")
        #expect(first.sources.first?.link?.host == "example.com")
        #expect(first.sources.last?.link == nil)
    }

    @Test func rejectsInconsistentStateAndConversation() throws {
        let data = page("""
            {"message_id":"one","text":"Where?","answer":"","status":"completed","failure":"quota","sources":[]}
            """)
        #expect(throws: MessageHTTPFailure.self) { try LioTimelineWire.decodePage(data) }
        #expect(throws: MessageHTTPFailure.self) {
            try LioTimelineWire.decodePage(page(""), for: "lio-dialogue-00000000000000000000000000000000")
        }
    }

    private func page(_ rows: String) -> Data {
        Data("""
            {"version":"LIO-timeline.1","conversation_id":"\(conversation)","messages":[\(rows)],"next_before":null}
            """.utf8)
    }
}
