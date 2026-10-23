import Foundation
import CJSession
import CJAPI

public enum CleanupFailure: Error, Equatable, Sendable {
    case unavailable, stale, invalidResponse, exchangeUnknown, rejected(Int)
}

/// Trusted host supplies an EXISTING original operation from its authoritative source.
/// This binding is not proof of account permission; the current bearer and server gate
/// remain authoritative. No operation creation, UI-viewed grant or postlogout access.
public struct CleanupBinding: Equatable, Sendable {
    public let environment: UUID
    public let actorIdentity: String
    public let sessionOperation: SessionOperation
    public let originalOperationID: String
    public static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.environment == rhs.environment && lhs.sessionOperation == rhs.sessionOperation
            && Data(lhs.actorIdentity.utf8) == Data(rhs.actorIdentity.utf8)
            && Data(lhs.originalOperationID.utf8) == Data(rhs.originalOperationID.utf8)
    }
    public init(environment: UUID, actorIdentity: String, sessionOperation: SessionOperation,
                trustedOriginalOperationID: String) {
        self.environment = environment; self.actorIdentity = actorIdentity
        self.sessionOperation = sessionOperation; originalOperationID = trustedOriginalOperationID
    }
}

public struct PreparedCleanupRead: Sendable {
    let owner: UUID
    let generation: UUID
    let binding: CleanupBinding
}

/// Official generated whitelist, without a second wire model. Only expose after validation.
public typealias CleanupProgress = Components.Schemas.CurrentAccountCleanupProgress
public enum CleanupState: Equatable, Sendable {
    case unavailable, loading, loaded(CleanupProgress), failed(CleanupFailure)
}
public typealias CleanupCredentialCallback = @MainActor (CleanupBinding) async throws -> String?

func cleanupIdentifier(_ value: String, maximum: Int) -> Bool {
    let bytes = Array(value.utf8)
    guard (1...maximum).contains(bytes.count), let first = bytes.first,
          (48...57).contains(first) || (65...90).contains(first) || (97...122).contains(first) else { return false }
    return bytes.allSatisfy { (48...57).contains($0) || (65...90).contains($0)
        || (97...122).contains($0) || [95,46,58,47,45].contains($0) }
}
