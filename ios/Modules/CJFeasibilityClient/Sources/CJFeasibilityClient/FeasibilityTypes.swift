import Foundation
import CJSession
import CJAPI

public enum FeasibilityFailure: Error, Equatable, Sendable {
    case unavailable, stale, invalidResponse, exchangeFailed, rejected(Int, String)
}

/// Trusted host context only: construction grants no server authority or snapshot freshness.
/// Allocate a fresh selection UUID for every switch, including A–B–A.
public struct FeasibilityBinding: Equatable, Sendable {
    public let environment: UUID
    public let account: UUID
    public let generation: UUID
    public let selection: UUID
    public let sessionOperation: SessionOperation
    public let needsID: String
    public let acceptedRevision: Int?
    public let acceptedContentSHA256: String?
    public init(environment: UUID, account: UUID, generation: UUID, selection: UUID,
                sessionOperation: SessionOperation, needsID: String,
                acceptedRevision: Int? = nil, acceptedContentSHA256: String? = nil) {
        self.environment = environment; self.account = account; self.generation = generation
        self.selection = selection; self.sessionOperation = sessionOperation; self.needsID = needsID
        self.acceptedRevision = acceptedRevision; self.acceptedContentSHA256 = acceptedContentSHA256
    }
}

/// Limits are local rejection bounds, never truncation or wire query parameters.
public struct FeasibilityLimits: Sendable {
    public let maximumCollectionItems: Int
    public let maximumSourceBytes: Int
    public init(maximumCollectionItems: Int, maximumSourceBytes: Int) throws {
        guard (1...128).contains(maximumCollectionItems), (1...1_048_576).contains(maximumSourceBytes) else {
            throw FeasibilityFailure.unavailable
        }
        self.maximumCollectionItems = maximumCollectionItems; self.maximumSourceBytes = maximumSourceBytes
    }
}

/// In-memory observation; original private source text is never persisted or logged here.
public struct FeasibilityObservation: Sendable {
    public let requestID: String
    public let report: Components.Schemas.FeasibilityCurrentReport
}
public enum FeasibilityState: Sendable {
    case unavailable, loading, cancelled, loaded(FeasibilityObservation), failed(FeasibilityFailure)
}
public struct PreparedFeasibilityRead: Sendable {
    let owner: UUID
    let generation: UUID
    let binding: FeasibilityBinding
}
func validID(_ text: String) -> Bool {
    let b = Array(text.utf8)
    func alpha(_ c: UInt8) -> Bool { (48...57).contains(c) || (65...90).contains(c) || (97...122).contains(c) }
    return (1...96).contains(b.count) && alpha(b[0]) && b.allSatisfy { alpha($0) || [95,46,58,45].contains($0) }
}
func validHash(_ text: String) -> Bool { text.utf8.count == 64 && text.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) } }
func same(_ a: String, _ b: String) -> Bool { Data(a.utf8) == Data(b.utf8) }
