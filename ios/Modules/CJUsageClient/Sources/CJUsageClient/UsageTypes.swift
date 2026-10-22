import Foundation
import CJSession

public enum UsageFailure: Error, Equatable, Sendable {
    case unavailable, stale, invalidResponse, exchangeFailed, rejected(Int)
}

/// Trusted host supplies the original attempt. Optional associations must come from
/// the same original source, never inferred from a message/run or invented locally.
public struct UsageSource: Equatable, Sendable {
    public let attemptID: String
    public let operationID: String?
    public let runID: String?
    public init(attemptID: String, operationID: String? = nil, runID: String? = nil) {
        self.attemptID = attemptID; self.operationID = operationID; self.runID = runID
    }
    public static func == (a: Self, b: Self) -> Bool {
        Data(a.attemptID.utf8) == Data(b.attemptID.utf8) && a.operationID.map { Data($0.utf8) } == b.operationID.map { Data($0.utf8) }
            && a.runID.map { Data($0.utf8) } == b.runID.map { Data($0.utf8) }
    }
}

/// This is lifecycle context, NOT business authorization or dispatch permission.
/// Host allocates a new selection generation for every switch, including A-B-A.
public struct UsageBinding: Equatable, Sendable {
    public let source: UsageSource
    public let sessionOperation: SessionOperation
    public let actorIdentity: Data
    public let selectionGeneration: UUID
    public let revision: UInt64
    public init(source: UsageSource, sessionOperation: SessionOperation, actorIdentity: Data,
                selectionGeneration: UUID, revision: UInt64) {
        self.source = source; self.sessionOperation = sessionOperation; self.actorIdentity = actorIdentity
        self.selectionGeneration = selectionGeneration; self.revision = revision
    }
}

public struct UsageSnapshot: Equatable, Sendable {
    public enum Status: String, Sendable { case reserved, unknown, released, settled }
    public let attemptID: String
    public let operationID: String
    public let runID: String
    public let status: Status
    public let unit: String
    /// Exact decimal strings; no Int64 conversion, rounding or monetary meaning.
    public let reservedUnits: String
    public let confirmedUnits: String?
    public let confirmedOutput: String?
    public let receiptID: String?
    public let cancelled: Bool
    public let exceeded: Bool
    public let requestID: String
}
public enum UsageState: Equatable, Sendable {
    case unavailable, loading, loaded(UsageSnapshot), failed(UsageFailure)
}

public struct PreparedUsageRead: Sendable {
    let owner: UUID
    let generation: UUID
    public let binding: UsageBinding
}
