import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

@MainActor
struct LioTimelineServiceTests {
    @Test func missingSendResponseReadsTheSameQuestionWithoutPostingAgain() async throws {
        let fixture = TimelineFixture(loseResponse: true)
        let model = LioConversation(service: service(fixture))

        await model.refreshTimeline()
        #expect(model.turns.map { $0.question.messageID } == ["previous"])
        model.send("Where is the metro?", language: .english)
        let question = try #require(model.pending)
        await model.receive(question)

        #expect(model.turns.map { $0.question.messageID } == ["previous", question.messageID])
        #expect(model.turns.last?.answer == "Take the metro.")
        #expect(model.turns.last?.status == .finished)
        #expect(model.turns.last?.sources.first?.url?.host == "example.com")
        let sent = await fixture.sent
        #expect(sent.map(\.messageID) == [question.messageID])
    }

    @Test func showsActivityAndCommittedPrefixWhileWaitingForCompletion() async throws {
        let fixture = TimelineFixture()
        let service = service(fixture)
        let question = LioQuestion(messageID: "activity-test", text: "Where is the metro?", language: .english)
        var snapshots: [LioTimelineTurn] = []
        for await event in service.events(question) {
            if case .snapshot(let rows) = event, let row = rows.last { snapshots.append(row) }
        }

        #expect(snapshots.map(\.answer) == ["Take the ", "Take the metro."])
        #expect(snapshots.first?.status == .working(.travelInformation))
        #expect(snapshots.last?.status == .finished)
    }

    @Test func definitiveLocalFailureReusesIdenticalBytesAfterAnotherQuestion() async throws {
        let fixture = TimelineFixture(firstNotSent: true)
        let model = LioConversation(service: service(fixture))
        model.send("First question", language: .chinese)
        let first = try #require(model.pending)
        await model.receive(first)
        #expect(model.turns.last?.status == .failed(.notSent))

        model.send("Another question", language: .english)
        await model.receive(try #require(model.pending))

        model.resend(first.id)
        await model.receive(try #require(model.pending))

        let sent = await fixture.sent
        #expect(sent.count == 3)
        #expect(sent.first?.messageID == sent.last?.messageID)
        #expect(sent.first?.originalUTF8 == sent.last?.originalUTF8)
        #expect(model.turns.first(where: { $0.id == first.id })?.status == .finished)
    }

    @Test func coldStartFollowsAnExistingAnswerWithoutSendingAnything() async throws {
        let fixture = TimelineFixture()
        let persisted = try LioTimelineWire.Send(messageID: "already-accepted", text: "Metro?", locale: .english)
        await fixture.restore(persisted)
        let model = LioConversation(service: service(fixture))

        await model.refreshTimeline()

        #expect(model.turns.last?.question.messageID == persisted.messageID)
        #expect(model.turns.last?.answer == "Take the metro.")
        #expect(model.turns.last?.status == .finished)
        #expect(await fixture.sent.isEmpty)
    }

    private func service(_ fixture: TimelineFixture) -> LioService {
        .timeline(send: { try await fixture.submit($0) }, read: { try await fixture.read($0) },
                  pollInterval: .milliseconds(1), observationWindow: .seconds(2))
    }
}

private actor TimelineFixture {
    let conversationID = "lio-dialogue-0123456789abcdef0123456789abcdef"
    let loseResponse: Bool
    let firstNotSent: Bool
    private(set) var sent: [LioTimelineWire.Send] = []
    private var accepted: [LioTimelineWire.Send] = []
    private var readCount = 0

    init(loseResponse: Bool = false, firstNotSent: Bool = false) {
        self.loseResponse = loseResponse
        self.firstNotSent = firstNotSent
    }

    func restore(_ send: LioTimelineWire.Send) {
        accepted.append(send)
    }

    func submit(_ send: LioTimelineWire.Send) throws -> LioService.SendResult {
        sent.append(send)
        if firstNotSent, sent.count == 1 { return .notSent }
        accepted.append(send)
        readCount = 0
        if loseResponse { throw URLError(.networkConnectionLost) }
        return .accepted(conversationID: conversationID)
    }

    func read(_ expected: String?) throws -> LioTimelineWire.Page {
        readCount += 1
        var rows: [[String: Any]] = [
            ["message_id": "previous", "text": "Hi", "answer": "Hello", "status": "completed", "sources": []]
        ]
        for send in accepted {
            let payload = try #require(JSONSerialization.jsonObject(with: send.originalUTF8) as? [String: String])
            let done = readCount > 1 || send.messageID != accepted.last?.messageID
            rows.append([
                "message_id": send.messageID,
                "text": try #require(payload["text"]),
                "answer": done ? "Take the metro." : "Take the ",
                "status": done ? "completed" : "answering",
                "activity": done ? NSNull() : "checking_travel_information",
                "sources": done ? [["title": "Metro map", "url": "https://example.com/map"]] : []
            ])
        }
        let data = try JSONSerialization.data(withJSONObject: [
            "version": "LIO-timeline.1", "conversation_id": conversationID, "messages": rows, "next_before": NSNull()
        ])
        return try LioTimelineWire.decodePage(data, for: expected)
    }
}
