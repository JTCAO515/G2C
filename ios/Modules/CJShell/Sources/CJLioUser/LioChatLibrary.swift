import CJMessageHTTP
import Foundation
import Observation

public struct LioChatSession: Identifiable, Sendable {
    public let id: Data
    public let title: String
    let service: LioService
    let trips: LioChatTrips?

    public init(id: String, title: String, service: LioService) {
        self.init(id: id, title: title, service: service, trips: nil)
    }

    init(id: String, title: String, service: LioService, trips: LioChatTrips?) {
        self.id = Data(id.utf8)
        self.title = title
        self.service = service
        self.trips = trips
    }
}

@MainActor @Observable
final class LioChatTrips {
    var plan: LioTripPlan?

    init(plan: LioTripPlan? = nil) { self.plan = plan }
}

/// In-memory position only. The account root discards it on an identity change;
/// a new authenticated client must read the conversation again before use.
@MainActor public final class LioChatContinuity {
    var selectedID: Data?
    var draft = ""
    var firstQuestions: [Data: LioQuestion] = [:]
    var localIDs: [Data: String] = [:]
    var blankIDs: Set<Data> = []

    public init() {}

    public func inherit(_ previous: LioChatContinuity) {
        selectedID = previous.selectedID
        draft = previous.draft
        firstQuestions = previous.firstQuestions
        localIDs = previous.localIDs
        blankIDs = previous.blankIDs
    }
}

/// Supplies conversation-scoped services for the current account. Starting a
/// blank chat is local. The signed service creates it with the first send.
public struct LioChatLibrary {
    let currentID: Data
    let history: @MainActor () async throws -> [LioChatSession]
    let newChat: @MainActor () -> LioChatSession
    public private(set) var continuity: LioChatContinuity?
    private(set) var restore: (@MainActor () async throws -> LioChatSession?)?
    /// Explains the latest restore failure. It reads what the restore observed and changes nothing.
    private(set) var diagnose: (@MainActor (any Error) -> LioFailureDiagnosis)?

    public init(currentID: String,
                history: @escaping @MainActor () async throws -> [LioChatSession],
                newChat: @escaping @MainActor () -> LioChatSession) {
        self.currentID = Data(currentID.utf8)
        self.history = history
        self.newChat = newChat
    }

    @MainActor
    public static func signed(client: LioTimelineHTTP, defaultService: LioService,
                              language: @escaping @MainActor () -> LioLanguage,
                              continuity: LioChatContinuity? = nil,
                              version: LioTimelineWire.Version = .v2,
                              notes: LioDiagnosticLog = .shared,
                              tripHistory: @escaping @MainActor (String) -> LioTripHistoryClient) -> Self {
        let continuity = continuity ?? LioChatContinuity()
        let sessions = LioSignedChatSessions(client: client, continuity: continuity, version: version,
                                             notes: notes, tripHistory: tripHistory)
        let defaultID = "lio-original"
        var library = Self(currentID: defaultID, history: {
            let title = language().text("First conversation", "最早的对话")
            return try await sessions.history() + [LioChatSession(id: defaultID, title: title, service: defaultService)]
        }, newChat: { sessions.newChat() })
        library.continuity = continuity
        library.restore = {
            guard let selected = continuity.selectedID, selected != Data(defaultID.utf8) else { return nil }
            do {
                return try await sessions.restore(selected)
            } catch {
                // The original error is rethrown unchanged; only a local note is added.
                if !(error is CancellationError) && !Task.isCancelled { notes.record(sessions.problem(error)) }
                throw error
            }
        }
        library.diagnose = { sessions.diagnose($0) }
        return library
    }
}

@MainActor
private final class LioSignedChatSessions {
    private let client: LioTimelineHTTP
    private let tripHistory: @MainActor (String) -> LioTripHistoryClient
    private let continuity: LioChatContinuity
    private let version: LioTimelineWire.Version
    private let notes: LioDiagnosticLog
    private var lastRestoreProblem: LioRequestProblem?

    init(client: LioTimelineHTTP, continuity: LioChatContinuity, version: LioTimelineWire.Version,
         notes: LioDiagnosticLog, tripHistory: @escaping @MainActor (String) -> LioTripHistoryClient) {
        self.client = client
        self.continuity = continuity
        self.version = version
        self.notes = notes
        self.tripHistory = tripHistory
    }

    func diagnose(_ error: any Error) -> LioFailureDiagnosis { problem(error).diagnosis }

    func problem(_ error: any Error) -> LioRequestProblem {
        lastRestoreProblem ?? LioRequestProblem(error, stage: .selectedChat)
    }

    private func conversationService(_ destination: LioTimelineWire.V2Destination,
                         didCreate: @escaping @Sendable (String) async -> Void) -> LioService {
        let client = client, notes = notes
        return LioService.signedConversation(client, destination: destination, version: version, readFailed: { error in
            let observation = client.lastObservation.flatMap { $0.kind == .timeline ? $0 : nil }
            notes.record(error: error, stage: .timeline, observation: observation)
        }, didCreate: didCreate)
    }

    func history() async throws -> [LioChatSession] {
        let attempt = LioRestoreAttempt(stage: .history)
        do {
            return try await LioTimelineHTTP.observing({ attempt.observation = $0 }) { @MainActor [self] in
                _ = try await client.reconcileFirstChat()
                return try recordedSessions()
            }
        } catch {
            if !(error is CancellationError) && !Task.isCancelled {
                notes.record(LioRequestProblem(error, stage: .history, observation: attempt.observation))
            }
            throw error
        }
    }

    private func recordedSessions() throws -> [LioChatSession] {
        try client.savedChats().map { saved in
            let service = conversationService(.existing(saved.id)) { _ in }
            let trips = LioChatTrips(plan: LioTripPlan(client: tripHistory(saved.id)))
            return LioChatSession(id: continuity.localIDs[Data(saved.id.utf8)] ?? saved.id, title: saved.title,
                                  service: service, trips: trips)
        }
    }

    func newChat() -> LioChatSession {
        let localID = UUID().uuidString
        return blank(localID)
    }

    private func blank(_ localID: String) -> LioChatSession {
        continuity.blankIDs.insert(Data(localID.utf8))
        let trips = LioChatTrips()
        let service = conversationService(.newChat) { [weak self] id in
            await self?.bind(id, localID: localID, trips: trips)
        }
        return LioChatSession(id: localID, title: "", service: service, trips: trips)
    }

    private func bind(_ id: String, localID: String, trips: LioChatTrips) {
        continuity.localIDs[Data(id.utf8)] = localID
        continuity.firstQuestions.removeValue(forKey: Data(localID.utf8))
        continuity.blankIDs.remove(Data(localID.utf8))
        trips.plan = LioTripPlan(client: tripHistory(id))
    }

    func restore(_ selected: Data) async throws -> LioChatSession {
        let attempt = LioRestoreAttempt(stage: .selectedChat)
        lastRestoreProblem = nil
        do {
            return try await LioTimelineHTTP.observing({ attempt.observation = $0 }) { @MainActor [self] in
                try await restore(selected, attempt: attempt)
            }
        } catch {
            if Task.isCancelled { throw CancellationError() }
            if !(error is CancellationError) {
                lastRestoreProblem = LioRequestProblem(error, stage: attempt.stage, observation: attempt.observation)
            }
            throw error
        }
    }

    private func restore(_ selected: Data, attempt: LioRestoreAttempt) async throws -> LioChatSession {
        if let first = continuity.firstQuestions[selected] {
            attempt.stage = .localRecord
            if try client.firstChatCanReturnToDraft(messageID: first.messageID) {
                continuity.firstQuestions.removeValue(forKey: selected)
                if continuity.draft.isEmpty { continuity.draft = first.text }
                return blank(String(decoding: selected, as: UTF8.self))
            }
            attempt.stage = .firstSendLookup
            guard let id = try await client.reconcileFirstChat(messageID: first.messageID) else {
                throw MessageHTTPFailure.exchangeUnknown
            }
            continuity.localIDs[Data(id.utf8)] = String(decoding: selected, as: UTF8.self)
            continuity.firstQuestions.removeValue(forKey: selected)
            continuity.blankIDs.remove(selected)
        }
        // A verified saved conversation is readable without reconciling a different first send.
        // The selected first send above and HTTP submission fences retain their original checks.
        attempt.stage = .localRecord
        let chats = try recordedSessions()
        if let chat = chats.first(where: { $0.id == selected }) { return chat }
        // A blank conversation has no server identity until its first send.
        attempt.stage = .selectedChat
        guard continuity.blankIDs.contains(selected) else { throw MessageHTTPFailure.exchangeUnknown }
        return blank(String(decoding: selected, as: UTF8.self))
    }
}

@MainActor private final class LioRestoreAttempt {
    var stage: LioFailureDiagnosis.Stage
    var observation: LioTimelineHTTP.Observation?
    init(stage: LioFailureDiagnosis.Stage) { self.stage = stage }
}
