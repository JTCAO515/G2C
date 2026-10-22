import Foundation
import CJAPI

public enum TripFailure: Error, Equatable, Sendable {
    case unconfigured, staleBinding, invalidInput, invalidResponse
    case liveWriteUnavailable, pendingRequiresQuery, exchangeUnknown
    case storageUnavailable, keyUnavailable
    case rejected(Int, String)
}

/// Host-owned identity and selection lifetime, never a server scope or authorization.
public struct TripBinding: Hashable, Sendable {
    public let environment: UUID
    public let account: UUID
    public let generation: UUID
    public let selection: UUID
    public init(environment: UUID, account: UUID, generation: UUID, selection: UUID) {
        self.environment = environment; self.account = account
        self.generation = generation; self.selection = selection
    }
}

public struct TripPage: Sendable {
    public let trips: [Components.Schemas.TripRecord]
    public let next: TripCursor?
}

public struct TripCursor: Sendable {
    let owner: UUID
    let binding: TripBinding
    let after: String
}

func same(_ lhs: String, _ rhs: String) -> Bool { Data(lhs.utf8) == Data(rhs.utf8) }
func tripID(_ text: String) -> Bool {
    let bytes = Array(text.utf8)
    func alphanumeric(_ byte: UInt8) -> Bool { (48...57).contains(byte) || (65...90).contains(byte) || (97...122).contains(byte) }
    return (1...128).contains(bytes.count) && alphanumeric(bytes[0]) && bytes.allSatisfy { alphanumeric($0) || [95, 46, 58, 45].contains($0) }
}
func tripHash(_ text: String) -> Bool {
    text.utf8.count == 64 && text.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
}
