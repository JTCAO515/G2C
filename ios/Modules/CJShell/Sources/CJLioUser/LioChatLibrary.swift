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
    var firstQuestions: [Data: String] = [:]
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
                              tripHistory: @escaping @MainActor (String) -> LioTripHistoryClient) -> Self {
        let continuity = continuity ?? LioChatContinuity()
        let sessions = LioSignedChatSessions(client: client, continuity: continuity, tripHistory: tripHistory)
        let defaultID = "lio-original"
        var library = Self(currentID: defaultID, history: {
            let title = language().text("First conversation", "最早的对话")
            return try await sessions.history() + [LioChatSession(id: defaultID, title: title, service: defaultService)]
        }, newChat: { sessions.newChat() })
        library.continuity = continuity
        library.restore = {
            guard let selected = continuity.selectedID, selected != Data(defaultID.utf8) else { return nil }
            return try await sessions.restore(selected)
        }
        return library
    }
}

@MainActor
private final class LioSignedChatSessions {
    private let client: LioTimelineHTTP
    private let tripHistory: @MainActor (String) -> LioTripHistoryClient
    private let continuity: LioChatContinuity

    init(client: LioTimelineHTTP, continuity: LioChatContinuity, tripHistory: @escaping @MainActor (String) -> LioTripHistoryClient) {
        self.client = client
        self.continuity = continuity
        self.tripHistory = tripHistory
    }

    func history() async throws -> [LioChatSession] {
        _ = try await client.reconcileFirstChat()
        return try client.savedChats().map { saved in
            let service = LioService.signedConversation(client, destination: .existing(saved.id)) { _ in }
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
        let service = LioService.signedConversation(client, destination: .newChat) { [weak self] id in
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
        if let first = continuity.firstQuestions[selected] {
            guard let id = try await client.reconcileFirstChat(messageID: first) else {
                throw MessageHTTPFailure.exchangeUnknown
            }
            continuity.localIDs[Data(id.utf8)] = String(decoding: selected, as: UTF8.self)
            continuity.firstQuestions.removeValue(forKey: selected)
            continuity.blankIDs.remove(selected)
        }
        let chats = try await history()
        if let chat = chats.first(where: { $0.id == selected }) { return chat }
        // A blank conversation has no server identity until its first send.
        guard continuity.blankIDs.contains(selected) else { throw MessageHTTPFailure.exchangeUnknown }
        return blank(String(decoding: selected, as: UTF8.self))
    }
}
