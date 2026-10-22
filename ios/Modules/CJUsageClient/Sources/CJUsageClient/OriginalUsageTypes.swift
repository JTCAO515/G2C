import Foundation
import CJAPI
import CJSession
import CJMessageClient

/// Captured only from this model's CURRENT canonical MESSAGE recovery accepted
/// record. Not constructible from caller IDs/DTOs, and never business authorization.
public struct AcceptedUsageMessage: Equatable, Sendable {
    let owner: UUID
    let id: UUID
    let record: ActionRecord
    let lease: Lease
    let receipt: Components.Schemas.MessageReceipt
    public var messageID: String { receipt.message_id }
    public static func == (a: Self, b: Self) -> Bool { a.owner == b.owner && a.id == b.id }
}

public struct OriginalUsageBinding: Equatable, Sendable {
    public let acceptedMessage: AcceptedUsageMessage
    public let sessionOperation: SessionOperation
    public let actorIdentity: Data
    public let selectionGeneration: UUID
    public let revision: UInt64
    public init(acceptedMessage: AcceptedUsageMessage, sessionOperation: SessionOperation,
                actorIdentity: Data, selectionGeneration: UUID, revision: UInt64) {
        self.acceptedMessage = acceptedMessage; self.sessionOperation = sessionOperation
        self.actorIdentity = actorIdentity; self.selectionGeneration = selectionGeneration; self.revision = revision
    }
}

/// Closed result of the official generated association GET plus exact original
/// MESSAGE receipt checks. No public initializer and no seven-ref acceptance API.
public struct ResolvedUsageSource: Equatable, Sendable {
    let owner: UUID
    let id: UUID
    let binding: OriginalUsageBinding
    let association: Components.Schemas.OriginalUsageAssociation
    public let requestID: String
    public var attemptID: String { association.attempt_id }
    public var operationID: String { association.operation_id }
    public var runID: String { association.run_id }
    public var messageID: String { association.message_id }
    public static func == (a: Self, b: Self) -> Bool { a.owner == b.owner && a.id == b.id }
}

public struct PreparedOriginalUsageRead: Sendable {
    let owner: UUID
    let generation: UUID
    let binding: OriginalUsageBinding
    let source: ResolvedUsageSource?
}
public enum OriginalUsageState: Equatable, Sendable {
    case unavailable, loading, sourceReady(ResolvedUsageSource), loaded(UsageSnapshot), failed(UsageFailure)
}
public typealias OriginalUsageCredentialCallback = @MainActor (OriginalUsageBinding) async throws -> String?
