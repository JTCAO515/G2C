import Foundation
import Observation

public enum LioLanguage: Sendable {
    case english, chinese

    func text(_ english: String, _ chinese: String) -> String {
        self == .english ? english : chinese
    }
}

struct LioQuestion: Identifiable, Equatable, Sendable {
    let messageID: String
    let text: String
    let language: LioLanguage
    var isResend = false

    var id: Data { Data(messageID.utf8) }
}

struct LioSource: Identifiable, Equatable, Sendable {
    let id: String
    let title: String
    let url: URL?
}

enum LioActivity: Equatable, Sendable {
    case places, weather, directions, travelInformation
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
    case snapshot(LioTimelinePage)
    case activity(LioActivity)
    case text(String)
    case source(LioSource)
    case savedItinerary(LioItinerary)
    case finished
    case failed(LioFailure)
}

public struct LioService: Sendable {
    let updates: (@Sendable ([Data]) -> AsyncStream<LioTimelinePage>)?
    let earlier: (@Sendable (String) async throws -> LioTimelinePage)?
    let events: @Sendable (LioQuestion) -> AsyncStream<LioEvent>

    init(updates: (@Sendable ([Data]) -> AsyncStream<LioTimelinePage>)? = nil,
         earlier: (@Sendable (String) async throws -> LioTimelinePage)? = nil,
         events: @escaping @Sendable (LioQuestion) -> AsyncStream<LioEvent>) {
        self.updates = updates
        self.earlier = earlier
        self.events = events
    }

    public static let unavailable = LioService { _ in
        AsyncStream { $0.yield(.failed(.unavailable)); $0.finish() }
    }
}

struct LioTurn: Identifiable {
    enum Status: Equatable, Sendable {
        case thinking, working(LioActivity), answering, finished, failed(LioFailure)
    }

    let question: LioQuestion
    var status: Status = .thinking
    var answer = ""
    var sources: [LioSource] = []
    var itinerary: LioItinerary?
    var fromTimeline = false
    var id: Data { question.id }
}

@MainActor @Observable
final class LioConversation {
    private let service: LioService
    private(set) var turns: [LioTurn] = []
    var itineraries: [LioItinerary] {
        var seen: Set<String> = []
        return Array(turns.reversed().compactMap { turn -> LioItinerary? in
            guard let trip = turn.itinerary, seen.insert(trip.id).inserted else { return nil }
            return trip
        }.reversed())
    }
    private(set) var pending: LioQuestion?
    private(set) var nextBefore: String?
    private(set) var loadingEarlier = false
    private(set) var earlierUnavailable = false
    private var sendGeneration = 0
    private var receiving = false

    init(service: LioService) { self.service = service }

    func send(_ text: String, language: LioLanguage) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, pending == nil else { return }
        let question = LioQuestion(messageID: UUID().uuidString, text: text, language: language)
        turns.append(LioTurn(question: question))
        sendGeneration += 1
        pending = question
    }

    func resend(_ id: Data) {
        guard pending == nil,
              let index = turns.firstIndex(where: { $0.id == id }),
              turns[index].status == .failed(.notSent) else { return }
        turns[index].status = .thinking
        sendGeneration += 1
        var question = turns[index].question
        question.isResend = true
        pending = question
    }

    func askAgain(_ id: Data) {
        guard let turn = turns.first(where: { $0.id == id }),
              turn.status == .failed(.unfinished) else { return }
        send(turn.question.text, language: turn.question.language)
    }

    func receive(_ question: LioQuestion) async {
        guard pending == question, !receiving else { return }
        receiving = true
        defer {
            receiving = false
            pending = nil
        }
        for await event in service.events(question) {
            guard !Task.isCancelled else { break }
            if case .snapshot(let timeline) = event {
                display(timeline)
                continue
            }
            guard let index = turns.firstIndex(where: { $0.id == question.id }) else { break }
            switch event {
            case .snapshot: break
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
            case .finished:
                turns[index].status = .finished
                return
            case .failed(let failure):
                turns[index].status = .failed(failure)
                return
            }
        }
        if let index = turns.firstIndex(where: { $0.id == question.id }) {
            turns[index].status = .failed(.waiting)
        }
    }

    func refreshTimeline() async {
        guard pending == nil, let updates = service.updates else { return }
        let generation = sendGeneration
        let waiting = turns.filter { $0.status == .failed(.waiting) }.map(\.id)
        for await timeline in updates(waiting) {
            guard !Task.isCancelled, generation == sendGeneration, pending == nil else { return }
            display(timeline)
        }
    }

    func loadEarlier() async -> Data? {
        guard let cursor = nextBefore, let earlier = service.earlier, !loadingEarlier else { return nil }
        loadingEarlier = true
        earlierUnavailable = false
        defer { loadingEarlier = false }
        do {
            let page = try await earlier(cursor)
            guard !Task.isCancelled, nextBefore == cursor else { return nil }
            let known = Set(turns.map(\.id))
            let older = page.turns.filter { !known.contains($0.id) }
            turns.insert(contentsOf: older.map { makeTurn($0) }, at: 0)
            nextBefore = page.nextBefore
            return older.first?.id
        } catch is CancellationError {
            return nil
        } catch {
            earlierUnavailable = true
            return nil
        }
    }

    private func display(_ page: LioTimelinePage) {
        let visibleIDs = Set(page.turns.map(\.id))
        let existing = Dictionary(uniqueKeysWithValues: turns.map { ($0.id, $0.question) })
        let previous = turns.filter { $0.fromTimeline && !visibleIDs.contains($0.id) }
        let local = turns.filter { !$0.fromTimeline && !visibleIDs.contains($0.id) }
        if previous.isEmpty { nextBefore = page.nextBefore }
        turns = previous + page.turns.map { makeTurn($0, question: existing[$0.id]) } + local
    }

    private func makeTurn(_ row: LioTimelineTurn, question: LioQuestion? = nil) -> LioTurn {
        let question = question ?? LioQuestion(messageID: row.messageID, text: row.text, language: .english)
        return LioTurn(question: question, status: row.status, answer: row.answer,
                       sources: row.sources, itinerary: row.itinerary, fromTimeline: true)
    }
}
