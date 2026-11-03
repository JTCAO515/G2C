import Foundation
import Testing
import CryptoKit
import CJMessageKeys
@testable import CJMemoryClient

@MainActor struct ItemJournalRemovalTests {
    @Test(arguments: [false, true])
    func removesOnlyMatchingItemWithoutKeyCallbacksDuringExecution(legacyName: Bool) throws {
        let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: root) }
        let key = SymmetricKey(size: .bits256)
        var keyCalls = 0
        let journal = try MemoryEncryptedRecords<MemoryPending>(directory: root, maximumBytes: 100_000, maximumRecords: 10,
            namespace: .init(environment: UUID(), account: UUID(), purpose: .localMemoryPendingV1), keyID: UUID(), domain: "CJMemoryPending", key: { keyCalls += 1; return key })
        var firstCommand = command(); firstCommand.operation_id = UUID().uuidString
        let first = try MemoryPending(firstCommand)
        var secondCommand = command(); secondCommand.operation_id = UUID().uuidString; secondCommand.item_id = "other-item"
        let second = try MemoryPending(secondCommand)
        try journal.append(first); try journal.append(second)
        if legacyName {
            try FileManager.default.moveItem(at: root.appendingPathComponent(digest(Data(first.operationID.utf8)) + ".memory"),
                to: root.appendingPathComponent(UUID(uuidString: first.operationID)!.uuidString + ".memory"))
        }
        let otherFile = root.appendingPathComponent(digest(Data(second.operationID.utf8)) + ".memory")
        let otherBytes = try Data(contentsOf: otherFile)
        let plan = try journal.prepareRemoval { same($0.itemID, first.itemID) }
        let before = keyCalls
        try journal.performRemoval(plan)
        #expect(keyCalls == before)
        #expect(try Data(contentsOf: otherFile) == otherBytes)
        #expect(try journal.pending().map(\.operationID) == [second.operationID])
        #expect(throws: (any Error).self) { try journal.performRemoval(plan) }
    }

    @Test(arguments: ["replacement", "new-record", "corrupt", "directory"])
    func refusesChangedInventoryBeforeAnyRemoval(kind: String) throws {
        let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: root) }
        let key = SymmetricKey(size: .bits256)
        let journal = try MemoryEncryptedRecords<MemoryPending>(directory: root, maximumBytes: 100_000, maximumRecords: 10,
            namespace: .init(environment: UUID(), account: UUID(), purpose: .localMemoryPendingV1), keyID: UUID(), domain: "CJMemoryPending", key: { key })
        let first = try MemoryPending(command()); try journal.append(first)
        let target = root.appendingPathComponent(digest(Data(first.operationID.utf8)) + ".memory")
        let original = try Data(contentsOf: target)
        let plan = try journal.prepareRemoval { _ in true }
        switch kind {
        case "replacement":
            let displaced = root.appendingPathComponent("displaced")
            try FileManager.default.moveItem(at: target, to: displaced)
            try original.write(to: target); try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: target.path)
            try FileManager.default.removeItem(at: displaced)
        case "new-record":
            var new = command(); new.operation_id = "new-action"; new.item_id = "other-item"
            try journal.append(MemoryPending(new))
        case "directory":
            try FileManager.default.createDirectory(at: root.appendingPathComponent("unexpected"), withIntermediateDirectories: false)
        default: try Data("bad".utf8).write(to: target)
        }
        let before = try Data(contentsOf: target)
        #expect(throws: (any Error).self) { try journal.performRemoval(plan) }
        #expect(try Data(contentsOf: target) == before)
    }
}
