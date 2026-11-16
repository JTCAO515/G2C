import Foundation
import Observation
import CJMessageHTTP
import Testing
@testable import CJLioUser

@Suite @MainActor
struct LioSessionPresentationTests {
    @Test func suspendingRetainsDisplayedTurnsAndOriginalUncertainQuestionWithoutSending() async throws {
        let model = LioConversation(service: LioService { _ in
            AsyncStream { $0.yield(.text("The existing answer.")); $0.yield(.finished); $0.finish() }
        })
        model.send("Existing question", language: .english)
        let completed = try #require(model.pending)
        await model.receive(completed)
        model.send("北京继续安排", language: .chinese)
        let uncertain = try #require(model.pending)

        model.suspendForSessionRefresh()
        #expect(model.pending == nil)
        #expect(model.turns.map(\.question) == [completed, uncertain])
        #expect(model.turns.first?.answer == "The existing answer.")
        #expect(model.turns.last?.status == .failed(.waiting))
        #expect(model.send("Do not send while checking", language: .english) == false)
        #expect(model.pending == nil)
        #expect(model.turns.count == 2)

        model.resumeAfterSessionRefresh(service: .unavailable)
        #expect(model.pending == nil)
        #expect(model.turns.map(\.question) == [completed, uncertain])
        #expect(model.turns.last?.status == .failed(.waiting))
    }
    @Test func oldSendCallbacksCannotMutateTheRetainedTurnOrClearANewPendingQuestion() async throws {
        let old = AsyncStream<LioEvent>.makeStream()
        let oldStarted = AsyncStream<Void>.makeStream()
        let model = LioConversation(service: LioService { _ in
            oldStarted.continuation.yield(())
            return old.stream
        })
        model.send("Original unsettled question", language: .english)
        let original = try #require(model.pending)
        let oldTask = Task { await model.receive(original) }
        for await _ in oldStarted.stream { break }

        model.suspendForSessionRefresh()
        let current = AsyncStream<LioEvent>.makeStream()
        let currentStarted = AsyncStream<Void>.makeStream()
        model.resumeAfterSessionRefresh(service: LioService { _ in
            currentStarted.continuation.yield(())
            return current.stream
        })
        model.send("Current question", language: .english)
        let question = try #require(model.pending)
        let currentTask = Task { await model.receive(question) }
        for await _ in currentStarted.stream { break }
        old.continuation.yield(.text("A stale answer"))
        old.continuation.yield(.finished)
        await oldTask.value
        #expect(model.turns.first?.answer == "")
        #expect(model.turns.first?.status == .failed(.waiting))
        #expect(model.pending == question)

        current.continuation.yield(.text("A current answer"))
        current.continuation.yield(.finished)
        await currentTask.value
        #expect(model.turns.last?.answer == "A current answer")
        #expect(model.pending == nil)
        old.continuation.finish(); oldStarted.continuation.finish()
        current.continuation.finish(); currentStarted.continuation.finish()
    }

    @Test func renewedReaderQueriesTheOriginalQuestionAndNeverCallsItsSendService() async throws {
        let model = LioConversation(service: .unavailable)
        model.send("北京继续安排", language: .chinese)
        let original = try #require(model.pending)
        model.suspendForSessionRefresh()
        let recorder = SessionReaderRecorder()
        let page = try Self.page(original, answer: "The answer found by reading.")
        model.resumeAfterSessionRefresh(service: LioService(updates: { ids in
            AsyncStream { output in
                Task { await recorder.read(ids); output.yield(.snapshot(page)); output.finish() }
            }
        }, events: { _ in
            AsyncStream { output in Task { await recorder.send(); output.finish() } }
        }))
        await model.refreshTimeline()
        #expect(await recorder.reads == [[original.id]])
        #expect(await recorder.sends == 0)
        #expect(model.pending == nil)
        #expect(model.turns.count == 1)
        #expect(model.turns.first?.question == original)
        #expect(model.turns.first?.answer == "The answer found by reading.")
        #expect(model.turns.first?.status == .finished)
    }

    @Test func suspendedConversationCannotReadUsingTheRetiredService() async throws {
        let recorder = SessionReaderRecorder()
        let model = LioConversation(service: LioService(updates: { ids in
            AsyncStream { output in
                Task { await recorder.read(ids); output.yield(.snapshot(.empty)); output.finish() }
            }
        }, events: { _ in AsyncStream { $0.finish() } }))
        model.suspendForSessionRefresh()
        await model.refreshTimeline()
        #expect(await recorder.reads.isEmpty)
    }


    @Test func retiredEarlierPageCannotInsertRowsOrFinishTheNewReadersBusyState() async throws {
        let latest = LioQuestion(messageID: UUID().uuidString, text: "Latest", language: .english)
        let latestPage = try Self.page(latest, answer: "Latest answer", nextBefore: latest.messageID)
        let stale = LioQuestion(messageID: UUID().uuidString, text: "Stale earlier row", language: .english)
        let current = LioQuestion(messageID: UUID().uuidString, text: "Current earlier row", language: .english)
        let oldPages = AsyncStream<LioTimelinePage>.makeStream()
        let oldStarted = AsyncStream<Void>.makeStream()
        let model = LioConversation(service: LioService(updates: { _ in
            AsyncStream { $0.yield(.snapshot(latestPage)); $0.finish() }
        }, earlier: { _ in
            oldStarted.continuation.yield(())
            for await page in oldPages.stream { return page }
            throw CancellationError()
        }, events: { _ in AsyncStream { $0.finish() } }))
        await model.refreshTimeline()
        let oldTask = Task { await model.loadEarlier() }
        for await _ in oldStarted.stream { break }
        model.suspendForSessionRefresh()
        let newPages = AsyncStream<LioTimelinePage>.makeStream()
        let newStarted = AsyncStream<Void>.makeStream()
        model.resumeAfterSessionRefresh(service: LioService(updates: { _ in
            AsyncStream { $0.yield(.snapshot(latestPage)); $0.finish() }
        }, earlier: { _ in
            newStarted.continuation.yield(())
            for await page in newPages.stream { return page }
            throw CancellationError()
        }, events: { _ in AsyncStream { $0.finish() } }))
        let newTask = Task { await model.loadEarlier() }
        for await _ in newStarted.stream { break }
        oldPages.continuation.yield(try Self.page(stale, answer: "Stale answer"))
        _ = await oldTask.value
        #expect(model.turns.map(\.id) == [latest.id])
        #expect(model.loadingEarlier)
        newPages.continuation.yield(try Self.page(current, answer: "Current answer"))
        _ = await newTask.value
        #expect(model.turns.map(\.id) == [current.id, latest.id])
        #expect(!model.loadingEarlier)
        oldPages.continuation.finish(); oldStarted.continuation.finish()
        newPages.continuation.finish(); newStarted.continuation.finish()
    }


    @Test func suspensionDoesNotDowngradeAnAlreadyConfirmedTimelineAnswer() async throws {
        let events = AsyncStream<LioEvent>.makeStream()
        let changed = AsyncStream<Void>.makeStream()
        let model = LioConversation(service: LioService { _ in events.stream })
        model.send("Confirmed question", language: .english)
        let question = try #require(model.pending)
        let page = try Self.page(question, answer: "Confirmed answer")
        withObservationTracking { _ = model.turns } onChange: { changed.continuation.yield(()) }
        let receiving = Task { await model.receive(question) }
        events.continuation.yield(.snapshot(page))
        for await _ in changed.stream { break }
        #expect(model.turns.first?.status == .finished)
        model.suspendForSessionRefresh()
        #expect(model.turns.first?.status == .finished)
        #expect(model.turns.first?.answer == "Confirmed answer")
        #expect(model.turns.first?.question == question)
        model.resumeAfterSessionRefresh(service: .unavailable, restoredUnsentFirst: question)
        #expect(model.turns.count == 1)
        #expect(model.turns.first?.status == .finished)
        #expect(model.turns.first?.answer == "Confirmed answer")
        events.continuation.finish(); changed.continuation.finish()
        await receiving.value
    }

    private static func page(_ question: LioQuestion, answer: String, nextBefore: String? = nil) throws -> LioTimelinePage {
        let object: [String: Any] = ["version": "LIO-timeline.2",
            "conversation_id": "lio-dialogue-0123456789abcdef0123456789abcdef",
            "messages": [["message_id": question.messageID, "text": question.text,
                          "answer": answer, "status": "completed", "sources": []]],
            "next_before": nextBefore as Any? ?? NSNull()]
        return LioTimelinePage(try LioTimelineWire.decodePage(JSONSerialization.data(withJSONObject: object), version: .v2))
    }

}


private actor SessionReaderRecorder {
    private(set) var reads: [[Data]] = []
    private(set) var sends = 0
    func read(_ ids: [Data]) { reads.append(ids) }
    func send() { sends += 1 }
}
