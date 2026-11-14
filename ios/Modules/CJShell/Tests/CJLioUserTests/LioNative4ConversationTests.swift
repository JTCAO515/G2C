import Foundation
import Testing
import CJMessageHTTP
@testable import CJLioUser

@MainActor
struct LioNative4ConversationTests {
    @Test(arguments: ["en", "zh", "structured4_undated", "structured4_dated", "legacy_card2"])
    func actualConversationReceivesTheTypedNative4Presentation(_ name: String) async throws {
        let backend = Native4ConversationBackend(template: try templateBytes(name))
        let service = LioService.exploration(send: { await backend.submit($0) }, read: { id, before in
            try await backend.read(id, before: before)
        }, destination: .newChat, didCreate: { await backend.created($0) }, pollInterval: .milliseconds(2),
           observationWindow: .milliseconds(50))
        let conversation = LioConversation(service: service)
        conversation.send("Start discussing this trip", language: name == "zh" ? .chinese : .english)
        let question = try #require(conversation.pending)
        await conversation.receive(question)
        let turn = try #require(conversation.turns.first)
        let display = try #require(turn.exploration)
        #expect(turn.status == .finished && conversation.pending == nil)
        #expect(conversation.conversationID == "lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        #expect(display.messageID == question.messageID)
        #expect(!display.presentation.segments.isEmpty)
        #expect(display.presentation.answer == turn.answer)
        #expect(turn.itinerary == nil)
        let sent = await backend.originals
        #expect(sent.count == 1)
        let envelope = try #require(JSONSerialization.jsonObject(with: sent[0].originalUTF8) as? [String: Any])
        #expect(envelope["version"] as? String == "LIO-message.4")
        #expect(sent[0].messageID == question.messageID)
        #expect(await backend.creations == ["lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"])
        if name == "en" || name == "zh" {
            #expect(display.presentation.segments.first?.purpose == .direction)
            #expect(display.questions[0].options.map(\.id) == ["interests.history", "interests.food", "interests.nature"])
            #expect(display.presentation.exits.count == 2)
        } else {
            let trip = try #require(display.trip)
            switch (name, trip) {
            case ("legacy_card2", .calendar(let card)): #expect(card.contentVersion == .second)
            case (_, .rich(let card)): #expect(card.tripVersion > 0 && !card.days.isEmpty)
            default: Issue.record("Native trip was replaced by an older presentation")
            }
        }
    }

    @Test func provenNotSentRetriesOnlyTheSameNative4Original() async throws {
        let backend = Native4ConversationBackend(template: try templateBytes("en"), firstNotSent: true)
        let service = LioService.exploration(send: { await backend.submit($0) }, read: { id, before in
            try await backend.read(id, before: before)
        }, destination: .newChat, didCreate: { await backend.created($0) },
           pollInterval: .milliseconds(2), observationWindow: .milliseconds(50))
        let conversation = LioConversation(service: service)
        conversation.send("Se\u{301}jour 北京", language: .english)
        let question = try #require(conversation.pending)
        await conversation.receive(question)
        #expect(conversation.turns.first?.status == .failed(.notSent))
        conversation.resend(question.id)
        let retry = try #require(conversation.pending)
        await conversation.receive(retry)
        #expect(conversation.turns.first?.status == .finished)
        let originals = await backend.originals
        #expect(originals.count == 2 && originals[0].originalUTF8 == originals[1].originalUTF8)
        #expect(originals.allSatisfy { $0.messageID == question.messageID })
        for original in originals {
            let envelope = try #require(JSONSerialization.jsonObject(with: original.originalUTF8) as? [String: Any])
            #expect(envelope["version"] as? String == "LIO-message.4")
        }
        #expect(await backend.creations.count == 1)
    }

    @Test func unsafeProgressAndTripLabelsDoNotEnterThePublicProjection() throws {
        var waiting = try example("waiting")
        var rows = try #require(waiting["messages"] as? [[String: Any]])
        var progress = try #require(rows[0]["progress"] as? [String: Any])
        progress["text"] = "Calling amap tools"
        rows[0]["progress"] = progress; waiting["messages"] = rows
        let page = try decode(waiting)
        #expect(throws: Error.self) { try LioTimelinePage(page) }

        var rich = try example("structured4_undated")
        rows = try #require(rich["messages"] as? [[String: Any]])
        var card = try #require(rows[0]["trip"] as? [String: Any])
        card["title"] = "RUN 42"
        rows[0]["trip"] = card; rich["messages"] = rows
        let badCard = try decode(rich)
        #expect(throws: Error.self) { try LioTimelinePage(badCard) }
    }

    @Test func overlappingOlderNative4PagesRefreshCompletedPresentationData() async throws {
        let feed = Native4PageFeed(template: try templateBytes("en"))
        let service = LioService.exploration(send: { _ in .uncertain }, read: { id, before in
            try await feed.read(id, before: before)
        }, destination: .existing("lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
        let conversation = LioConversation(service: service)
        await conversation.refreshTimeline()
        #expect(conversation.turns.first?.exploration?.presentation.profile.count == 1)
        feed.newWindow = true
        await conversation.refreshTimeline()
        #expect(conversation.turns.first?.id == Data("m1".utf8))
        #expect(conversation.turns.first?.exploration?.presentation.profile.count == 1)
        _ = await conversation.loadEarlier()
        let second = try #require(conversation.turns.first(where: { $0.id == Data("m2".utf8) }))
        #expect(second.status == .finished && second.exploration?.presentation.profile.isEmpty == true)
        _ = await conversation.loadEarlier()
        #expect(conversation.turns.first?.exploration?.presentation.profile.isEmpty == true)
        #expect(conversation.nextBefore == nil && !conversation.earlierUnavailable)
    }

    private func templateBytes(_ name: String) throws -> Data {
        try JSONSerialization.data(withJSONObject: example(name), options: [.sortedKeys, .withoutEscapingSlashes])
    }

    private func example(_ name: String) throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let bytes = try Data(contentsOf: root.appendingPathComponent("contracts/message/lio-exploration-examples.4.json"))
        let fields = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        return try #require(fields[name] as? [String: Any])
    }
    private func decode(_ value: [String: Any]) throws -> LioExplorationWire.Page {
        try LioExplorationWire.decodePage(JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]))
    }
}

private actor Native4ConversationBackend {
    private let template: Data
    private let firstNotSent: Bool
    private(set) var originals: [LioTimelineWire.Send] = []
    private(set) var creations: [String] = []
    init(template: Data, firstNotSent: Bool = false) { self.template = template; self.firstNotSent = firstNotSent }
    func submit(_ original: LioTimelineWire.Send) -> LioService.SendResult {
        originals.append(original)
        if firstNotSent && originals.count == 1 { return .notSent }
        return .accepted(conversationID: "lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    }
    func created(_ id: String) { creations.append(id) }
    func read(_ id: String?, before: String?) throws -> LioExplorationWire.Page {
        #expect(id == "lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" && before == nil)
        let original = try #require(originals.last)
        let input = try #require(JSONSerialization.jsonObject(with: original.originalUTF8) as? [String: Any])
        var value = try #require(JSONSerialization.jsonObject(with: template) as? [String: Any])
        var rows = try #require(value["messages"] as? [[String: Any]])
        rows[0]["message_id"] = original.messageID; rows[0]["text"] = input["text"]
        value["messages"] = rows
        return try LioExplorationWire.decodePage(JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]))
    }
}

@MainActor private final class Native4PageFeed {
    let template: Data
    var newWindow = false
    init(template: Data) { self.template = template }
    func read(_ id: String?, before: String?) throws -> LioExplorationWire.Page {
        #expect(id == "lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        let indices: ClosedRange<Int>
        let next: String?
        switch before {
        case "m22": indices = 2...21; next = "m2"
        case "m2": indices = 1...1; next = nil
        case nil:
            indices = newWindow ? 22...41 : 1...20
            next = newWindow ? "m22" : "m1"
        default: Issue.record("Unexpected cursor"); throw CocoaError(.coderInvalidValue)
        }
        var value = try #require(JSONSerialization.jsonObject(with: template) as? [String: Any])
        let rows = try #require(value["messages"] as? [[String: Any]])
        let original = try #require(rows.first)
        value["messages"] = indices.map { index in
            var row = original
            row["message_id"] = "m\(index)"
            row["profile"] = newWindow ? [] : [["factor_key":"lodging_tier", "display_text":"Enjoys quieter stays", "state":"memory"]]
            return row
        }
        value["next_before"] = next.map { $0 as Any } ?? NSNull()
        return try LioExplorationWire.decodePage(JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]))
    }
}
