import CJMessageHTTP
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
    /// #1727: the ticket of a tap-to-ask chip; `text` is then the chip's label exactly.
    var chipTicket: String?

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
    /// The service rejected this question before accepting it.
    case invalidInput
    case dailyLimit
    case serviceLimit
    /// The service confirmed that this question finished without an answer.
    case unfinished
    /// Delivery or the result is uncertain. A read can resolve it; no new write.
    case waiting
    case unavailable
}

enum LioEvent: Sendable {
    case snapshot(LioTimelinePage)
    case readFailed(LioRequestProblem)
    case sendFailed(LioRequestProblem)
    case activity(LioActivity)
    case text(String)
    case source(LioSource)
    case savedItinerary(LioItinerary)
    /// Debug preview only (#1727): the answer's layout and buttons.
    case layout(LioTimelineWire.AnswerLayout, [LioTimelineWire.Followup], [LioTimelineWire.Chip])
    /// Debug preview only (#1991): the places named in the answer.
    case places([LioPlaceSpan])
    case finished
    case failed(LioFailure)
}

public struct LioService: Sendable {
    let updates: (@Sendable ([Data]) -> AsyncStream<LioTimelineUpdate>)?
    let earlier: (@Sendable (String) async throws -> LioTimelinePage)?
    let events: @Sendable (LioQuestion) -> AsyncStream<LioEvent>

    init(updates: (@Sendable ([Data]) -> AsyncStream<LioTimelineUpdate>)? = nil,
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
    var memoryTags: [LioMemoryWire.Tag] = []
    var exploration: LioExplorationDisplay?
    /// #1727: how the server says this answer is shown, and its fixed buttons (empty unless the build asked for them).
    var layout: LioTimelineWire.AnswerLayout?
    var followups: [LioTimelineWire.Followup] = []
    var chips: [LioTimelineWire.Chip] = []
    /// #1991: words of `answer` the server named as places (empty unless the build asked for them).
    var places: [LioPlaceSpan] = []
    /// #1999: the server says the account has never chosen about memory and this answer holds a preference.
    var memoryPrompt = false
    /// #2001: the line "based on what you asked me to remember" under the answer.
    var memoryNote: LioMemoryUsedNote?
    var fromTimeline = false
    var readFailure: LioRequestProblem?
    var id: Data { question.id }

    var hasTimelineResult: Bool {
        guard fromTimeline else { return false }
        return switch status {
        case .finished, .failed(.dailyLimit), .failed(.serviceLimit), .failed(.unavailable): true
        default: false
        }
    }
}

@MainActor @Observable
final class LioConversation {
    private var service: LioService
    private(set) var sessionSuspended = false
    private(set) var turns: [LioTurn] = []
    private(set) var conversationID: String?
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
    private(set) var hasLoadedTimeline: Bool
    private(set) var timelineUnavailable = false
    private(set) var timelineFailure: LioRequestProblem?
    private var sendGeneration = 0
    private var serviceGeneration = 0
    private var receiving = false

    init(service: LioService) {
        self.service = service
        hasLoadedTimeline = service.updates == nil
    }

    /// Keep the visible conversation while the App retires its authenticated
    /// clients. An unsettled question remains read-only under its original ID.
    func suspendForSessionRefresh() {
        guard !sessionSuspended else { return }
        sessionSuspended = true
        sendGeneration += 1
        serviceGeneration += 1
        if let pending, let index = turns.firstIndex(where: { $0.id == pending.id }) {
            switch turns[index].status {
            case .thinking, .working, .answering, .failed(.waiting):
                turns[index].status = .failed(.waiting)
            case .finished, .failed: break
            }
        }
        pending = nil
        receiving = false
        loadingEarlier = false
    }

    /// The authenticated App composition supplies the newly verified reader.
    /// Rebinding never resubmits a question or recreates the displayed turns.
    func resumeAfterSessionRefresh(service: LioService, restoredUnsentFirst: LioQuestion? = nil) {
        sendGeneration += 1
        serviceGeneration += 1
        if let first = restoredUnsentFirst {
            // The exact question remains in continuity's Unsent card and draft.
            // Never remove a server-read turn or reinterpret an unknown send.
            turns.removeAll { $0.id == first.id && !$0.fromTimeline }
        }
        self.service = service
        sessionSuspended = false
    }

    @discardableResult
    func send(_ text: String, language: LioLanguage, chipTicket: String? = nil) -> Bool {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sessionSuspended, !text.isEmpty, pending == nil else { return false }
        var question = LioQuestion(messageID: UUID().uuidString, text: text, language: language)
        question.chipTicket = chipTicket
        turns.append(LioTurn(question: question))
        sendGeneration += 1
        pending = question
        return true
    }

    func resend(_ id: Data) {
        guard !sessionSuspended, pending == nil,
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
        guard !sessionSuspended, pending == question, !receiving else { return }
        let generation = sendGeneration
        receiving = true
        defer {
            if generation == sendGeneration {
                receiving = false
                pending = nil
            }
        }
        for await event in service.events(question) {
            guard !Task.isCancelled, !sessionSuspended, generation == sendGeneration else { return }
            if case .snapshot(let timeline) = event {
                display(timeline)
                continue
            }
            guard let index = turns.firstIndex(where: { $0.id == question.id }) else { break }
            switch event {
            case .snapshot: break
            case .sendFailed(let failure):
                turns[index].readFailure = failure
                turns[index].status = .failed(.unavailable)
                return
            case .readFailed(let failure):
                turns[index].readFailure = failure
                turns[index].status = .failed(.waiting)
                continue
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
            case .layout(let layout, let followups, let chips):
                turns[index].layout = layout
                turns[index].followups = followups
                turns[index].chips = chips
            case .places(let places):
                turns[index].places = places
            case .finished:
                turns[index].status = .finished
                return
            case .failed(let failure):
                if failure != .waiting || !turns[index].hasTimelineResult {
                    turns[index].status = .failed(failure)
                }
                return
            }
        }
        guard !Task.isCancelled, !sessionSuspended, generation == sendGeneration else { return }
        if let index = turns.firstIndex(where: { $0.id == question.id }), !turns[index].hasTimelineResult {
            turns[index].status = .failed(.waiting)
        }
    }

    func refreshTimeline() async {
        guard !sessionSuspended, pending == nil, let updates = service.updates else { return }
        let generation = sendGeneration
        timelineUnavailable = false
        timelineFailure = nil
        let waiting = turns.compactMap { turn -> Data? in
            switch turn.status {
            case .thinking, .working, .answering, .failed(.waiting): turn.id
            default: nil
            }
        }
        for await update in updates(waiting) {
            guard !Task.isCancelled, generation == sendGeneration, pending == nil else { return }
            switch update {
            case .failed(let problem):
                timelineFailure = problem
                timelineUnavailable = true
            case .snapshot(let timeline):
                display(timeline)
                if !waiting.isEmpty && !timeline.turns.contains(where: \.isActive)
                    && waiting.allSatisfy({ id in turns.contains { $0.id == id && $0.hasTimelineResult } }) {
                    return
                }
            }
        }
        if !Task.isCancelled, generation == sendGeneration, pending == nil, !hasLoadedTimeline {
            timelineUnavailable = true
        }
    }

    func loadEarlier() async -> Data? {
        guard !sessionSuspended, let cursor = nextBefore, let earlier = service.earlier, !loadingEarlier else { return nil }
        let generation = serviceGeneration
        loadingEarlier = true
        earlierUnavailable = false
        defer {
            if generation == serviceGeneration { loadingEarlier = false }
        }
        do {
            let page = try await earlier(cursor)
            guard !Task.isCancelled, !sessionSuspended, generation == serviceGeneration, nextBefore == cursor,
                  let boundary = turns.firstIndex(where: { $0.id == Data(cursor.utf8) }) else { return nil }
            var insertion = boundary
            var firstInserted: Data?
            for row in page.turns.reversed() {
                if let existing = turns.firstIndex(where: { $0.id == row.id }) {
                    let turn = turns[existing]
                    if turn.fromTimeline {
                        if !turn.hasTimelineResult || row.exploration != nil {
                            turns[existing] = makeTurn(row, question: turn.question)
                        }
                        insertion = existing
                    } else {
                        turns.remove(at: existing)
                        if existing < insertion { insertion -= 1 }
                        turns.insert(makeTurn(row, question: turn.question), at: insertion)
                        firstInserted = row.id
                    }
                } else {
                    turns.insert(makeTurn(row), at: insertion)
                    firstInserted = row.id
                }
            }
            nextBefore = page.nextBefore
            return firstInserted
        } catch is CancellationError {
            return nil
        } catch {
            guard !sessionSuspended, generation == serviceGeneration else { return nil }
            earlierUnavailable = true
            return nil
        }
    }

    private func display(_ page: LioTimelinePage) {
        conversationID = page.conversationID
        hasLoadedTimeline = true
        timelineUnavailable = false
        timelineFailure = nil
        let visibleIDs = Set(page.turns.map(\.id))
        let existing = Dictionary(uniqueKeysWithValues: turns.map { ($0.id, $0.question) })
        let previous = turns.filter { $0.fromTimeline && !visibleIDs.contains($0.id) }
        let local = turns.filter { !$0.fromTimeline && !visibleIDs.contains($0.id) }
        let overlaps = turns.contains { $0.fromTimeline && visibleIDs.contains($0.id) }
        if previous.isEmpty || (!visibleIDs.isEmpty && !overlaps) {
            nextBefore = page.nextBefore
        }
        turns = previous + page.turns.map { makeTurn($0, question: existing[$0.id]) } + local
    }

    private func makeTurn(_ row: LioTimelineTurn, question: LioQuestion? = nil) -> LioTurn {
        let question = question ?? LioQuestion(messageID: row.messageID, text: row.text, language: .english)
        return LioTurn(question: question, status: row.status, answer: row.answer,
                       sources: row.sources, itinerary: row.itinerary, memoryTags: row.memoryTags,
                       exploration: row.exploration, layout: row.layout, followups: row.followups, chips: row.chips,
                       places: row.places, memoryPrompt: row.memoryPrompt,
                       memoryNote: row.memoryNote, fromTimeline: true)
    }
}
