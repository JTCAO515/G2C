#if DEBUG && (targetEnvironment(simulator) || G2C_M4_DEVICE_ACCEPTANCE)
import Foundation
import CJCleanupClient
import CJSession

/// Closed mapping to the five existing Root slots. No server path or caller
/// selector is used, and the current ordinary SDK slot is never among them.
@MainActor final class DevelopmentControlRecordStore: CleanupControlRecordStoring {
    let scope: AccountCleanupScope
    private let records: [CleanupControlRecord: KeychainSessionStore]
    private let selected: KeychainSessionStore
    init(scope: AccountCleanupScope, manifest: KeychainSessionStore, execution: KeychainSessionStore,
         device: KeychainSessionStore, account: KeychainSessionStore, selected: KeychainSessionStore) {
        self.scope = scope; records = [.manifest: manifest, .execution: execution, .device: device, .account: account]
        self.selected = selected
    }
    func read(_ record: CleanupControlRecord) throws -> Data? {
        guard let store = records[record] else { throw CleanupFailure.stale }
        return try store.load()?.withBytes { $0 }
    }
    func readSelected() throws -> Data? { try selected.load()?.withBytes { $0 } }
    func stageSelected(_ plan: Data, expected: Data) throws {
        guard try readSelected() == expected else { throw CleanupFailure.stale }
        try selected.save(SessionMaterial(trustedSDKBytes: plan))
        guard try readSelected() == plan else { throw CleanupFailure.exchangeUnknown }
    }
    func remove(_ record: CleanupControlRecord, expected: Data) throws -> Bool {
        guard let store = records[record] else { throw CleanupFailure.stale }
        return try store.removeIfMatching(SessionMaterial(trustedSDKBytes: expected))
    }
    func removeSelected(expected: Data) throws -> Bool { try selected.removeIfMatching(SessionMaterial(trustedSDKBytes: expected)) }
    func writeTerminalIfSelectedAbsent(_ terminal: Data) throws -> Bool {
        guard try readSelected() == nil else { return false }
        try selected.save(SessionMaterial(trustedSDKBytes: terminal))
        guard try readSelected() == terminal else { throw CleanupFailure.exchangeUnknown }
        return true
    }
}
#endif
