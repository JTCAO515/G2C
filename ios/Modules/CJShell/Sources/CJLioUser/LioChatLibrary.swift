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

/// Supplies conversation-scoped services for the current account. Starting a
/// blank chat is local. The signed service creates it with the first send.
public struct LioChatLibrary {
    let currentID: Data
    let history: @MainActor () async throws -> [LioChatSession]
    let newChat: @MainActor () -> LioChatSession

    public init(currentID: String,
                history: @escaping @MainActor () async throws -> [LioChatSession],
                newChat: @escaping @MainActor () -> LioChatSession) {
        self.currentID = Data(currentID.utf8)
        self.history = history
        self.newChat = newChat
    }

    @MainActor
    public static func signed(client: LioTimelineHTTP, defaultService: LioService,
                              defaultTitle: @escaping @MainActor () -> String,
                              tripHistory: @escaping @MainActor (String) -> LioTripHistoryClient) -> Self {
        let sessions = LioSignedChatSessions(client: client, tripHistory: tripHistory)
        let defaultID = "lio-original"
        return Self(currentID: defaultID, history: {
            try sessions.history() + [LioChatSession(id: defaultID, title: defaultTitle(), service: defaultService)]
        }, newChat: { sessions.newChat() })
    }
}

@MainActor
private final class LioSignedChatSessions {
    private let client: LioTimelineHTTP
    private let tripHistory: @MainActor (String) -> LioTripHistoryClient
    private var localIDs: [Data: String] = [:]

    init(client: LioTimelineHTTP, tripHistory: @escaping @MainActor (String) -> LioTripHistoryClient) {
        self.client = client
        self.tripHistory = tripHistory
    }

    func history() throws -> [LioChatSession] {
        try client.savedChats().map { saved in
            let service = LioService.signedConversation(client, destination: .existing(saved.id)) { _ in }
            let trips = LioChatTrips(plan: LioTripPlan(client: tripHistory(saved.id)))
            return LioChatSession(id: localIDs[Data(saved.id.utf8)] ?? saved.id, title: saved.title,
                                  service: service, trips: trips)
        }
    }

    func newChat() -> LioChatSession {
        let localID = UUID().uuidString
        let trips = LioChatTrips()
        let service = LioService.signedConversation(client, destination: .newChat) { [weak self] id in
            await self?.bind(id, localID: localID, trips: trips)
        }
        return LioChatSession(id: localID, title: "", service: service, trips: trips)
    }

    private func bind(_ id: String, localID: String, trips: LioChatTrips) {
        localIDs[Data(id.utf8)] = localID
        trips.plan = LioTripPlan(client: tripHistory(id))
    }
}
