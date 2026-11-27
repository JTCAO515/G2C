import Foundation
import Testing
@testable import CJMessageHTTP

/// #2010 (M-5): `rich.memory.used` and `used_total` of LIO-answer-rich.1 as the App reads them: 1 to 3 items, an id of the
/// contract's form, a one-line title of at most 40 characters, a total of 1...99 that is at least the number listed. One
/// bad item is dropped alone; a list or total that breaks its rule is dropped whole; none of it ever fails the page.
struct LioAnswerMemoryUsedWireTests {
    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"

    private func page(rich: String?, extra: String = "", status: String = "completed", answer: String = "上午去故宫。") -> Data {
        let answerJSON = String(decoding: (try? JSONEncoder().encode(answer)) ?? Data(), as: UTF8.self)
        return Data("""
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[
            {"message_id":"m1","text":"Q","answer":\(answerJSON),"status":"\(status)","sources":[]\(extra)\(rich.map { ",\"rich\":" + $0 } ?? "")}],"next_before":null}
            """.utf8)
    }

    private func read(_ rich: String?, extra: String = "", status: String = "completed", answer: String = "上午去故宫。") throws -> LioTimelineWire.Message {
        try #require(try LioTimelineWire.decodePage(page(rich: rich, extra: extra, status: status, answer: answer),
                                                    for: conversation, version: .v2).messages.first)
    }

    private func used(_ items: String, total: String = "2", other: String = "") -> String {
        #"{"version":"LIO-answer-rich.1"\#(other),"memory":{"used":\#(items),"used_total":\#(total)}}"#
    }

    private func item(_ id: String, _ title: String) -> String { #"{"item_id":"\#(id)","title":"\#(title)"}"# }

    private let spicy = #"{"item_id":"mem-spicy","title":"不吃辣"}"#
    private let slow = #"{"item_id":"mem_slow.pace:1","title":"节奏慢一点"}"#
    private let trip = #","trip":{"trip_id":"trip-1","title":"北京三日","days":[]}"#

    // MARK: Reading

    @Test func twoItemsAndTheirTotalAreRead() throws {
        let rich = try #require(try read(used("[\(spicy),\(slow)]", total: "5")).rich)
        let value = try #require(rich.memoryUsed)
        #expect(value.items == [.init(itemID: "mem-spicy", title: "不吃辣"), .init(itemID: "mem_slow.pace:1", title: "节奏慢一点")])
        #expect(value.total == 5, "more were used than are listed")
        #expect(rich.entities.isEmpty && rich.cards.isEmpty && !rich.memoryPrompt, "the other parts are as they were")
    }

    @Test func aRowWithoutTheFieldReadsAsBefore() throws {
        #expect(try read(nil).rich == nil)
        #expect(try read(#"{"version":"LIO-answer-rich.1","entities":[{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}]}"#)
            .rich?.memoryUsed == nil)
        let prompt = try read(#"{"version":"LIO-answer-rich.1","memory":{"prompt":"consent"}}"#).rich
        #expect(prompt?.memoryPrompt == true && prompt?.memoryUsed == nil, "memory.prompt alone is as before")
    }

    @Test func theTwoMemoryPartsAreReadOnEachOthersTerms() throws {
        let both = #"{"version":"LIO-answer-rich.1","memory":{"prompt":"consent","used":[\#(spicy)],"used_total":1}}"#
        let rich = try #require(try read(both).rich)
        #expect(rich.memoryPrompt && rich.memoryUsed?.items.map(\.itemID) == ["mem-spicy"])
        let brokenUsed = #"{"version":"LIO-answer-rich.1","memory":{"prompt":"consent","used":"x","used_total":"y"}}"#
        let kept = try #require(try read(brokenUsed).rich)
        #expect(kept.memoryPrompt && kept.memoryUsed == nil, "a bad used never costs the prompt")
    }

    @Test func richOnlyShowsOnACompletedRowWithAnAnswer() throws {
        let body = used("[\(spicy)]", total: "1")
        for status in ["sending", "answering"] { #expect(try read(body, status: status).rich == nil, "\(status)") }
        #expect(try read(body, answer: "").rich == nil)
    }

    @Test func aPlanReplyKeepsItsMemoriesAndStillNothingElse() throws {
        let place = #"{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}"#
        let card = #"{"type":"taxi","label":"打车去这里","open":{"tool":"taxi","parameters":{}}}"#
        let body = #"{"version":"LIO-answer-rich.1","entities":[\#(place)],"cards":[\#(card)],"memory":{"prompt":"consent","used":[\#(spicy)],"used_total":2}}"#
        let rich = try #require(try read(body, extra: trip).rich)
        #expect(rich.cards.isEmpty && !rich.memoryPrompt, "a plan reply carries no cards, as before")
        #expect(rich.entities.count == 1 && rich.memoryUsed?.total == 2)
        let only = try #require(try read(used("[\(spicy)]", total: "1"), extra: trip).rich)
        #expect(only.memoryUsed?.items.count == 1 && only.entities.isEmpty, "memories alone are a rich")
    }

    // MARK: Rules

    @Test(arguments: [
        (#"[{"item_id":"a","title":"x"},{"item_id":"b","title":"x"},{"item_id":"c","title":"x"},{"item_id":"d","title":"x"}]"#, "4"),
        ("[]", "1"),
        (#"[{"item_id":"a","title":"x"}]"#, "0"),
        (#"[{"item_id":"a","title":"x"}]"#, "100"),
        (#"[{"item_id":"a","title":"x"}]"#, "-1"),
        (#"[{"item_id":"a","title":"x"},{"item_id":"b","title":"y"}]"#, "1"),
        (#"[{"item_id":"a","title":"x"}]"#, "1.5"),
        (#"[{"item_id":"a","title":"x"}]"#, #""1""#),
        (#"[{"item_id":"a","title":"x"}]"#, "null"),
        (#"{"item_id":"a","title":"x"}"#, "1"),
        (#""a""#, "1"),
        ("null", "1"),
    ]) func aListOrTotalThatBreaksItsRuleIsDroppedWhole(items: String, total: String) throws {
        let message = try read(used(items, total: total))
        #expect(message.rich == nil, "\(items) \(total)")
        #expect(message.answer == "上午去故宫。")
    }

    @Test func aMissingHalfDropsTheWholeOfIt() throws {
        #expect(try read(#"{"version":"LIO-answer-rich.1","memory":{"used":[\#(spicy)]}}"#).rich == nil)
        #expect(try read(#"{"version":"LIO-answer-rich.1","memory":{"used_total":1}}"#).rich == nil)
    }

    @Test func theTotalMayBeAnythingFromTheNumberListedTo99() throws {
        for (total, ok) in [(1, true), (2, true), (99, true), (100, false), (0, false)] {
            let value = try read(used("[\(spicy)]", total: "\(total)")).rich?.memoryUsed
            #expect((value != nil) == ok, "\(total)")
        }
        #expect(try read(used("[\(spicy),\(slow)]", total: "2")).rich?.memoryUsed?.items.count == 2, "equal to the number listed")
    }

    @Test(arguments: [
        "", "-a", ".a", ":a", "_a", " a", "a b", "a/b", "a\\u000ab", "记忆", "a记", "a\\\"b",
        String(repeating: "a", count: 257),
    ]) func anItemWithABadIdIsDroppedAlone(id: String) throws {
        let rich = try #require(try read(used("[\(item(id, "好"))," + spicy + "]")).rich)
        #expect(rich.memoryUsed?.items.map(\.itemID) == ["mem-spicy"], "\(id)")
        #expect(rich.memoryUsed?.total == 2, "the total is the server's")
    }

    @Test func theLongestAndTheShortestGoodIdsAreKept() throws {
        let longest = "a" + String(repeating: "b", count: 255)
        let rich = try #require(try read(used("[\(item(longest, "长"))," + item("0", "短") + "]")).rich)
        #expect(rich.memoryUsed?.items.map(\.itemID) == [longest, "0"])
        #expect(LioTimelineWire.MemoryUsed.validItemID("A0_.:-z"))
    }

    @Test func aTitleOverFortyCharactersOrOnMoreThanOneLineIsDroppedAlone() throws {
        let forty = String(repeating: "甲", count: 40)
        let fortyOne = String(repeating: "甲", count: 41)
        let kept = try #require(try read(used("[\(item("a", forty)),\(item("b", fortyOne)),\(item("c", "两\\n行"))]", total: "3")).rich)
        #expect(kept.memoryUsed?.items.map(\.itemID) == ["a"], "40 is the limit; a new line is not one line")
        for bad in ["a\\rb", "a\\u2028b", "a\\u2029b", "a\\tb", "a\\u0000b", "a\\u200bb", " 前空格", "后空格 ", ""] {
            let value = try read(used("[\(item("a", bad)),\(spicy)]")).rich?.memoryUsed
            #expect(value?.items.map(\.itemID) == ["mem-spicy"], "\(bad.debugDescription)")
        }
    }

    @Test func anItemWithoutATitleOrAnIdOrOfTheWrongTypeIsDroppedAlone() throws {
        let bad = [#"{"item_id":"a"}"#, #"{"title":"x"}"#, #"{"item_id":7,"title":"x"}"#, #"{"item_id":"a","title":null}"#,
                   "5", "null", #""x""#]
        for one in bad {
            let value = try read(used("[\(one),\(spicy)]")).rich?.memoryUsed
            #expect(value?.items.map(\.itemID) == ["mem-spicy"], "\(one)")
        }
        let extra = #"{"item_id":"a","title":"x","score":0.9}"#
        #expect(try read(used("[\(extra)]", total: "1")).rich?.memoryUsed?.items.count == 1, "an unknown key is ignored")
    }

    @Test func aRepeatedIdIsListedOnce() throws {
        let value = try read(used("[\(spicy),\(spicy)]", total: "2")).rich?.memoryUsed
        #expect(value?.items.count == 1 && value?.total == 2)
    }

    @Test func whenEveryItemFailsThereIsNoUsedAndNoRich() throws {
        #expect(try read(used("[\(item("-", "x")),\(item("", "y"))]")).rich == nil)
        let withPlace = #"{"version":"LIO-answer-rich.1","entities":[{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}],"memory":{"used":[\#(item("-", "x"))],"used_total":1}}"#
        let rich = try #require(try read(withPlace).rich)
        #expect(rich.memoryUsed == nil && rich.entities.count == 1, "the places are kept")
    }

    @Test func aBrokenMemoryPartNeverFailsThePage() throws {
        for memory in [#""x""#, "7", "[]", "null", #"{"used":{"a":1},"used_total":1}"#] {
            let message = try read(#"{"version":"LIO-answer-rich.1","memory":\#(memory),"entities":[{"type":"place","start":2,"end":4,"place_id":"pl_bj_gugong"}]}"#)
            #expect(message.rich?.memoryUsed == nil && message.rich?.entities.count == 1, "\(memory)")
        }
    }

    @Test func theInitKeepsEveryExistingCallerWorking() {
        #expect(LioTimelineWire.Rich().memoryUsed == nil)
        #expect(LioTimelineWire.Rich(entities: [], cards: [], memoryPrompt: true).memoryUsed == nil)
        #expect(LioTimelineWire.MemoryUsed.validated([.init(itemID: "a", title: "b")], total: 1)?.total == 1)
        #expect(LioTimelineWire.MemoryUsed.validated([nil], total: 1) == nil)
    }
}
