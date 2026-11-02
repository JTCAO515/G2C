import Foundation
import Darwin
import CryptoKit
import Testing
import CJMessageKeys
@testable import CJMemoryClient

@MainActor private final class MemoryCleanupFixture {
    let parent = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
    let key = SymmetricKey(size: .bits256)
    let keyID = UUID()
    let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localMemoryPendingV1)
    var root: URL { parent.appendingPathComponent("account-A") }
    init() throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    }
    func dispose() { try? FileManager.default.removeItem(at: parent) }
    func store(at path: URL? = nil, key: (() throws -> SymmetricKey)? = nil) throws -> MemoryPendingStore {
        let material = self.key
        return try MemoryPendingStore(directory: path ?? root, maximumBytes: 524_288, maximumRecords: 20,
            namespace: namespace, keyID: keyID, key: key ?? { material })
    }
}

@MainActor struct LocalJournalCleanupTests {
    @Test func clearsWithoutKeyPreservesOtherAccountAndPermanentlyRetiresOriginalStore() throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        var keyAvailable = true; var calls = 0
        let journal = try f.store { calls += 1; guard keyAvailable else { throw MemoryFailure.keyUnavailable }; return f.key }
        let record = try MemoryPending(command())
        try journal.append(record)
        let other = f.parent.appendingPathComponent("account-B")
        try FileManager.default.createDirectory(at: other, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let otherJournal = try f.store(at: other); try otherJournal.append(record)
        let otherFile = try #require(FileManager.default.contentsOfDirectory(at: other, includingPropertiesForKeys: nil).first)
        let otherBytes = try Data(contentsOf: otherFile)
        keyAvailable = false; let before = calls
        try journal.clearLocalFiles()
        #expect(calls == before)
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
        #expect(try Data(contentsOf: otherFile) == otherBytes)
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.pending() }
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.append(record) }
        try journal.clearLocalFiles()
        #expect(calls == before)
        #expect(try f.store().pending().isEmpty)
    }
    @Test(arguments: ["unknown", "directory", "symlink", "hardlink"])
    func rejectsUnexpectedEntryBeforeErasingAndAllowsOriginalTargetRetry(kind: String) throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        let journal = try f.store(); let record = try MemoryPending(command()); try journal.append(record)
        let originalFile = try #require(FileManager.default.contentsOfDirectory(at: f.root, includingPropertiesForKeys: nil).first)
        let bytes = try Data(contentsOf: originalFile)
        let bad = f.root.appendingPathComponent(kind == "unknown" ? "unexpected" : String(repeating: "a", count: 64) + ".memory")
        switch kind {
        case "directory": try FileManager.default.createDirectory(at: bad, withIntermediateDirectories: false)
        case "symlink": try FileManager.default.createSymbolicLink(at: bad, withDestinationURL: originalFile)
        case "hardlink": try FileManager.default.linkItem(at: originalFile, to: bad)
        default: try Data("unknown".utf8).write(to: bad)
        }
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.clearLocalFiles() }
        #expect(try Data(contentsOf: originalFile) == bytes)
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.append(record) }
        try FileManager.default.removeItem(at: bad)
        try journal.clearLocalFiles()
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test func originalDirectoryReplacementCannotEraseReplacementOrDisplacedData() throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        let journal = try f.store(); try journal.append(MemoryPending(command()))
        let displaced = f.parent.appendingPathComponent("displaced")
        try FileManager.default.moveItem(at: f.root, to: displaced)
        try FileManager.default.createDirectory(at: f.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let replacement = try f.store(); try replacement.append(MemoryPending(command()))
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.clearLocalFiles() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).count == 1)
        #expect(try FileManager.default.contentsOfDirectory(atPath: displaced.path).count == 1)
        try FileManager.default.removeItem(at: f.root)
        try FileManager.default.moveItem(at: displaced, to: f.root)
        try journal.clearLocalFiles()
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test func cleanupInsideLastBindingCallbackPreventsLateAppend() throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        let journal = try f.store(); let record = try MemoryPending(command())
        #expect(throws: MemoryFailure.storageUnavailable) {
            try journal.append(record) { try journal.clearLocalFiles() }
        }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test func cleanupInsideKeyCallbackWithholdsAlreadyDecryptedResult() throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        var erase = false; var journal: MemoryPendingStore!
        journal = try f.store {
            if erase { try journal.clearLocalFiles() }
            return f.key
        }
        try journal.append(MemoryPending(command()))
        erase = true
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.pending() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test(arguments: ["CJMemoryPending", "CJMemoryManagementPending", "CJMemoryTypedPendingV2", "CJMemoryHistoryPendingV1"])
    func capturesAndClearsOnlyKnownSidecarFamily(domain: String) throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        let journal = try MemoryEncryptedRecords<MemoryPending>(directory: f.root, maximumBytes: 524_288,
            maximumRecords: 20, namespace: f.namespace, keyID: f.keyID, domain: domain, key: { f.key })
        let record = try MemoryPending(command()); try journal.append(record)
        let suffix: String
        switch domain {
        case "CJMemoryPending": suffix = "CJMemoryRejections"
        case "CJMemoryManagementPending": suffix = "CJMemoryManagementRejections"
        case "CJMemoryTypedPendingV2": suffix = "CJMemoryTypedRejectionsV2"
        default: suffix = "CJMemoryHistoryRejectionsV1"
        }
        try journal.recordRejection(record, status: 409, code: "INPUT_CONFLICT", domain: suffix, validateBinding: {})
        var directories = [f.root, f.root.appendingPathExtension(suffix)]
        var heldManagement: MemoryEncryptedRecords<MemoryPending>?
        if domain == "CJMemoryTypedPendingV2" {
            let management: MemoryEncryptedRecords<MemoryPending>? = try journal.adjacentRecords(domain: "CJMemoryTypedManagementV2", create: true)
            let records = try #require(management); heldManagement = records
            try records.append(record)
            try records.recordRejection(record, status: 409, code: "INPUT_CONFLICT", domain: "CJMemoryTypedManagementRejectionsV2", validateBinding: {})
            directories += [f.root.appendingPathExtension("CJMemoryTypedManagementV2"),
                f.root.appendingPathExtension("CJMemoryTypedManagementV2.CJMemoryTypedManagementRejectionsV2")]
        }
        let unknown = f.root.appendingPathExtension("unprovided")
        try FileManager.default.createDirectory(at: unknown, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let sentinel = unknown.appendingPathComponent("keep"); try Data("keep".utf8).write(to: sentinel)
        try journal.clearLocalFiles()
        for directory in directories { #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).isEmpty) }
        #expect(try Data(contentsOf: sentinel) == Data("keep".utf8))
        if let heldManagement { #expect(throws: MemoryFailure.storageUnavailable) { try heldManagement.append(record) } }
    }
    @Test(arguments: [true, false])
    func sidecarReplacementOrLateAppearanceCannotBeAdopted(initiallyPresent: Bool) throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        let sidecar = f.root.appendingPathExtension("CJMemoryRejections")
        if initiallyPresent { try FileManager.default.createDirectory(at: sidecar, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        let journal = try f.store(); let record = try MemoryPending(command()); try journal.append(record)
        if initiallyPresent { try FileManager.default.moveItem(at: sidecar, to: f.parent.appendingPathComponent("old-sidecar")) }
        try FileManager.default.createDirectory(at: sidecar, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let sentinel = sidecar.appendingPathComponent(String(repeating: "a", count: 64) + ".memory")
        try Data("keep".utf8).write(to: sentinel)
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.clearLocalFiles() }
        #expect(try Data(contentsOf: sentinel) == Data("keep".utf8))
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).count == 1)
    }
    @Test func capturesExistingSidecarOnReopenAndAcceptsLegacyUUIDFilenameForErasure() throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        let first = try f.store(); let record = try MemoryPending(command()); try first.append(record)
        try first.recordRejection(record, status: 409, code: "INPUT_CONFLICT", validateBinding: {})
        let originalFile = f.root.appendingPathComponent(digest(Data(record.operationID.utf8)) + ".memory")
        try FileManager.default.moveItem(at: originalFile, to: f.root.appendingPathComponent(UUID().uuidString + ".memory"))
        let reopened = try f.store(); try reopened.clearLocalFiles()
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.appendingPathExtension("CJMemoryRejections").path).isEmpty)
    }

    @Test func publicTypedAndHistoryStoresEraseTheirActualOriginalAndRejectionRecords() throws {
        let f = try MemoryCleanupFixture(); defer { f.dispose() }
        let typed = try TypedMemoryPendingStore(directory: f.root, maximumBytes: 100_000, maximumRecords: 20,
            namespace: f.namespace, keyID: f.keyID, key: { f.key })
        let record = TypedMemoryPending(try TypedMemoryCommand(operationID: "original", itemID: "item", subject: "self", slot: "preference",
            text: "中文原文", occurredAt: "去年", kind: .preference, travelContext: nil))
        try typed.append(record, validateBinding: {})
        try typed.recordRejection(record, status: 409, code: "INPUT_CONFLICT", validateBinding: {})
        try typed.clearLocalFiles()
        #expect(throws: MemoryFailure.storageUnavailable) { try typed.pending() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.appendingPathExtension("CJMemoryTypedRejectionsV2").path).isEmpty)
        let historyRoot = f.parent.appendingPathComponent("account-A.history-v1")
        try FileManager.default.createDirectory(at: historyRoot, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let history = try MemoryHistoryPendingStore(directory: historyRoot, maximumBytes: 100_000, maximumRecords: 20,
            namespace: f.namespace, keyID: f.keyID, key: { f.key })
        let bytes = Data(#"{"version":"MEMORY-HISTORY@1","conversation_id":"会话","generation":"generation","epoch":0,"enabled":false,"source_version":0,"withdrawal_epoch":1}"#.utf8)
        var parser = StrictMemoryJSON(bytes: Array(bytes))
        let settings = try MemoryHistorySettings(parser.document())
        let action = try MemoryHistoryPending(change: .enable, settings: settings)
        try history.append(action, validate: {})
        try history.recordRejection(action, status: 409, code: "MEMORY_HISTORY_CONFLICT", validate: {})
        try history.clearLocalFiles()
        #expect(throws: MemoryFailure.storageUnavailable) { try history.records() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: historyRoot.path).isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: historyRoot.appendingPathExtension("CJMemoryHistoryRejectionsV1").path).isEmpty)
    }

}
