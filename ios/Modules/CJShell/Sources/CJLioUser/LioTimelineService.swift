import CJMessageHTTP
import Foundation

struct LioTimelineTurn: Sendable {
    let messageID: String
    var id: Data { Data(messageID.utf8) }
    let text: String
    let answer: String
    let status: LioTurn.Status
    let sources: [LioSource]
    let itinerary: LioItinerary?
    let memoryTags: [LioMemoryWire.Tag]

    var isActive: Bool {
        switch status {
        case .thinking, .working, .answering: true
        case .finished, .failed: false
        }
    }

    init(_ message: LioTimelineWire.Message) {
        messageID = message.id
        text = message.question
        answer = message.answer
        itinerary = message.trip.map(LioItinerary.init)
        // A choice is available only when its description is safe to show.
        memoryTags = message.memoryTags.filter { LioPublicDisplay.permitsText($0.text) }
        sources = message.sources.enumerated().compactMap { index, source in
            guard LioPublicDisplay.permitsText(source.title) else { return nil }
            let url = source.link.flatMap { LioPublicDisplay.permitsSource($0) ? $0 : nil }
            return LioSource(id: "\(message.id).\(index)", title: source.title, url: url)
        }
        switch (message.state, message.activity) {
        case (.waiting, _): status = .thinking
        case (.answering, .places): status = .working(.places)
        case (.answering, .weather): status = .working(.weather)
        case (.answering, .travelInformation): status = .working(.travelInformation)
        case (.answering, nil): status = message.answer.isEmpty ? .thinking : .answering
        case (.completed, _): status = .finished
        case (.unavailable, _): status = .failed(.unavailable)
        }
    }
}

struct LioTimelinePage: Sendable {
    let turns: [LioTimelineTurn]
    let nextBefore: String?
    static let empty = Self(turns: [], nextBefore: nil)

    private init(turns: [LioTimelineTurn], nextBefore: String?) {
        self.turns = turns
        self.nextBefore = nextBefore
    }

    init(_ page: LioTimelineWire.Page) {
        turns = page.messages.map(LioTimelineTurn.init)
        nextBefore = page.nextBefore
    }

    init(latest: Self, earlier: [Self]) {
        var seen = Set<Data>()
        let ordered = earlier.reversed().flatMap(\.turns) + latest.turns
        turns = Array(ordered.reversed().filter { seen.insert($0.id).inserted }.reversed())
        nextBefore = earlier.isEmpty ? latest.nextBefore : earlier.last?.nextBefore
    }
}

extension LioService {
    public static func signedTimeline(_ client: LioTimelineHTTP) -> LioService {
        timeline(send: { original in
            switch try await client.submit(original) {
            case .accepted(let id): .accepted(conversationID: id)
            case .notSent: .notSent
            case .dailyLimit: .dailyLimit
            }
        }, read: { id, before in
            try await client.timeline(conversationID: id, before: before)
        })
    }

    public static func signedConversation(_ client: LioTimelineHTTP, destination: LioTimelineWire.V2Destination,
                                          didCreate: @escaping @Sendable (String) async -> Void) -> LioService {
        timeline(send: { original in
            switch try await client.submit(original) {
            case .accepted(let id): .accepted(conversationID: id)
            case .notSent: .notSent
            case .dailyLimit: .dailyLimit
            }
        }, read: { id, before in
            try await client.timeline(conversationID: id, before: before, version: .v2)
        }, destination: destination, didCreate: didCreate)
    }

    enum SendResult: Sendable {
        case accepted(conversationID: String)
        case notSent, dailyLimit, uncertain
    }

    /// A scoped transport supplies definitive send outcomes and read-only pages.
    /// Uncertain sends are observed through the timeline and never repeated here.
    static func timeline(
        send: @escaping @Sendable (LioTimelineWire.Send) async throws -> SendResult,
        read: @escaping @Sendable (String?, String?) async throws -> LioTimelineWire.Page,
        destination: LioTimelineWire.V2Destination? = nil,
        didCreate: @escaping @Sendable (String) async -> Void = { _ in },
        pollInterval: Duration = .seconds(2),
        observationWindow: Duration = .seconds(90),
        recoveryInterval: Duration = .seconds(15)
    ) -> LioService {
        let session = LioTimelineSession(send: send, read: read, destination: destination, didCreate: didCreate)
        return LioService(updates: { waiting in
            session.observe(waiting: waiting, interval: pollInterval, window: observationWindow,
                            recoveryInterval: waiting.isEmpty ? nil : recoveryInterval)
        }, earlier: { cursor in
            try await session.page(before: cursor)
        }) { question in
            AsyncStream { continuation in
                let task = Task {
                    defer { continuation.finish() }
                    do {
                        switch try await session.submit(question) {
                        case .dailyLimit: continuation.yield(.failed(.dailyLimit)); return
                        case .notSent: continuation.yield(.failed(.notSent)); return
                        case .accepted, .uncertain: break
                        }
                        for await timeline in session.observe(waiting: [question.id], interval: pollInterval,
                                                                window: observationWindow) {
                            try Task.checkCancellation()
                            continuation.yield(.snapshot(timeline))
                            if let status = timeline.turns.first(where: { $0.id == question.id })?.status {
                                switch status {
                                case .finished: continuation.yield(.finished); return
                                case .failed(let failure): continuation.yield(.failed(failure)); return
                                default: break
                                }
                            }
                        }
                        continuation.yield(.failed(.waiting))
                    } catch is CancellationError {
                        return
                    } catch {
                        continuation.yield(.failed(.unavailable))
                    }
                }
                continuation.onTermination = { _ in task.cancel() }
            }
        }
    }
}

private actor LioTimelineSession {
    let send: @Sendable (LioTimelineWire.Send) async throws -> LioService.SendResult
    let read: @Sendable (String?, String?) async throws -> LioTimelineWire.Page
    let destination: LioTimelineWire.V2Destination?
    let didCreate: @Sendable (String) async -> Void
    private var conversationID: String?
    private var firstOriginal: LioTimelineWire.Send?
    private enum Submission {
        case attempted
        case notSent(LioTimelineWire.Send)
    }

    private var submissions: [Data: Submission] = [:]

    init(send: @escaping @Sendable (LioTimelineWire.Send) async throws -> LioService.SendResult,
         read: @escaping @Sendable (String?, String?) async throws -> LioTimelineWire.Page,
         destination: LioTimelineWire.V2Destination?, didCreate: @escaping @Sendable (String) async -> Void) {
        self.send = send
        self.read = read
        self.destination = destination
        self.didCreate = didCreate
        if case .some(.existing(let id)) = destination { conversationID = id }
    }

    func submit(_ question: LioQuestion) async throws -> LioService.SendResult {
        if let firstOriginal, !firstOriginal.messageID.utf8.elementsEqual(question.messageID.utf8) {
            // The first send has no confirmed conversation ID. Do not send
            // another first message or attach it to the default conversation.
            return .uncertain
        }
        let original: LioTimelineWire.Send
        switch (question.isResend, submissions[question.id]) {
        case (true, .notSent(let retry)):
            original = retry
        case (false, .notSent):
            return .notSent
        case (false, nil):
            let locale: LioTimelineWire.Locale = question.language == .english ? .english : .chinese
            if let destination {
                original = try LioTimelineWire.Send(messageID: question.messageID, text: question.text, locale: locale,
                                                    destination: conversationID.map(LioTimelineWire.V2Destination.existing) ?? destination)
            } else {
                original = try LioTimelineWire.Send(messageID: question.messageID, text: question.text,
                                                    locale: locale, conversationID: conversationID)
            }
        default:
            return .uncertain
        }
        if case .some(.newChat) = destination, conversationID == nil { firstOriginal = original }
        submissions[question.id] = .attempted
        do {
            let outcome = try await send(original)
            switch outcome {
            case .accepted(let id):
                let created = firstOriginal != nil
                conversationID = id
                firstOriginal = nil
                if created { await didCreate(id) }
            case .notSent: submissions[question.id] = .notSent(original)
            case .dailyLimit: firstOriginal = nil
            case .uncertain: break
            }
            return outcome
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            return .uncertain
        }
    }

    nonisolated func observe(waiting: [Data], interval: Duration, window: Duration,
                             recoveryInterval: Duration? = nil) -> AsyncStream<LioTimelinePage> {
        AsyncStream { continuation in
            let task = Task {
                defer { continuation.finish() }
                let clock = ContinuousClock()
                let deadline = clock.now.advanced(by: window)
                let waitingIDs = Set(waiting)
                var boundary: String?
                var earlier: [(before: String, page: LioTimelinePage)] = []
                var nextRefresh = 0
                var knownActive = false
                repeat {
                    do {
                        try Task.checkCancellation()
                        let latest = try await page()
                        if !waitingIDs.isEmpty {
                            if boundary != latest.nextBefore {
                                boundary = latest.nextBefore
                                earlier.removeAll()
                            }
                            let seen = Set(latest.turns.map(\.id) + earlier.flatMap { $0.page.turns.map(\.id) })
                            let cursor = earlier.isEmpty ? latest.nextBefore : earlier.last?.page.nextBefore
                            if !waitingIDs.isSubset(of: seen), let cursor {
                                // Follow at most one older page on each read cycle.
                                earlier.append((cursor, try await page(before: cursor)))
                            } else {
                                let active = earlier.indices.filter { index in
                                    earlier[index].page.turns.contains { $0.isActive && waitingIDs.contains($0.id) }
                                }
                                if !active.isEmpty {
                                    let index = active[nextRefresh % active.count]
                                    nextRefresh += 1
                                    let cursor = earlier[index].before
                                    earlier[index].page = try await page(before: cursor)
                                }
                            }
                        }
                        let timeline = earlier.isEmpty ? latest : LioTimelinePage(latest: latest, earlier: earlier.map(\.page))
                        continuation.yield(timeline)
                        knownActive = latest.turns.contains(where: \.isActive)
                            || earlier.contains { $0.page.turns.contains { $0.isActive && waitingIDs.contains($0.id) } }
                        if !knownActive && waiting.allSatisfy({ id in timeline.turns.contains { $0.id == id } }) {
                            return
                        }
                    } catch is CancellationError {
                        return
                    } catch {
                        // A failed observation grants no further send.
                        knownActive = false
                    }
                    let withinWindow = clock.now < deadline
                    guard knownActive || withinWindow || recoveryInterval != nil else { return }
                    let delay = if knownActive || withinWindow {
                        interval
                    } else {
                        // The foreground observer keeps only read access after the send task ends.
                        recoveryInterval ?? interval
                    }
                    do {
                        try await clock.sleep(for: delay)
                    } catch {
                        return
                    }
                } while !Task.isCancelled
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    func page(before: String? = nil) async throws -> LioTimelinePage {
        if case .some(.newChat) = destination, conversationID == nil { return .empty }
        let page = try await read(conversationID, before)
        try Task.checkCancellation()
        if let id = page.conversationID { conversationID = id }
        return LioTimelinePage(page)
    }
}
