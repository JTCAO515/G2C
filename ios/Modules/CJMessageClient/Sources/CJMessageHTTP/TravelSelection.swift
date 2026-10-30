import Foundation
import Observation
import CJAPI
import CJMessageClient

public enum MessageSendWireVersion: String, Sendable {
    case legacy = "MESSAGE-send.1",travel = "MESSAGE-send.2"
    /// Historical accepted records remain readable, never newly submitted.
    case historicalDraft = "MESSAGE-draft.1"
}
public enum TravelSelectionState {
    case unselected,loading,none,travel(Components.Schemas.TravelContextReadResponse.travel_contextPayload),unavailable
}
public struct CapturedTravelSelection: Sendable {
    public let context: MessageReadResult<Components.Schemas.TravelContextReadResponse.travel_contextPayload>?
    fileprivate let owner: UUID
    fileprivate let revision: UUID
}
/// Explicit UI choice plus the actual B read. Configured IDs are choices, never
/// owner/currentness permission. No chat-derived identity or automatic fallback.
@MainActor @Observable public final class TravelSelectionModel {
    private enum State {
        case unselected,loading,none,travel(MessageReadResult<Components.Schemas.TravelContextReadResponse.travel_contextPayload>),unavailable
    }
    private let configuredIDs: [String]
    private let client: MessageHTTPClient
    private let lease: Lease
    private let current: @MainActor () -> Bool
    private let owner = UUID()
    private var revision = UUID()
    private var selected: State = .unselected
    public init(ids: [String],client: MessageHTTPClient,lease: Lease,isCurrent: @escaping @MainActor () -> Bool) throws {
        guard !ids.isEmpty,Set(ids.map({ Data($0.utf8) })).count == ids.count,
              ids.allSatisfy({ $0.utf8.count == 32 && $0.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) }) else { throw MessageHTTPFailure.invalidConfiguration }
        configuredIDs = ids;self.client = client;self.lease = lease;current = isCurrent
    }
    private func check(_ token: UUID) throws {
        guard revision == token else { throw RecoveryError.staleOperation }
        let active = current()
        guard active,revision == token else { throw RecoveryError.inactive }
        try client.recovery.validateScope(client.scope,lease:lease)
    }
    public var ids: [String] {
        do { try check(revision);return configuredIDs } catch { return [] }
    }
    public var state: TravelSelectionState {
        let token = revision
        do { try check(token) } catch { return .unavailable }
        switch selected {
        case .unselected:return .unselected
        case .loading:return .loading
        case .none:return .none
        case .travel(let result):return .travel(result.value)
        case .unavailable:return .unavailable
        }
    }
    public func invalidate() { revision = UUID();selected = .unselected }
    public func selectNone() throws {
        try check(revision);revision = UUID();selected = .none
    }
    public func selectTravel(_ id: String) async {
        let token = UUID();revision = token;selected = .loading
        do {
            try check(token)
            guard configuredIDs.contains(where:{ Data($0.utf8) == Data(id.utf8) }) else { throw RecoveryError.invalidInput }
            let result = try await client.readTravelContext(id:id,lease:lease)
            try check(token);try client.validateRead(result,lease:lease)
            guard result.value.active else { throw MessageHTTPFailure.invalidResponse }
            selected = .travel(result)
        } catch {
            if revision == token { selected = .unavailable }
        }
    }
    public func capture() throws -> CapturedTravelSelection {
        let token = revision;try check(token)
        let context: MessageReadResult<Components.Schemas.TravelContextReadResponse.travel_contextPayload>?
        switch selected {
        case .none:context = nil
        case .travel(let result):try client.validateRead(result,lease:lease);context = result
        case .unselected,.loading,.unavailable:throw RecoveryError.queryOnly
        }
        try check(token)
        return CapturedTravelSelection(context:context,owner:owner,revision:token)
    }
    public func validate(_ capture: CapturedTravelSelection) throws {
        try check(capture.revision)
        guard capture.owner == owner else { throw RecoveryError.inactive }
        if let context = capture.context { try client.validateRead(context,lease:lease) }
    }
}
