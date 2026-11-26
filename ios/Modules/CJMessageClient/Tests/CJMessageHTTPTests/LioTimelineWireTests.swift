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

    @Test func v2SelectsNewExistingOrDefaultWithoutMixingDestinations() throws {
        let new = try LioTimelineWire.Send(messageID: "first", text: "Hello", locale: .english, destination: .newChat)
        let fields = try #require(JSONSerialization.jsonObject(with: new.originalUTF8) as? [String: Any])
        #expect(fields["version"] as? String == "LIO-message.2")
        #expect(fields["new_conversation"] as? Bool == true)
        #expect(fields["conversation_id"] == nil)
        let existing = try LioTimelineWire.Send(messageID: "next", text: "Hello", locale: .english, destination: .existing(conversation))
        let scoped = try #require(JSONSerialization.jsonObject(with: existing.originalUTF8) as? [String: Any])
        #expect(scoped["conversation_id"] as? String == conversation && scoped["new_conversation"] == nil)
        let fallback = try LioTimelineWire.Send(messageID: "default", text: "Hello", locale: .english, destination: .defaultChat)
        let defaults = try #require(JSONSerialization.jsonObject(with: fallback.originalUTF8) as? [String: Any])
        #expect(defaults["conversation_id"] == nil && defaults["new_conversation"] == nil)

        let receipt = Data("""
            {"version":"LIO-message-receipt.2","message_id":"first","conversation_id":"\(conversation)"}
            """.utf8)
        #expect(try new.confirm(receipt) == conversation)
        #expect(throws: MessageHTTPFailure.self) { try existing.confirm(receipt) }
        let legacy = try LioTimelineWire.Send(messageID: "first", text: "Hello", locale: .english)
        #expect(throws: MessageHTTPFailure.self) { try legacy.confirm(receipt) }
    }

    @Test func v2TimelineRequiresTheExpectedVersionAndConversation() throws {
        let data = Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[],"next_before":null}
            """.utf8)
        #expect(try LioTimelineWire.decodePage(data, for: conversation, version: .v2).conversationID == conversation)
        #expect(throws: MessageHTTPFailure.self) { try LioTimelineWire.decodePage(data, for: conversation) }
        #expect(throws: MessageHTTPFailure.self) {
            try LioTimelineWire.decodePage(data, for: "lio-dialogue-00000000000000000000000000000000", version: .v2)
        }
    }

    // MARK: LIO-answer-followups.1 (#1727)

    private func v2Row(status: String = "completed", extra: String) -> String {
        """
        {"message_id":"m1","text":"Q","answer":"One.\\n\\nTwo.","status":"\(status)","sources":[]\(extra)}
        """
    }

    private func v2Page(_ rows: String) -> Data {
        Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[\(rows)],"next_before":null}
            """.utf8)
    }

    private let buttons = """
        ,"layout":"split","followups":{"version":"LIO-answer-followups.1","actions":[
        {"tool":"payment-guide","parameters":{},"label":"打开支付开通指南"},
        {"tool":"taxi","parameters":{"destination":"故宫博物院","lat":"39.918058","lng":"116.397026"},"label":"打车去这里"}]}
        """

    @Test func rowsWithoutTheNewKeysReadAsBefore() throws {
        let page = try LioTimelineWire.decodePage(v2Page(v2Row(extra: "")), for: conversation, version: .v2)
        let message = try #require(page.messages.first)
        #expect(message.layout == nil && message.followups.isEmpty)
    }

    @Test func layoutAndFollowupsAreProjectedForACompletedSplitAnswer() throws {
        let page = try LioTimelineWire.decodePage(v2Page(v2Row(extra: buttons)), for: conversation, version: .v2)
        let message = try #require(page.messages.first)
        #expect(message.layout == .split)
        #expect(message.followups.map(\.tool) == ["payment-guide", "taxi"])
        #expect(message.followups[0].parameters.isEmpty && message.followups[0].label == "打开支付开通指南")
        #expect(message.followups[1].parameters == ["destination": "故宫博物院", "lat": "39.918058", "lng": "116.397026"])
    }

    @Test func buttonsOnlyAppearOnACompletedSplitRow() throws {
        let answering = try LioTimelineWire.decodePage(v2Page(v2Row(status: "answering", extra: buttons)), for: conversation, version: .v2)
        #expect(answering.messages[0].layout == .split && answering.messages[0].followups.isEmpty)
        let single = buttons.replacingOccurrences(of: "\"split\"", with: "\"single\"")
        let page = try LioTimelineWire.decodePage(v2Page(v2Row(extra: single)), for: conversation, version: .v2)
        #expect(page.messages[0].layout == .single && page.messages[0].followups.isEmpty)
    }

    @Test(arguments: [
        #","layout":"split","followups":{"version":"LIO-answer-followups.2","actions":[{"tool":"taxi","parameters":{},"label":"打车"}]}"#,
        #","layout":"split","followups":{"version":"LIO-answer-followups.1","actions":[]}"#,
        #","layout":"split","followups":{"version":"LIO-answer-followups.1","actions":[{"tool":"a","parameters":{},"label":"1"},{"tool":"b","parameters":{},"label":"2"},{"tool":"c","parameters":{},"label":"3"}]}"#,
        #","layout":"split","followups":{"version":"LIO-answer-followups.1","actions":[{"tool":"taxi","parameters":{"lat":39.9},"label":"打车"}]}"#,
        #","layout":"split","followups":{"version":"LIO-answer-followups.1","actions":[{"tool":"taxi bad","parameters":{},"label":"打车"}]}"#,
        #","layout":"split","followups":{"version":"LIO-answer-followups.1","actions":[{"tool":"taxi","parameters":{},"label":" 打车"}]}"#,
        #","layout":"split","followups":{"version":"LIO-answer-followups.1","actions":[{"tool":"taxi","parameters":{},"label":"打\u200b车"}]}"#,
        #","layout":"split","followups":{"version":"LIO-answer-followups.1","actions":[{"tool":"taxi","parameters":{"k":""},"label":"打车"}]}"#,
        #","layout":"split","followups":"nope""#,
    ]) func aDamagedButtonListReadsAsNoButtonsAndNeverFailsThePage(extra: String) throws {
        let page = try LioTimelineWire.decodePage(v2Page(v2Row(extra: extra)), for: conversation, version: .v2)
        #expect(page.messages[0].layout == .split)
        #expect(page.messages[0].followups.isEmpty, "all or nothing")
        #expect(page.messages[0].answer == "One.\n\nTwo.")
    }

    // MARK: tap-to-ask chips (#1727, part 2)

    private let ticket = String(repeating: "a", count: 42) + "-"

    private func chipsExtra(_ followups: String) -> String { ",\"layout\":\"split\",\"followups\":" + followups }

    @Test func chipsAreProjectedWithOrWithoutATicketAndActionsAreOptional() throws {
        let only = chipsExtra("""
            {"version":"LIO-answer-followups.1","chips":[{"label":"付不了怎么办","ticket":"\(ticket)"},{"label":"Older question"}]}
            """)
        let message = try #require(try LioTimelineWire.decodePage(v2Page(v2Row(extra: only)), for: conversation, version: .v2).messages.first)
        #expect(message.followups.isEmpty)
        #expect(message.chips == [.init(label: "付不了怎么办", ticket: ticket), .init(label: "Older question", ticket: nil)])
        let both = chipsExtra("""
            {"version":"LIO-answer-followups.1","actions":[{"tool":"taxi","parameters":{},"label":"打车"}],"chips":[{"label":"A","ticket":"\(ticket)"}]}
            """)
        let mixed = try #require(try LioTimelineWire.decodePage(v2Page(v2Row(extra: both)), for: conversation, version: .v2).messages.first)
        #expect(mixed.followups.map(\.tool) == ["taxi"] && mixed.chips.count == 1)
    }

    @Test(arguments: [
        #"{"version":"LIO-answer-followups.1"}"#,
        #"{"version":"LIO-answer-followups.1","actions":[],"chips":[]}"#,
        #"{"version":"LIO-answer-followups.1","chips":[{"label":"1"},{"label":"2"},{"label":"3"},{"label":"4"}]}"#,
        #"{"version":"LIO-answer-followups.1","chips":[{"label":"ok","ticket":"short"}]}"#,
        #"{"version":"LIO-answer-followups.1","chips":[{"label":"ok","ticket":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa+"}]}"#,
        #"{"version":"LIO-answer-followups.1","chips":[{"label":"这个问题的字数超过了二十四个字符的上限这个问题的字数超过了二十四个"}]}"#,
        #"{"version":"LIO-answer-followups.1","chips":[{"label":" lead"}]}"#,
        #"{"version":"LIO-answer-followups.1","chips":[{"label":"a\nb"}]}"#,
        #"{"version":"LIO-answer-followups.1","chips":[{"label":""}]}"#,
    ]) func aDamagedChipListReadsAsNothingAndNeverFailsThePage(followups: String) throws {
        let page = try LioTimelineWire.decodePage(v2Page(v2Row(extra: chipsExtra(followups))), for: conversation, version: .v2)
        #expect(page.messages[0].chips.isEmpty && page.messages[0].followups.isEmpty)
        #expect(page.messages[0].answer == "One.\n\nTwo.")
    }

    @Test func chipsOnlyShowOnACompletedSplitRow() throws {
        let json = chipsExtra(#"{"version":"LIO-answer-followups.1","chips":[{"label":"ok"}]}"#)
        let answering = try LioTimelineWire.decodePage(v2Page(v2Row(status: "answering", extra: json)), for: conversation, version: .v2)
        #expect(answering.messages[0].chips.isEmpty)
    }

    // MARK: sending a chip

    @Test func aChipQuestionCarriesItsTicketAsOneExtraFieldAndNothingElseChanges() throws {
        let plain = try LioTimelineWire.Send(messageID: "m1", text: "付不了怎么办", locale: .chinese, destination: .existing(conversation))
        let chip = try LioTimelineWire.Send(messageID: "m1", text: "付不了怎么办", locale: .chinese, destination: .existing(conversation),
                                            chipTicket: ticket)
        let plainObject = try #require(JSONSerialization.jsonObject(with: plain.originalUTF8) as? [String: Any])
        let chipObject = try #require(JSONSerialization.jsonObject(with: chip.originalUTF8) as? [String: Any])
        #expect(plainObject["chip_ticket"] == nil, "without a ticket the bytes are what they were")
        #expect(chipObject["chip_ticket"] as? String == ticket)
        #expect(chipObject.filter { $0.key != "chip_ticket" }.map(\.key).sorted() == plainObject.keys.sorted())
        #expect(chipObject["text"] as? String == "付不了怎么办", "the label, byte for byte")
    }

    @Test func aTicketIsRefusedOnEveryVersionButTheSecondAndWhenMalformed() throws {
        for version in [LioTimelineWire.Version.v3, .v4] {
            #expect(throws: MessageHTTPFailure.self) {
                _ = try LioTimelineWire.Send(messageID: "m1", text: "Q", locale: .english, destination: .existing(conversation),
                                             version: version, chipTicket: ticket)
            }
        }
        #expect(throws: MessageHTTPFailure.self) {
            _ = try LioTimelineWire.Send(messageID: "m1", text: "Q", locale: .english, destination: .existing(conversation), chipTicket: "short")
        }
    }

    @Test func anUnknownLayoutReadsAsNoLayout() throws {
        let page = try LioTimelineWire.decodePage(v2Page(v2Row(extra: #","layout":"triple""#)), for: conversation, version: .v2)
        #expect(page.messages[0].layout == nil && page.messages[0].followups.isEmpty)
    }

    private func page(_ rows: String) -> Data {
        Data("""
            {"version":"LIO-timeline.1","conversation_id":"\(conversation)","messages":[\(rows)],"next_before":null}
            """.utf8)
    }
}
