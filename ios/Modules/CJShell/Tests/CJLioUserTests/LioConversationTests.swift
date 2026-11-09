import Foundation
import Testing
@testable import CJLioUser

@Suite @MainActor
struct LioConversationTests {
    @Test func transportFailureResendsTheSameQuestion() async throws {
        let (events, continuation) = AsyncStream<LioEvent>.makeStream()
        let model = LioConversation(service: LioService { _ in events })
        model.send("在上海怎么坐地铁？", language: .chinese)
        let first = try #require(model.pending)
        continuation.yield(.failed(.notSent))
        await model.receive(first)
        model.resend(first.id)
        #expect(model.pending == first)
        #expect(model.turns.count == 1)
        #expect(model.turns.first?.status == .thinking)
        continuation.finish()
    }

    @Test func confirmedFailureCanStartANewQuestion() async throws {
        let model = LioConversation(service: LioService { _ in
            AsyncStream { $0.yield(.failed(.unfinished)); $0.finish() }
        })
        model.send("Where should I stay?", language: .english)
        let first = try #require(model.pending)
        await model.receive(first)
        model.askAgain(first.id)
        let second = try #require(model.pending)
        #expect(second.id != first.id)
        #expect(second.text == first.text)
        #expect(second.language == first.language)
        #expect(model.turns.count == 2)
    }

    @Test func incompleteStreamKeepsPartialAnswerWithoutOfferingAnotherWrite() async throws {
        let model = LioConversation(service: LioService { _ in
            AsyncStream { $0.yield(.text("Take the ")); $0.finish() }
        })
        model.send("Metro?", language: .english)
        let question = try #require(model.pending)
        await model.receive(question)
        model.resend(question.id)
        model.askAgain(question.id)
        #expect(model.pending == nil)
        #expect(model.turns.count == 1)
        #expect(model.turns.first?.answer == "Take the ")
        #expect(model.turns.first?.status == .failed(.waiting))
    }

    @Test func textAndSourcesStayWithTheQuestion() async throws {
        let source = LioSource(id: "1", title: "Metro map", url: nil)
        let model = LioConversation(service: LioService { _ in
            AsyncStream {
                $0.yield(.activity(.directions))
                $0.yield(.text("Take the "))
                $0.yield(.text("metro."))
                $0.yield(.source(source))
                $0.yield(.source(source))
                $0.yield(.finished)
                $0.finish()
            }
        })
        model.send("Metro?", language: .english)
        let question = try #require(model.pending)
        await model.receive(question)
        let turn = try #require(model.turns.first)
        #expect(turn.id == question.id)
        #expect(turn.answer == "Take the metro.")
        #expect(turn.sources == [source])
        #expect(turn.status == .finished)
    }

    @Test func quotaDoesNotOfferResend() async throws {
        let model = LioConversation(service: LioService { _ in
            AsyncStream { $0.yield(.failed(.dailyLimit)); $0.finish() }
        })
        model.send("Metro?", language: .english)
        let question = try #require(model.pending)
        await model.receive(question)
        model.resend(question.id)
        model.askAgain(question.id)
        #expect(model.pending == nil)
        #expect(model.turns.first?.status == .failed(.dailyLimit))
    }
}
