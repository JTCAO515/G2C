import Foundation
import Observation

public enum LioLanguage: Sendable {
    case english, chinese

    func text(_ english: String, _ chinese: String) -> String {
        self == .english ? english : chinese
    }
}

struct LioQuestion: Identifiable, Equatable, Sendable {
    let id: UUID
    let text: String
    let language: LioLanguage
}

struct LioSource: Identifiable, Equatable, Sendable {
    let id: String
    let title: String
    let url: URL?
}

enum LioActivity: Equatable, Sendable {
    case places, weather, directions
}

enum LioFailure: Equatable, Sendable {
    /// The service can prove the question wasn't sent; keep its identity.
    case notSent
    case dailyLimit
    /// The service confirmed that this question finished without an answer.
    case unfinished
    /// Delivery or the result is uncertain. A read can resolve it; no new write.
    case waiting
    case unavailable
}

enum LioEvent: Sendable {
    case activity(LioActivity)
    case text(String)
    case source(LioSource)
    case savedItinerary(LioItinerary)
    case finished
    case failed(LioFailure)
}

public struct LioService: Sendable {
    let events: @Sendable (LioQuestion) -> AsyncStream<LioEvent>

    public static let unavailable = LioService { _ in
        AsyncStream { $0.yield(.failed(.unavailable)); $0.finish() }
    }
}

struct LioTurn: Identifiable {
    enum Status: Equatable {
        case thinking, working(LioActivity), answering, finished, failed(LioFailure)
    }

    let question: LioQuestion
    var status: Status = .thinking
    var answer = ""
    var sources: [LioSource] = []
    var itinerary: LioItinerary?
    var id: UUID { question.id }
}

@MainActor @Observable
final class LioConversation {
    private let service: LioService
    private(set) var turns: [LioTurn] = []
    private(set) var itineraries: [LioItinerary] = []
    private(set) var pending: LioQuestion?

    init(service: LioService) { self.service = service }

    func send(_ text: String, language: LioLanguage) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, pending == nil else { return }
        let question = LioQuestion(id: UUID(), text: text, language: language)
        turns.append(LioTurn(question: question))
        pending = question
    }

    func resend(_ id: UUID) {
        guard pending == nil,
              let index = turns.firstIndex(where: { $0.id == id }),
              turns[index].status == .failed(.notSent) else { return }
        turns[index].status = .thinking
        pending = turns[index].question
    }

    func askAgain(_ id: UUID) {
        guard let turn = turns.first(where: { $0.id == id }),
              turn.status == .failed(.unfinished) else { return }
        send(turn.question.text, language: turn.question.language)
    }

    func receive(_ question: LioQuestion) async {
        guard pending?.id == question.id,
              let index = turns.firstIndex(where: { $0.id == question.id }) else { return }
        defer { pending = nil }
        for await event in service.events(question) {
            guard !Task.isCancelled else { break }
            switch event {
            case .activity(let activity):
                if turns[index].answer.isEmpty { turns[index].status = .working(activity) }
            case .text(let text):
                turns[index].status = .answering
                turns[index].answer += text
            case .source(let source):
                if !turns[index].sources.contains(where: { $0.id == source.id }) {
                    turns[index].sources.append(source)
                }
            case .savedItinerary(let itinerary):
                turns[index].itinerary = itinerary
                if let savedIndex = itineraries.firstIndex(where: { $0.id == itinerary.id }) {
                    itineraries[savedIndex] = itinerary
                } else {
                    itineraries.append(itinerary)
                }
            case .finished:
                turns[index].status = .finished
                return
            case .failed(let failure):
                turns[index].status = .failed(failure)
                return
            }
        }
        turns[index].status = .failed(.waiting)
    }
}
