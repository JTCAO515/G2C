import Foundation
import CJAPI

public typealias NeedsSchema = Components.Schemas
public enum NeedsFailure: Error, Equatable, Sendable {
    case unconfigured, staleBinding, invalidInput, invalidResponse
    case liveWriteUnavailable, pendingRequiresQuery, exchangeUnknown
    case storageUnavailable, keyUnavailable
    case rejected(Int, String)
}

/// Supplied by the trusted session host. These UUIDs are local lifetimes, not wire IDs or server scope.
public struct NeedsBinding: Hashable, Sendable {
    public let environment: UUID
    public let account: UUID
    public let generation: UUID
    public let selection: UUID
    public init(environment: UUID, account: UUID, generation: UUID, selection: UUID) {
        self.environment = environment; self.account = account
        self.generation = generation; self.selection = selection
    }
}
func same(_ lhs: String, _ rhs: String) -> Bool { Data(lhs.utf8) == Data(rhs.utf8) }
func needsID(_ text: String) -> Bool {
    let bytes = Array(text.utf8)
    func alphanumeric(_ b: UInt8) -> Bool { (48...57).contains(b) || (65...90).contains(b) || (97...122).contains(b) }
    return (1...96).contains(bytes.count) && alphanumeric(bytes[0]) && bytes.allSatisfy { alphanumeric($0) || [95, 46, 58, 45].contains($0) }
}
func validText(_ text: String) -> Bool { (1...4096).contains(text.unicodeScalars.count) && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
func encoded<T: Encodable>(_ value: T) throws -> Data {
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    return try encoder.encode(value)
}

/// Frozen once before persistence/outflow. Original bytes are the identity; never re-encoded for recovery.
public struct NeedsPending: Codable, Sendable {
    public let originalUTF8: Data
    public var actionID: String { command.action_id }
    public var needsID: String { command.needs_id }
    public let command: NeedsSchema.NeedsCommand
    public init(command: NeedsSchema.NeedsCommand) throws {
        try validateCommand(command)
        self.command = command; originalUTF8 = try encoded(command)
        guard originalUTF8.count <= 131_072 else { throw NeedsFailure.invalidInput }
    }
    func validate() throws {
        guard originalUTF8.count <= 131_072, String(data: originalUTF8, encoding: .utf8) != nil else { throw NeedsFailure.invalidInput }
        let decoded = try JSONDecoder().decode(NeedsSchema.NeedsCommand.self, from: originalUTF8)
        try validateCommand(decoded)
        // Byte-aware comparison also protects canonically equivalent, differently encoded Unicode text.
        guard try encoded(decoded) == encoded(command) else { throw NeedsFailure.invalidInput }
    }
}

public enum NeedsResult: Sendable {
    case detail(NeedsSchema.NeedsSnapshot?)
    case revision(NeedsSchema.NeedsRevision?)
    case confirmed(NeedsSchema.NeedsReceipt, NeedsSchema.NeedsRevision)
    case notObserved // Unknown, never a resend permit.
}

/// Opaque one-use operation. Capture synchronously before starting a Task.
public struct NeedsWork: Sendable {
    enum Kind: Sendable {
        case detail(String), revision(String, Int), query(String), submit(NeedsPending)
    }
    let owner: UUID
    let generation: UUID
    let binding: NeedsBinding
    let kind: Kind
}
