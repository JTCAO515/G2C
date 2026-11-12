import CJMessageHTTP
import Foundation
import Testing
@testable import CJLioUser

@MainActor
struct LioTimelineServiceTests {
    @Test func historyIsUnknownUntilARealSnapshotArrives() async throws {
        let fixture = TimelineFixture()
        let model = LioConversation(service: service(fixture))
        #expect(!model.hasLoadedTimeline && !model.timelineUnavailable)
        await model.refreshTimeline()
        #expect(model.hasLoadedTimeline && !model.timelineUnavailable)
        #expect(model.turns.map { $0.question.messageID } == ["previous"])
    }

    @Test func aKnownEmptyConversationCanShowItsFirstWelcome() async {
        let service = LioService(updates: { _ in AsyncStream { $0.yield(.empty); $0.finish() } }) { _ in
            Issue.record("Welcome checks cannot send a question")
            return AsyncStream { $0.finish() }
        }
        let model = LioConversation(service: service)
        await model.refreshTimeline()
        #expect(model.hasLoadedTimeline && !model.timelineUnavailable && model.turns.isEmpty)
    }

    @Test func anObservationWithoutDataIsNotAnEmptyNewConversation() async {
        let service = LioService(updates: { _ in AsyncStream { $0.finish() } }) { _ in
            Issue.record("A failed history read cannot send")
            return AsyncStream { $0.finish() }
        }
        let model = LioConversation(service: service)
        await model.refreshTimeline()
        #expect(!model.hasLoadedTimeline && model.timelineUnavailable && model.turns.isEmpty)
    }

    @Test func cancelledHistoryDoesNotInventAFailureOrAnEmptyHistory() async {
        let service = LioService(updates: { _ in AsyncStream { _ in } }) { _ in AsyncStream { $0.finish() } }
        let model = LioConversation(service: service)
        let observation = Task { await model.refreshTimeline() }
        await Task.yield()
        observation.cancel()
        await observation.value
        #expect(!model.hasLoadedTimeline && !model.timelineUnavailable)
    }

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
            if case .snapshot(let rows) = event, let row = rows.turns.last { snapshots.append(row) }
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

    @Test func timelineServiceLimitDoesNotClaimDailyCapOrAllowAnotherWrite() async throws {
        let fixture = TimelineFixture(serviceLimit: true)
        let model = LioConversation(service: service(fixture))
        model.send("Where is the metro?", language: .english)
        let question = try #require(model.pending)
        await model.receive(question)

        #expect(model.turns.last?.status == .failed(.serviceLimit))
        #expect(model.turns.last?.hasTimelineResult == true)
        model.resend(question.id)
        model.askAgain(question.id)
        #expect(model.pending == nil)
        #expect(await fixture.sent.map(\.messageID) == [question.messageID])
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

    @Test func restartedObservationDoesNotSubmitAnAlreadyAttemptedQuestion() async throws {
        let fixture = TimelineFixture(loseResponse: true)
        let service = service(fixture)
        let question = LioQuestion(messageID: "restart", text: "Metro?", language: .english)
        for await _ in service.events(question) {}
        for await _ in service.events(question) {}
        #expect(await fixture.sent.map(\.messageID) == [question.messageID])
    }

    @Test func blankV2ConversationBecomesScopedOnlyAfterTheFirstReceipt() async throws {
        let fixture = TimelineFixture()
        let service = LioService.timeline(
            send: { try await fixture.submit($0) }, read: { try await fixture.read($0, before: $1, version: .v2) },
            destination: .newChat, didCreate: { await fixture.recordCreated($0) },
            pollInterval: .milliseconds(1), observationWindow: .seconds(2))
        let model = LioConversation(service: service)
        await model.refreshTimeline()
        #expect(model.turns.isEmpty)
        #expect(await fixture.v2Reads.isEmpty)
        model.send("First question", language: .english)
        await model.receive(try #require(model.pending))
        model.send("Next question", language: .english)
        await model.receive(try #require(model.pending))

        let sent = await fixture.sent
        try #require(sent.count == 2)
        let first = try #require(JSONSerialization.jsonObject(with: sent[0].originalUTF8) as? [String: Any])
        let second = try #require(JSONSerialization.jsonObject(with: sent[1].originalUTF8) as? [String: Any])
        #expect(first["new_conversation"] as? Bool == true && first["conversation_id"] == nil)
        #expect(second["conversation_id"] as? String == fixture.conversationID && second["new_conversation"] == nil)
        #expect(await fixture.v2Reads.allSatisfy { $0 == fixture.conversationID })
        #expect(await fixture.created == [fixture.conversationID])
        #expect(model.turns.count == 2 && model.turns.allSatisfy { $0.status == .finished })
    }

    @Test func rejectedFirstV2SendAllowsAnotherQuestionInTheBlankChat() async throws {
        let fixture = TimelineFixture(firstRejected: true)
        let service = LioService.timeline(
            send: { try await fixture.submit($0) }, read: { try await fixture.read($0, before: $1, version: .v2) },
            destination: .newChat, didCreate: { await fixture.recordCreated($0) },
            pollInterval: .milliseconds(1), observationWindow: .seconds(2))
        let model = LioConversation(service: service)
        model.send("First question", language: .english)
        let first = try #require(model.pending)
        await model.receive(first)
        #expect(model.turns.last?.status == .failed(.invalidInput))
        #expect(await fixture.v2Reads.isEmpty)

        model.send("Another question", language: .english)
        let next = try #require(model.pending)
        await model.receive(next)
        #expect(model.turns.first(where: { $0.id == next.id })?.status == .finished)
        #expect(model.turns.first(where: { $0.id == first.id })?.status == .failed(.invalidInput))
        #expect(await fixture.sent.map(\.messageID) == [first.messageID, next.messageID])
        #expect(await fixture.v2Reads.allSatisfy { $0 == fixture.conversationID })
        #expect(await fixture.created == [fixture.conversationID])
    }

    @Test func uncertainFirstV2SendNeverReadsDefaultOrCreatesAnotherConversation() async throws {
        let fixture = TimelineFixture(loseResponse: true)
        let service = LioService.timeline(
            send: { try await fixture.submit($0) }, read: { try await fixture.read($0, before: $1, version: .v2) },
            destination: .newChat, recoverFirst: { await fixture.lookupFirst($0) },
            didCreate: { await fixture.recordCreated($0) }, pollInterval: .milliseconds(1),
            observationWindow: .milliseconds(3), recoveryInterval: .milliseconds(1))
        let model = LioConversation(service: service)
        model.send("First question", language: .english)
        let first = try #require(model.pending)
        await model.receive(first)
        #expect(model.turns.last?.status == .failed(.waiting))
        model.send("Another question", language: .english)
        await model.receive(try #require(model.pending))

        #expect(await fixture.sent.map(\.messageID) == [first.messageID])
        #expect(await fixture.v2Reads.isEmpty)
        #expect(await fixture.created.isEmpty)

        await fixture.publishFirstReceipt()
        await model.refreshTimeline()

        #expect(await fixture.sent.map(\.messageID) == [first.messageID])
        #expect(await fixture.v2Reads.allSatisfy { $0 == fixture.conversationID })
        #expect(await fixture.created == [fixture.conversationID])
        #expect(model.turns.first?.status == .finished)
    }

    @Test func reconnectAfterTheSendWindowRecoversTheAnswerWithoutAnotherWrite() async throws {
        let fixture = TimelineFixture(loseResponse: true)
        await fixture.disconnect()
        let service = LioService.timeline(
            send: { try await fixture.submit($0) }, read: { try await fixture.read($0, before: $1) },
            pollInterval: .milliseconds(10), observationWindow: .milliseconds(2),
            recoveryInterval: .milliseconds(1))
        let model = LioConversation(service: service)
        model.send("Metro?", language: .english)
        let question = try #require(model.pending)

        await model.receive(question)
        #expect(model.turns.last?.status == .failed(.waiting))
        #expect(model.pending == nil)

        // A foreground read must survive beyond its own short observation window.
        await fixture.reconnectAfterReads(4)
        await model.refreshTimeline()

        #expect(model.turns.last?.status == .finished)
        #expect(model.turns.last?.answer == "Take the metro.")
        #expect(await fixture.sent.map(\.messageID) == [question.messageID])
    }

    @Test func reconnectFollowsAnOlderActiveAnswerWithoutManualHistoryOrAnotherWrite() async throws {
        let fixture = TimelineFixture(loseResponse: true, firstAnswerNeedsOlderReads: 2)
        await fixture.disconnect()
        let service = LioService.timeline(
            send: { try await fixture.submit($0) }, read: { try await fixture.read($0, before: $1) },
            pollInterval: .milliseconds(1), observationWindow: .milliseconds(12),
            recoveryInterval: .milliseconds(1))
        let model = LioConversation(service: service)
        model.send("在哪里坐地铁？", language: .chinese)
        let question = try #require(model.pending)
        await model.receive(question)
        #expect(model.turns.last?.status == .failed(.waiting))

        for index in 1...45 {
            await fixture.restore(try LioTimelineWire.Send(messageID: "other-\(index)", text: "Metro?", locale: .english))
        }
        await fixture.reconnectAfterReads(0)
        await model.refreshTimeline()

        #expect(model.turns.map { $0.question.messageID } == ["previous", question.messageID] + (1...45).map { "other-\($0)" })
        let recovered = try #require(model.turns.first { $0.id == question.id })
        #expect(recovered.status == .finished)
        #expect(recovered.question.language == .chinese)
        #expect(recovered.answer == "Take the metro.")
        #expect(await fixture.olderRequests == ["other-26", "other-6", "other-6"])
        #expect(await fixture.sent.map(\.messageID) == [question.messageID])
    }

    @Test func olderPagesRemainInOrderAfterRefreshingTheLatestPage() async throws {
        let fixture = TimelineFixture()
        for index in 1...45 {
            await fixture.restore(try LioTimelineWire.Send(messageID: "message-\(index)", text: "Metro?", locale: .english))
        }
        let model = LioConversation(service: service(fixture))
        await model.refreshTimeline()
        #expect(model.turns.count == 20)
        #expect(model.nextBefore == "message-26")

        _ = await model.loadEarlier()
        _ = await model.loadEarlier()
        #expect(model.nextBefore == nil)
        await model.refreshTimeline()

        #expect(model.turns.map { $0.question.messageID } == ["previous"] + (1...45).map { "message-\($0)" })
        #expect(await fixture.olderRequests == ["message-26", "message-6"])
        #expect(await fixture.sent.isEmpty)
    }

    @Test func fillsTheGapWhenAnotherDeviceAddsAWholePage() async throws {
        let fixture = TimelineFixture()
        for index in 1...20 {
            await fixture.restore(try LioTimelineWire.Send(messageID: "message-\(index)", text: "Metro?", locale: .english))
        }
        let model = LioConversation(service: service(fixture))
        await model.refreshTimeline()
        #expect(model.nextBefore == "message-1")

        for index in 21...60 {
            await fixture.restore(try LioTimelineWire.Send(messageID: "message-\(index)", text: "Metro?", locale: .english))
        }
        await model.refreshTimeline()
        #expect(model.nextBefore == "message-41")

        let inserted = await model.loadEarlier()

        #expect(inserted == Data("message-21".utf8))
        #expect(model.turns.map { $0.question.messageID } == (1...60).map { "message-\($0)" })
        #expect(await fixture.olderRequests == ["message-41"])
        #expect(await fixture.sent.isEmpty)
    }

    @Test func insertsHistoryBeforeKnownRowsWhenAnOlderPagePartlyOverlaps() async throws {
        let fixture = TimelineFixture()
        for index in 1...120 {
            await fixture.restore(try LioTimelineWire.Send(messageID: "message-\(index)", text: "Metro?", locale: .english))
        }
        let model = LioConversation(service: service(fixture))
        await model.refreshTimeline()
        #expect(model.nextBefore == "message-101")

        for index in 121...145 {
            await fixture.restore(try LioTimelineWire.Send(messageID: "message-\(index)", text: "Metro?", locale: .english))
        }
        await model.refreshTimeline()
        #expect(model.nextBefore == "message-126")

        _ = await model.loadEarlier()
        let firstNew = await model.loadEarlier()

        #expect(firstNew == Data("message-86".utf8))
        #expect(model.turns.map { $0.question.messageID } == (86...145).map { "message-\($0)" })
        #expect(await fixture.olderRequests == ["message-126", "message-106"])
        #expect(await fixture.sent.isEmpty)
    }

    @Test func earlierPageReplacesAWaitingPlaceholderWithTheConfirmedAnswer() async throws {
        let fixture = TimelineFixture(loseResponse: true)
        await fixture.disconnect()
        let actual = LioService.timeline(
            send: { try await fixture.submit($0) }, read: { try await fixture.read($0, before: $1) },
            pollInterval: .milliseconds(10), observationWindow: .milliseconds(2))
        let (latest, continuation) = AsyncStream<LioTimelinePage>.makeStream()
        let model = LioConversation(service: LioService(
            updates: { _ in latest }, earlier: actual.earlier, events: actual.events
        ))
        model.send("在哪里坐地铁？", language: .chinese)
        let question = try #require(model.pending)
        await model.receive(question)
        #expect(model.turns.last?.status == .failed(.waiting))

        for index in 1...25 {
            await fixture.restore(try LioTimelineWire.Send(messageID: "other-\(index)", text: "Metro?", locale: .english))
        }
        await fixture.reconnectAfterReads(0)
        let page = try await fixture.read(nil, before: nil)
        continuation.yield(LioTimelinePage(page))
        continuation.finish()
        await model.refreshTimeline()
        #expect(model.nextBefore == "other-6")

        _ = await model.loadEarlier()

        #expect(model.turns.map { $0.question.messageID } == ["previous", question.messageID] + (1...25).map { "other-\($0)" })
        let recovered = try #require(model.turns.first { $0.id == question.id })
        #expect(recovered.question.language == .chinese)
        #expect(recovered.status == .finished)
        #expect(recovered.answer == "Take the metro.")
        #expect(await fixture.sent.map(\.messageID) == [question.messageID])
    }

    private func service(_ fixture: TimelineFixture) -> LioService {
        .timeline(send: { try await fixture.submit($0) }, read: { try await fixture.read($0, before: $1) },
                  pollInterval: .milliseconds(1), observationWindow: .seconds(2))
    }
}

private actor TimelineFixture {
    let conversationID = "lio-dialogue-0123456789abcdef0123456789abcdef"
    let loseResponse: Bool
    let firstNotSent: Bool
    let firstRejected: Bool
    let serviceLimit: Bool
    let firstAnswerNeedsOlderReads: Int
    private(set) var olderRequests: [String] = []
    private(set) var sent: [LioTimelineWire.Send] = []
    private(set) var v2Reads: [String?] = []
    private(set) var created: [String] = []
    private var accepted: [LioTimelineWire.Send] = []
    private var readCount = 0
    private var readsUntilConnection: Int?
    private var firstReceiptVisible = false

    init(loseResponse: Bool = false, firstNotSent: Bool = false, firstRejected: Bool = false, serviceLimit: Bool = false,
         firstAnswerNeedsOlderReads: Int = 0) {
        self.loseResponse = loseResponse
        self.firstNotSent = firstNotSent
        self.firstRejected = firstRejected
        self.serviceLimit = serviceLimit
        self.firstAnswerNeedsOlderReads = firstAnswerNeedsOlderReads
    }

    func disconnect() { readsUntilConnection = .max }

    func reconnectAfterReads(_ count: Int) { readsUntilConnection = count }

    func restore(_ send: LioTimelineWire.Send) {
        accepted.append(send)
    }

    func recordCreated(_ id: String) { created.append(id) }

    func publishFirstReceipt() { firstReceiptVisible = true }

    func lookupFirst(_ id: String) -> String? {
        guard firstReceiptVisible, accepted.first?.messageID == id else { return nil }
        return conversationID
    }

    func submit(_ send: LioTimelineWire.Send) throws -> LioService.SendResult {
        sent.append(send)
        if firstNotSent, sent.count == 1 { return .notSent }
        if firstRejected, sent.count == 1 { return .rejected }
        accepted.append(send)
        readCount = 0
        if loseResponse { throw URLError(.networkConnectionLost) }
        return .accepted(conversationID: conversationID)
    }

    func read(_ expected: String?, before: String?, version: LioTimelineWire.Version = .v1) throws -> LioTimelineWire.Page {
        if let readsUntilConnection, readsUntilConnection > 0 {
            self.readsUntilConnection = readsUntilConnection - 1
            throw URLError(.notConnectedToInternet)
        }
        readCount += 1
        if version == .v2 { v2Reads.append(expected) }
        var rows: [[String: Any]] = version == .v1 ? [
            ["message_id": "previous", "text": "Hi", "answer": "Hello", "status": "completed", "sources": []]
        ] : []
        for send in accepted {
            let payload = try #require(JSONSerialization.jsonObject(with: send.originalUTF8) as? [String: Any])
            let text = try #require(payload["text"] as? String)
            if serviceLimit {
                rows.append(["message_id": send.messageID, "text": text, "answer": "",
                             "status": "failed", "failure": "quota", "sources": []])
                continue
            }
            let held = send.messageID == accepted.first?.messageID && olderRequests.count < firstAnswerNeedsOlderReads
            let done = !held && (readCount > 1 || send.messageID != accepted.last?.messageID)
            rows.append([
                "message_id": send.messageID,
                "text": text,
                "answer": done ? "Take the metro." : "Take the ",
                "status": done ? "completed" : "answering",
                "activity": done ? NSNull() : "checking_travel_information",
                "sources": done ? [["title": "Metro map", "url": "https://example.com/map"]] : []
            ])
        }
        if let before {
            olderRequests.append(before)
            let boundary = try #require(rows.firstIndex { $0["message_id"] as? String == before })
            rows = Array(rows.prefix(boundary))
        }
        let visible = Array(rows.suffix(20))
        let cursor: Any = rows.count > visible.count ? try #require(visible.first?["message_id"]) : NSNull()
        let data = try JSONSerialization.data(withJSONObject: [
            "version": "LIO-timeline.\(version.rawValue)", "conversation_id": conversationID, "messages": visible, "next_before": cursor
        ])
        return try LioTimelineWire.decodePage(data, for: expected, version: version)
    }
}
