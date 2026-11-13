import Foundation
import Testing
import CJMessageHTTP
@testable import CJLioUser

struct LioExplorationDisplayTests {
    private func message(_ name: String) throws -> LioExplorationWire.Message {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let file = try Data(contentsOf: root.appendingPathComponent("contracts/message/lio-exploration-examples.4.json"))
        let examples = try #require(JSONSerialization.jsonObject(with: file) as? [String: Any])
        let value = try #require(examples[name])
        return try #require(try LioExplorationWire.decodePage(JSONSerialization.data(withJSONObject: value)).messages.first)
    }

    @Test(arguments: ["en", "zh"])
    func decodedGroupsProduceOneOrderedPartialReplyWithoutAutoSending(_ name: String) throws {
        let raw = try message(name), display = try LioExplorationDisplay(raw)
        #expect(display.presentation.segments.map(\.text) == raw.segments.map(\.text))
        #expect(display.presentation.plainAnswer(questionCount: display.questions.count) == nil)
        var draft = display.draft()
        let group = try #require(draft.questions.first)
        #expect(draft.jointReply.isEmpty)
        draft.toggle(group.options[2], in: group)
        draft.toggle(group.options[0], in: group)
        #expect(draft.jointReply == [raw.questions[0].options[0].sendText, raw.questions[0].options[2].sendText].joined(separator: "\n"))
        #expect(display.presentation.exits.map(\.sendText) == raw.exits.map(\.sendText))
    }

    @Test(arguments: ["waiting", "planning_started"])
    func progressRemainsTypedDataForItsOwner(_ name: String) throws {
        let raw = try message(name), display = try LioExplorationDisplay(raw)
        #expect(display.progress == raw.progress)
        #expect(display.questions.isEmpty)
        #expect(display.state == raw.state)
    }

    @Test func oldVersionsKeepOnlyTheirActualPlainAnswer() throws {
        for version in [LioTimelineWire.Version.v1, .v2] {
            let input = Data("{\"version\":\"LIO-timeline.\(version.rawValue)\",\"conversation_id\":\"lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"messages\":[{\"message_id\":\"old\",\"text\":\"Hello\",\"answer\":\"## Ideas\\n- A quiet walk\",\"status\":\"completed\",\"failure\":null,\"activity\":null,\"sources\":[],\"trip\":null,\"memory\":null}],\"next_before\":null}".utf8)
            let row = try #require(try LioTimelineWire.decodePage(input, version: version).messages.first)
            let display = try LioExplorationDisplay(legacy: row)
            #expect(display.presentation.plainAnswer(questionCount: 0) == row.answer)
            #expect(display.questions.isEmpty && display.presentation.profile.isEmpty && display.progress == nil)
        }
    }
}
