import Foundation
import Testing
@testable import CJMessageHTTP

/// #2001: `rich.memory.used` and `used_total` (LIO-answer-rich.1): which remembered preferences an answer was based on.
@MainActor
struct LioMemoryUsedWireTests {
    private let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"

    private func decoded(_ memory: String, status: String = "completed", answer: String = "好的。") throws -> LioTimelineWire.Message {
        let body = """
            {"version":"LIO-timeline.2","conversation_id":"\(conversation)","messages":[{"message_id":"m1","text":"Q","answer":"\(answer)","status":"\(status)","sources":[],"rich":{"version":"LIO-answer-rich.1","memory":\(memory)}}],"next_before":null}
            """
        return try #require(try LioTimelineWire.decodePage(Data(body.utf8), for: conversation, version: .v2).messages.first)
    }

    private func used(_ memory: String) throws -> LioTimelineWire.MemoryUsed? { try decoded(memory).rich?.memoryUsed }

    @Test func oneToThreeItemsAndTheTotalAreRead() throws {
        let one = try used(#"{"used":[{"item_id":"mem-71c2","title":"节奏慢"}],"used_total":1}"#)
        #expect(one == .init(items: [.init(itemID: "mem-71c2", title: "节奏慢")], total: 1))
        let three = try used(#"{"used":[{"item_id":"a","title":"x1"},{"item_id":"b","title":"x2"},{"item_id":"c","title":"x3"}],"used_total":42}"#)
        #expect(three?.items.map(\.itemID) == ["a", "b", "c"] && three?.total == 42, "most relevant first, as sent")
    }

    @Test func theTotalMayExceedTheListButNeverFallBelowIt() throws {
        #expect(try used(#"{"used":[{"item_id":"a","title":"x1"},{"item_id":"b","title":"x2"}],"used_total":99}"#)?.total == 99)
        #expect(try used(#"{"used":[{"item_id":"a","title":"x1"},{"item_id":"b","title":"x2"}],"used_total":2}"#)?.total == 2)
        #expect(try used(#"{"used":[{"item_id":"a","title":"x1"},{"item_id":"b","title":"x2"}],"used_total":1}"#) == nil)
    }

    @Test(arguments: [
        #"{"used":[{"item_id":"a","title":"x1"}]}"#,
        #"{"used_total":3}"#,
        #"{"used":[],"used_total":1}"#,
        #"{"used":[{"item_id":"a","title":"x1"}],"used_total":0}"#,
        #"{"used":[{"item_id":"a","title":"x1"}],"used_total":100}"#,
        #"{"used":[{"item_id":"a","title":"x1"}],"used_total":-1}"#,
        #"{"used":[{"item_id":"a","title":"x1"}],"used_total":"1"}"#,
        #"{"used":[{"item_id":"a","title":"x1"}],"used_total":1.5}"#,
        #"{"used":[{"item_id":"a","title":"x1"},{"item_id":"b","title":"x2"},{"item_id":"c","title":"x3"},{"item_id":"d","title":"x4"}],"used_total":4}"#,
        #"{"used":[{"item_id":"a","title":"x1"},{"item_id":"a","title":"x2"}],"used_total":2}"#,
        #"{"used":"nope","used_total":1}"#,
        #"{"used":{"item_id":"a","title":"x1"},"used_total":1}"#,
        #"{"used":null,"used_total":null}"#,
    ]) func aBrokenUsedReadsAsNoneAndNeverFailsThePage(memory: String) throws {
        let message = try decoded(memory)
        #expect(message.rich?.memoryUsed == nil)
        #expect(message.answer == "好的。")
    }

    @Test(arguments: [
        #"{"item_id":"","title":"x"}"#,
        #"{"item_id":"_a","title":"x"}"#,
        #"{"item_id":"-a","title":"x"}"#,
        #"{"item_id":"a b","title":"x"}"#,
        #"{"item_id":"a/b","title":"x"}"#,
        #"{"item_id":"é","title":"x"}"#,
        #"{"item_id":"a","title":""}"#,
        #"{"item_id":"a","title":"line\nbreak"}"#,
        #"{"item_id":"a","title":"tab\there"}"#,
        #"{"item_id":"a","title":"zero​width"}"#,
        #"{"item_id":"a","title":"sep arator"}"#,
        #"{"item_id":"a","title":"bom﻿here"}"#,
        #"{"item_id":"a"}"#,
        #"{"title":"x"}"#,
        #"{"item_id":7,"title":"x"}"#,
        #"{"item_id":"a","title":["x"]}"#,
    ]) func anItemThatFailsItsRuleIsDroppedOnItsOwn(item: String) throws {
        let good = #"{"item_id":"ok","title":"节奏慢"}"#
        let both = try used(#"{"used":[\#(item),\#(good)],"used_total":2}"#)
        #expect(both == .init(items: [.init(itemID: "ok", title: "节奏慢")], total: 2), "the good one stays")
        #expect(try used(#"{"used":[\#(item)],"used_total":1}"#) == nil, "nothing left, no line")
    }

    @Test func idAndTitleLimitsAreExact() throws {
        let id256 = "a" + String(repeating: "b", count: 255)
        let id257 = id256 + "c"
        #expect(try used(#"{"used":[{"item_id":"\#(id256)","title":"x"}],"used_total":1}"#)?.items.first?.itemID == id256)
        #expect(try used(#"{"used":[{"item_id":"\#(id257)","title":"x"}],"used_total":1}"#) == nil)
        let title40 = String(repeating: "节", count: 40)
        #expect(try used(#"{"used":[{"item_id":"a","title":"\#(title40)"}],"used_total":1}"#)?.items.first?.title == title40)
        #expect(try used(#"{"used":[{"item_id":"a","title":"\#(title40)节"}],"used_total":1}"#) == nil)
        #expect(try used(#"{"used":[{"item_id":"a.b:c_d-1","title":"x"}],"used_total":1}"#) != nil)
    }

    @Test func anExtraKeyOnAnItemIsIgnoredAndTheRememberedTextIsNeverKept() throws {
        let value = try used(#"{"used":[{"item_id":"mem-1","title":"x1","text":"不吃辣","body":"secret"}],"used_total":1}"#)
        #expect(value == .init(items: [.init(itemID: "mem-1", title: "x1")], total: 1))
    }

    @Test func usedAndThePromptAreReadSeparately() throws {
        let both = try decoded(#"{"prompt":"consent","used":[{"item_id":"a","title":"x1"}],"used_total":1}"#).rich
        #expect(both?.memoryPrompt == true && both?.memoryUsed?.items.count == 1)
        let brokenUsed = try decoded(#"{"prompt":"consent","used":"nope","used_total":1}"#).rich
        #expect(brokenUsed?.memoryPrompt == true && brokenUsed?.memoryUsed == nil)
        let brokenPrompt = try decoded(#"{"prompt":"granted","used":[{"item_id":"a","title":"x1"}],"used_total":1}"#).rich
        #expect(brokenPrompt?.memoryPrompt == false && brokenPrompt?.memoryUsed != nil)
    }

    @Test func usedOnlyRidesOnACompletedRowWithAnAnswer() throws {
        let memory = #"{"used":[{"item_id":"a","title":"x1"}],"used_total":1}"#
        #expect(try decoded(memory, status: "answering").rich == nil)
        #expect(try decoded(memory, status: "sending").rich == nil)
        #expect(try decoded(memory, answer: "").rich == nil)
    }

    // MARK: The contract's own examples

    private func examples() throws -> [String: [[String: Any]]] {
        var url = URL(fileURLWithPath: #filePath)
        while !FileManager.default.fileExists(atPath: url.appendingPathComponent("contracts/message/lio-answer-rich-examples.1.json").path) {
            let parent = url.deletingLastPathComponent()
            try #require(parent != url, "the contracts folder")
            url = parent
        }
        let file = url.appendingPathComponent("contracts/message/lio-answer-rich-examples.1.json")
        let object = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
        return ["valid": try #require(object["valid"] as? [[String: Any]]), "invalid": try #require(object["invalid"] as? [[String: Any]])]
    }

    private func memoryJSON(_ example: [String: Any]) throws -> String? {
        guard let rich = example["rich"] as? [String: Any], let memory = rich["memory"] else { return nil }
        return String(decoding: try JSONSerialization.data(withJSONObject: memory, options: [.fragmentsAllowed]), as: UTF8.self)
    }

    @Test func theValidMemoryExamplesAreReadAsTheContractDescribesThem() throws {
        var seen: [String: LioTimelineWire.Rich] = [:]
        for example in try examples()["valid"] ?? [] {
            guard let memory = try memoryJSON(example), let name = example["name"] as? String else { continue }
            seen[name] = try #require(try decoded(memory).rich, "\(name)")
        }
        #expect(seen["memory prompt only"] == .init(entities: [], memoryPrompt: true))
        #expect(seen["memory used only"]?.memoryUsed == .init(items: [.init(itemID: "mem-71c2", title: "节奏慢")], total: 1))
        #expect(seen["memory prompt and used"]?.memoryPrompt == true)
        #expect(seen["memory prompt and used"]?.memoryUsed?.items.map(\.title) == ["Slow pace", "不吃辣"])
        #expect(seen["memory prompt and used"]?.memoryUsed?.total == 5)
        #expect(seen["everything at once"]?.memoryUsed?.total == 1)
    }

    @Test func theInvalidMemoryExamplesNeverBecomeALineOrAPrompt() throws {
        var checked = 0
        for example in try examples()["invalid"] ?? [] {
            guard let memory = try memoryJSON(example), let name = example["name"] as? String else { continue }
            let rich = try decoded(memory).rich
            if name == "memory carries the remembered text" {
                // The server must not send it; if it did, the App keeps the title and nothing else.
                #expect(rich?.memoryUsed == .init(items: [.init(itemID: "mem-1", title: "x1")], total: 1), "\(name)")
            } else {
                #expect(rich?.memoryUsed == nil && rich?.memoryPrompt != true, "\(name)")
            }
            checked += 1
        }
        #expect(checked >= 8, "the memory examples of the contract")
    }
}
