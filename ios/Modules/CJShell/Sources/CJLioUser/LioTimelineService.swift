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
    let exploration: LioExplorationDisplay?

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
        exploration = nil
        memoryTags = message.memoryTags.filter { LioPublicDisplay.permitsText($0.text) }
        sources = Self.projectSources(message.sources.map { ($0.title, $0.link) }, messageID: message.id)
        status = Self.status(message.state, activity: message.activity, answer: message.answer)
    }

    init(_ message: LioExplorationWire.Message) throws {
        messageID = message.id
        text = message.question
        answer = message.answer
        exploration = try LioExplorationDisplay(message)
        // Native calendar/rich summaries keep their actual type and binding in exploration.trip.
        itinerary = nil
        memoryTags = message.memoryTags.filter { LioPublicDisplay.permitsText($0.text) }
        sources = Self.projectSources(message.sources.map { ($0.title, $0.link) }, messageID: message.id)
        status = Self.status(message.state, activity: message.activity, answer: message.answer)
    }

    private static func projectSources(_ values: [(String, URL?)], messageID: String) -> [LioSource] {
        values.enumerated().compactMap { index, source in
            guard LioPublicDisplay.permitsText(source.0) else { return nil }
            let url = source.1.flatMap { LioPublicDisplay.permitsSource($0) ? $0 : nil }
            return LioSource(id: "\(messageID).\(index)", title: source.0, url: url)
        }
    }

    private static func status(_ state: LioTimelineWire.Message.State, activity: LioTimelineWire.Activity?,
                               answer: String) -> LioTurn.Status {
        switch (state, activity) {
        case (.waiting, _): .thinking
        case (.answering, .places): .working(.places)
        case (.answering, .weather): .working(.weather)
        case (.answering, .travelInformation): .working(.travelInformation)
        case (.answering, nil): answer.isEmpty ? .thinking : .answering
        case (.completed, _): .finished
        case (.serviceLimit, _): .failed(.serviceLimit)
        case (.unavailable, _): .failed(.unavailable)
        }
    }
}

struct LioTimelinePage: Sendable {
    let turns: [LioTimelineTurn]
    let nextBefore: String?
    let conversationID: String?
    static let empty = Self(turns: [], nextBefore: nil, conversationID: nil)

    private init(turns: [LioTimelineTurn], nextBefore: String?, conversationID: String?) {
        self.conversationID = conversationID
        self.turns = turns
        self.nextBefore = nextBefore
    }

    init(_ page: LioTimelineWire.Page) {
        turns = page.messages.map(LioTimelineTurn.init)
        nextBefore = page.nextBefore
        conversationID = page.conversationID
    }

    init(_ page: LioExplorationWire.Page) throws {
        turns = try page.messages.map(LioTimelineTurn.init)
        nextBefore = page.nextBefore
        conversationID = page.conversationID
    }

    init(latest: Self, earlier: [Self]) {
        conversationID = latest.conversationID
        var seen = Set<Data>()
        let ordered = earlier.reversed().flatMap(\.turns) + latest.turns
        turns = Array(ordered.reversed().filter { seen.insert($0.id).inserted }.reversed())
        nextBefore = earlier.isEmpty ? latest.nextBefore : earlier.last?.nextBefore
    }
}

extension LioService {
    public static func signedTimeline(_ client: LioTimelineHTTP) -> LioService {
        timeline(send: { original in
            try await signedSend(client, original)
        }, read: { id, before in
            try await client.timeline(conversationID: id, before: before)
        })
    }

    public static func signedConversation(_ client: LioTimelineHTTP, destination: LioTimelineWire.V2Destination,
                                          didCreate: @escaping @Sendable (String) async -> Void) -> LioService {
        timeline(send: { original in
            try await signedSend(client, original)
        }, read: { id, before in
            try await client.timeline(conversationID: id, before: before, version: .v2)
        }, destination: destination, recoverFirst: { id in
            try await client.reconcileFirstChat(messageID: id)
        }, didCreate: didCreate)
    }

    /// Native4 is selected explicitly; existing public entrypoints retain their original protocol.
    public static func signedExplorationConversation(_ client: LioTimelineHTTP,
        destination: LioTimelineWire.V2Destination, didCreate: @escaping @Sendable (String) async -> Void) -> LioService {
        exploration(send: { original in try await signedSend(client, original) }, read: { id, before in
            try await client.exploration(conversationID: id, before: before)
        }, destination: destination, recoverFirst: { id in
            try await client.reconcileFirstChat(messageID: id)
        }, didCreate: didCreate)
    }

    private static func signedSend(_ client: LioTimelineHTTP, _ original: LioTimelineWire.Send) async throws -> SendResult {
        switch try await client.submit(original) {
        case .accepted(let id): .accepted(conversationID: id)
        case .notSent: .notSent
        case .dailyLimit: .dailyLimit
        case .rejected: .rejected
        }
    }

    enum SendResult: Sendable {
        case accepted(conversationID: String)
        case notSent, dailyLimit, rejected, uncertain
    }

    /// A scoped transport supplies definitive send outcomes and read-only pages.
    /// Uncertain sends are observed through the timeline and never repeated here.
    static func timeline(
        send: @escaping @Sendable (LioTimelineWire.Send) async throws -> SendResult,
        read: @escaping @Sendable (String?, String?) async throws -> LioTimelineWire.Page,
        destination: LioTimelineWire.V2Destination? = nil,
        recoverFirst: @escaping @Sendable (String) async throws -> String? = { _ in nil },
        didCreate: @escaping @Sendable (String) async -> Void = { _ in },
        pollInterval: Duration = .seconds(2),
        observationWindow: Duration = .seconds(90),
        recoveryInterval: Duration = .seconds(15)
    ) -> LioService {
        let session = LioTimelineSession(send: send, read: { id, before in
            LioTimelinePage(try await read(id, before))
        }, destination: destination, recoverFirst: recoverFirst, didCreate: didCreate)
        return service(session: session, pollInterval: pollInterval, observationWindow: observationWindow,
                       recoveryInterval: recoveryInterval)
    }

    static func exploration(
        send: @escaping @Sendable (LioTimelineWire.Send) async throws -> SendResult,
        read: @escaping @Sendable (String?, String?) async throws -> LioExplorationWire.Page,
        destination: LioTimelineWire.V2Destination = .defaultChat,
        recoverFirst: @escaping @Sendable (String) async throws -> String? = { _ in nil },
        didCreate: @escaping @Sendable (String) async -> Void = { _ in },
        pollInterval: Duration = .seconds(2), observationWindow: Duration = .seconds(90),
        recoveryInterval: Duration = .seconds(15)
    ) -> LioService {
        let session = LioTimelineSession(send: send, read: { id, before in
            try LioTimelinePage(await read(id, before))
        }, destination: destination, recoverFirst: recoverFirst, didCreate: didCreate, messageVersion: .v4)
        return service(session: session, pollInterval: pollInterval, observationWindow: observationWindow,
                       recoveryInterval: recoveryInterval)
    }

    private static func service(session: LioTimelineSession, pollInterval: Duration,
                                observationWindow: Duration, recoveryInterval: Duration) -> LioService {
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
                        case .rejected: continuation.yield(.failed(.invalidInput)); return
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
    let read: @Sendable (String?, String?) async throws -> LioTimelinePage
    private let messageVersion: LioTimelineWire.Version
    let destination: LioTimelineWire.V2Destination?
    let recoverFirst: @Sendable (String) async throws -> String?
    let didCreate: @Sendable (String) async -> Void
    private var conversationID: String?
    private var firstOriginal: LioTimelineWire.Send?
    private enum Submission {
        case attempted
        case notSent(LioTimelineWire.Send)
    }

    private var submissions: [Data: Submission] = [:]

    init(send: @escaping @Sendable (LioTimelineWire.Send) async throws -> LioService.SendResult,
         read: @escaping @Sendable (String?, String?) async throws -> LioTimelinePage,
         destination: LioTimelineWire.V2Destination?,
         recoverFirst: @escaping @Sendable (String) async throws -> String?,
         didCreate: @escaping @Sendable (String) async -> Void, messageVersion: LioTimelineWire.Version = .v2) {
        self.messageVersion = messageVersion
        self.send = send
        self.read = read
        self.destination = destination
        self.recoverFirst = recoverFirst
        self.didCreate = didCreate
        if case .some(.existing(let id)) = destination { conversationID = id }
    }

    func submit(_ question: LioQuestion) async throws -> LioService.SendResult {
        if let firstOriginal, !firstOriginal.messageID.utf8.elementsEqual(question.messageID.utf8) {
            // The first send has no confirmed conversation ID. Do not send
            // another first message or attach it to the default conversation.
            throw MessageHTTPFailure.exchangeUnknown
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
                                                    destination: conversationID.map(LioTimelineWire.V2Destination.existing) ?? destination,
                                                    version: messageVersion)
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
            case .dailyLimit, .rejected: firstOriginal = nil
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
        if case .some(.newChat) = destination, conversationID == nil {
            guard let firstOriginal, let id = try await recoverFirst(firstOriginal.messageID) else { return .empty }
            try Task.checkCancellation()
            if conversationID == nil {
                conversationID = id
                self.firstOriginal = nil
                await didCreate(id)
            }
        }
        let page = try await read(conversationID, before)
        try Task.checkCancellation()
        if let id = page.conversationID { conversationID = id }
        return page
    }
}
