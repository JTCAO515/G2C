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

    init(_ page: LioTimelineWire.Page) {
        turns = page.messages.map(LioTimelineTurn.init)
        nextBefore = page.nextBefore
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

    enum SendResult: Sendable {
        case accepted(conversationID: String)
        case notSent, dailyLimit, uncertain
    }

    /// A scoped transport supplies definitive send outcomes and read-only pages.
    /// Uncertain sends are observed through the timeline and never repeated here.
    static func timeline(
        send: @escaping @Sendable (LioTimelineWire.Send) async throws -> SendResult,
        read: @escaping @Sendable (String?, String?) async throws -> LioTimelineWire.Page,
        pollInterval: Duration = .seconds(2),
        observationWindow: Duration = .seconds(90),
        recoveryInterval: Duration = .seconds(15)
    ) -> LioService {
        let session = LioTimelineSession(send: send, read: read)
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
    private var conversationID: String?
    private enum Submission {
        case attempted
        case notSent(LioTimelineWire.Send)
    }

    private var submissions: [Data: Submission] = [:]

    init(send: @escaping @Sendable (LioTimelineWire.Send) async throws -> LioService.SendResult,
         read: @escaping @Sendable (String?, String?) async throws -> LioTimelineWire.Page) {
        self.send = send
        self.read = read
    }

    func submit(_ question: LioQuestion) async throws -> LioService.SendResult {
        let original: LioTimelineWire.Send
        switch (question.isResend, submissions[question.id]) {
        case (true, .notSent(let retry)):
            original = retry
        case (false, .notSent):
            return .notSent
        case (false, nil):
            original = try LioTimelineWire.Send(messageID: question.messageID, text: question.text,
                                                locale: question.language == .english ? .english : .chinese,
                                                conversationID: conversationID)
        default:
            return .uncertain
        }
        submissions[question.id] = .attempted
        do {
            let outcome = try await send(original)
            switch outcome {
            case .accepted(let id): conversationID = id
            case .notSent: submissions[question.id] = .notSent(original)
            case .dailyLimit, .uncertain: break
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
                var knownActive = false
                repeat {
                    do {
                        try Task.checkCancellation()
                        let timeline = try await page()
                        continuation.yield(timeline)
                        knownActive = timeline.turns.contains(where: \.isActive)
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
        let page = try await read(conversationID, before)
        try Task.checkCancellation()
        if let id = page.conversationID { conversationID = id }
        return LioTimelinePage(page)
    }
}
