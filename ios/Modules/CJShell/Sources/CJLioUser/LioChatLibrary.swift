import Foundation

public struct LioChatSession: Identifiable, Sendable {
    public let id: Data
    public let title: String
    let service: LioService

    public init(id: String, title: String, service: LioService) {
        self.id = Data(id.utf8)
        self.title = title
        self.service = service
    }
}

/// Supplies conversation-scoped services for the current account. The signed
/// adapter must settle the original creation before reporting its outcome.
public struct LioChatLibrary {
    let currentID: Data
    let history: @MainActor () async throws -> [LioChatSession]
    let create: @MainActor () async throws -> LioChatSession

    public init(currentID: String,
                history: @escaping @MainActor () async throws -> [LioChatSession],
                create: @escaping @MainActor () async throws -> LioChatSession) {
        self.currentID = Data(currentID.utf8)
        self.history = history
        self.create = create
    }
}
