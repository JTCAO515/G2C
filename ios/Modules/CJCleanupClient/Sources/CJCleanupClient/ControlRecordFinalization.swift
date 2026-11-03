import Foundation
import CJStrictJSON

public enum CleanupControlSelection: Sendable {
    case original(AccountCleanupScope), finalizing(CleanupControlFinalizationPlan), terminal(CleanupControlTerminal)
    public init(bytes: Data) throws {
        guard bytes.count <= 16384 else { throw CleanupFailure.invalidResponse }
        let fields = try accountCleanupObject(accountCleanupDocument(bytes))
        if let version = fields["version"] {
            switch try accountCleanupString(version) {
            case "CleanupControlFinalization@1": self = .finalizing(try .init(bytes: bytes))
            case "CleanupControlTerminal@1": self = .terminal(try .init(bytes: bytes))
            default: throw CleanupFailure.invalidResponse
            }
        } else {
            try accountCleanupKeys(fields, fields: ["environment", "account", "generation"])
            do { self = .original(try JSONDecoder().decode(AccountCleanupScope.self, from: bytes)) }
            catch { throw CleanupFailure.invalidResponse }
        }
    }
}

public enum CleanupControlRecord: String, CaseIterable, Codable, Sendable {
    case manifest, execution, device, account
}
/// Implemented only by the trusted native Root. Each case maps to an immutable
/// exact namespace. Removal must compare expected bytes and verify absence.
@MainActor public protocol CleanupControlRecordStoring: AnyObject {
    var scope: AccountCleanupScope { get }
    func read(_ record: CleanupControlRecord) throws -> Data?
    func readSelected() throws -> Data?
    func stageSelected(_ plan: Data, expected: Data) throws
    func remove(_ record: CleanupControlRecord, expected: Data) throws -> Bool
    func removeSelected(expected: Data) throws -> Bool
    func writeTerminalIfSelectedAbsent(_ terminal: Data) throws -> Bool
}

public struct CleanupControlTerminal: Encodable, Sendable {
    public let version: String
    public let scopeDigest: String
    public let operationDigest: String
    public let invocationDigest: String
    public let requestDigest: String
    public let receiptDigest: String
    public let registryDigest: String
    public let recordSetDigest: String
    public let outcome: String
    fileprivate init(scope: AccountCleanupScope, completion: DeviceCleanupCompletion, records: [CleanupControlExpectedRecord]) throws {
        version = "CleanupControlTerminal@1"; outcome = "original_control_records_cleared"
        scopeDigest = try controlScopeDigest(scope)
        operationDigest = deviceCleanupSHA(Data(completion.operationID.utf8))
        invocationDigest = deviceCleanupSHA(Data(completion.invocationID.utf8))
        requestDigest = completion.requestDigest
        guard let receipt = completion.receiptDigest, let registry = completion.registryDigest else { throw CleanupFailure.unavailable }
        receiptDigest = receipt; registryDigest = registry
        recordSetDigest = deviceCleanupSHA(try controlEncoded(records))
    }
    public init(bytes: Data) throws {
        guard bytes.count <= 4096 else { throw CleanupFailure.invalidResponse }
        try self.init(value: accountCleanupDocument(bytes))
        guard try encoded() == bytes else { throw CleanupFailure.invalidResponse }
    }
    fileprivate init(value: CJStrictJSON.StrictJSONValue) throws {
        let fields = try accountCleanupObject(value, fields: ["version", "scopeDigest", "operationDigest", "invocationDigest", "requestDigest", "receiptDigest", "registryDigest", "recordSetDigest", "outcome"])
        guard try accountCleanupString(fields["version"]) == "CleanupControlTerminal@1",
              try accountCleanupString(fields["outcome"]) == "original_control_records_cleared" else { throw CleanupFailure.invalidResponse }
        version = "CleanupControlTerminal@1"; outcome = "original_control_records_cleared"
        scopeDigest = try accountCleanupDigest(fields["scopeDigest"])
        operationDigest = try accountCleanupDigest(fields["operationDigest"])
        invocationDigest = try accountCleanupDigest(fields["invocationDigest"])
        requestDigest = try accountCleanupDigest(fields["requestDigest"])
        receiptDigest = try accountCleanupDigest(fields["receiptDigest"])
        registryDigest = try accountCleanupDigest(fields["registryDigest"])
        recordSetDigest = try accountCleanupDigest(fields["recordSetDigest"])
    }
    public func encoded() throws -> Data { try controlEncoded(self) }
}
fileprivate struct CleanupControlExpectedRecord: Codable, Sendable {
    let record: CleanupControlRecord
    let digest: String?
}
/// Private routing remains in the original Selected reconciliation slot only
/// while finalization is unfinished. The completed replacement has hashes only.
public struct CleanupControlFinalizationPlan: Encodable, Sendable {
    public let version: String
    public let scope: AccountCleanupScope
    fileprivate let records: [CleanupControlExpectedRecord]
    fileprivate let terminal: CleanupControlTerminal
    fileprivate init(scope: AccountCleanupScope, records: [CleanupControlExpectedRecord], terminal: CleanupControlTerminal) {
        version = "CleanupControlFinalization@1"; self.scope = scope; self.records = records; self.terminal = terminal
    }
    public init(bytes: Data) throws {
        guard bytes.count <= 16384 else { throw CleanupFailure.invalidResponse }
        let fields = try accountCleanupObject(accountCleanupDocument(bytes), fields: ["version", "scope", "records", "terminal"])
        guard try accountCleanupString(fields["version"]) == "CleanupControlFinalization@1" else { throw CleanupFailure.invalidResponse }
        let scoped = try accountCleanupObject(fields["scope"], fields: ["environment", "account", "generation"])
        guard let environment = UUID(uuidString: try accountCleanupString(scoped["environment"])),
              let account = UUID(uuidString: try accountCleanupString(scoped["account"])),
              let generation = UUID(uuidString: try accountCleanupString(scoped["generation"])) else { throw CleanupFailure.invalidResponse }
        version = "CleanupControlFinalization@1"; scope = .init(environment: environment, account: account, generation: generation)
        guard case .array(let values) = fields["records"], values.count == CleanupControlRecord.allCases.count else { throw CleanupFailure.invalidResponse }
        records = try values.map { value in
            let row = try accountCleanupObject(value)
            try accountCleanupKeys(row, fields: ["record"], optional: ["digest"])
            guard let record = CleanupControlRecord(rawValue: try accountCleanupString(row["record"])) else { throw CleanupFailure.invalidResponse }
            let digest = try row["digest"].map { try accountCleanupDigest($0) }
            return .init(record: record, digest: digest)
        }
        guard let terminalValue = fields["terminal"] else { throw CleanupFailure.invalidResponse }
        terminal = try CleanupControlTerminal(value: terminalValue)
        let scopeHash = try controlScopeDigest(scope)
        let recordsHash = deviceCleanupSHA(try controlEncoded(records))
        guard Set(records.map(\.record)) == Set(CleanupControlRecord.allCases),
              Set(records.map(\.record)).count == records.count,
              terminal.scopeDigest == scopeHash,
              terminal.recordSetDigest == recordsHash else { throw CleanupFailure.invalidResponse }
        _ = try CleanupControlTerminal(bytes: terminal.encoded())
        guard try encoded() == bytes else { throw CleanupFailure.invalidResponse }
    }
    public func encoded() throws -> Data { try controlEncoded(self) }
}

/// No backend result is inferred from missing records. A durable terminal-authorized
/// plan is staged before any removal. Selected remains the locator until last.
@MainActor public enum CleanupControlFinalizer {
    public static func start(completion: DeviceCleanupCompletion, store: any CleanupControlRecordStoring) throws -> CleanupControlTerminal {
        guard completion.permitsAccountRecordFinalization, completion.scope == store.scope,
              let selected = try store.readSelected() else { throw CleanupFailure.unavailable }
        let fields = try accountCleanupObject(accountCleanupDocument(selected), fields: ["environment", "account", "generation"])
        _ = fields
        let scope: AccountCleanupScope
        do { scope = try JSONDecoder().decode(AccountCleanupScope.self, from: selected) } catch { throw CleanupFailure.invalidResponse }
        guard scope == completion.scope else { throw CleanupFailure.stale }
        var snapshots: [CleanupControlRecord: Data] = [:]
        var records: [CleanupControlExpectedRecord] = []
        for record in CleanupControlRecord.allCases {
            let raw = try store.read(record)
            if let raw { snapshots[record] = raw }
            records.append(.init(record: record, digest: raw.map(deviceCleanupSHA)))
        }
        guard snapshots[.device].map(deviceCleanupSHA) == completion.journalSHA256 else { throw CleanupFailure.stale }
        let terminal = try CleanupControlTerminal(scope: scope, completion: completion, records: records)
        let plan = CleanupControlFinalizationPlan(scope: scope, records: records, terminal: terminal)
        // Compare every snapshot before staging or deleting the first record.
        for record in CleanupControlRecord.allCases { guard try store.read(record) == snapshots[record] else { throw CleanupFailure.stale } }
        guard store.scope == scope, try store.readSelected() == selected else { throw CleanupFailure.stale }
        try store.stageSelected(plan.encoded(), expected: selected)
        return try resume(plan: plan, store: store)
    }
    public static func resume(plan: CleanupControlFinalizationPlan, store: any CleanupControlRecordStoring) throws -> CleanupControlTerminal {
        let encoded = try plan.encoded()
        guard store.scope == plan.scope, try store.readSelected() == encoded else { throw CleanupFailure.stale }
        // Absence here is reconciliation of this previously staged removal plan,
        // never evidence of server/receipt completion on its own.
        for expected in plan.records {
            if let raw = try store.read(expected.record) {
                guard expected.digest == deviceCleanupSHA(raw) else { throw CleanupFailure.stale }
            }
        }
        guard store.scope == plan.scope, try store.readSelected() == encoded else { throw CleanupFailure.stale }
        for expected in plan.records {
            guard store.scope == plan.scope, try store.readSelected() == encoded else { throw CleanupFailure.stale }
            if let raw = try store.read(expected.record) {
                guard expected.digest == deviceCleanupSHA(raw), try store.remove(expected.record, expected: raw),
                      try store.read(expected.record) == nil else { throw CleanupFailure.stale }
            }
        }
        for expected in plan.records { guard try store.read(expected.record) == nil else { throw CleanupFailure.stale } }
        guard store.scope == plan.scope, try store.readSelected() == encoded,
              try store.removeSelected(expected: encoded), try store.readSelected() == nil else { throw CleanupFailure.stale }
        _ = try store.writeTerminalIfSelectedAbsent(plan.terminal.encoded()) // A newly selected account is never overwritten.
        return plan.terminal
    }
}
private func controlEncoded<T: Encodable>(_ value: T) throws -> Data {
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    return try encoder.encode(value)
}
private func controlScopeDigest(_ scope: AccountCleanupScope) throws -> String { deviceCleanupSHA(try controlEncoded(scope)) }
