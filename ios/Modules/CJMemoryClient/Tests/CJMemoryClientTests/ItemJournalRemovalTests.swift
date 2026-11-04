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
    // A crash between the synced temporary write and its rename leaves a hidden entry that
    // may hold an erased item's complete ciphertext even when no committed record names it.
    // The action behind it was never sent, so item erasure removes every such entry.
    @Test func erasesCrashLeftoverTemporariesEvenWithoutAMatchingRecord() throws {
        let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: root) }
        let key = SymmetricKey(size: .bits256)
        var keyCalls = 0
        let journal = try MemoryEncryptedRecords<MemoryPending>(directory: root, maximumBytes: 100_000, maximumRecords: 10,
            namespace: .init(environment: UUID(), account: UUID(), purpose: .localMemoryPendingV1), keyID: UUID(), domain: "CJMemoryPending", key: { keyCalls += 1; return key })
        let erased = try MemoryPending(command())
        var otherCommand = command(); otherCommand.item_id = "other-item"
        let other = try MemoryPending(otherCommand)
        try journal.append(erased)
        let erasedFile = root.appendingPathComponent(digest(Data(erased.operationID.utf8)) + ".memory")
        let complete = try Data(contentsOf: erasedFile)
        try FileManager.default.removeItem(at: erasedFile)
        try journal.append(other)
        try journal.recordRejection(other, status: 409, code: "ORIGINAL_CONFLICT", domain: "CJMemoryRejections", validateBinding: {})
        let rejections: MemoryEncryptedRecords<MemoryRejectedOperation<MemoryPending>> = try #require(try journal.adjacentRecords(domain: "CJMemoryRejections", create: false))
        let rejectionRoot = root.appendingPathExtension("CJMemoryRejections")
        defer { try? FileManager.default.removeItem(at: rejectionRoot) }
        let otherFile = root.appendingPathComponent(digest(Data(other.operationID.utf8)) + ".memory")
        let otherBytes = try Data(contentsOf: otherFile)
        let rejectionFile = rejectionRoot.appendingPathComponent(digest(Data(other.operationID.utf8)) + ".memory")
        let rejectionBytes = try Data(contentsOf: rejectionFile)
        try complete.write(to: root.appendingPathComponent(".write-" + UUID().uuidString))
        try complete.prefix(10).write(to: root.appendingPathComponent(".write-" + UUID().uuidString))
        try complete.write(to: rejectionRoot.appendingPathComponent(".write-" + UUID().uuidString))

        let plans = (try journal.prepareRemoval { same($0.itemID, erased.itemID) },
                     try rejections.prepareRemoval { same($0.original.itemID, erased.itemID) })
        let before = keyCalls
        try journal.performRemoval(plans.0); try rejections.performRemoval(plans.1)
        #expect(keyCalls == before)
        #expect(try FileManager.default.contentsOfDirectory(atPath: root.path) == [otherFile.lastPathComponent])
        #expect(try FileManager.default.contentsOfDirectory(atPath: rejectionRoot.path) == [rejectionFile.lastPathComponent])
        #expect(try Data(contentsOf: otherFile) == otherBytes)
        #expect(try Data(contentsOf: rejectionFile) == rejectionBytes)
        #expect(try journal.pending().map(\.operationID) == [other.operationID])
    }

    // Temporary entries take the same regular-file, single-link, own-UID preflight as account
    // cleanup, and the plan's exact set and identities are rechecked before the first unlink.
    @Test(arguments: ["directory", "symlink", "hardlink", "late", "replaced"])
    func refusesUnsafeOrChangedTemporaryBeforeAnyRemoval(kind: String) throws {
        let parent = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        let root = parent.appendingPathComponent("journal")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: parent) }
        let key = SymmetricKey(size: .bits256)
        let journal = try MemoryEncryptedRecords<MemoryPending>(directory: root, maximumBytes: 100_000, maximumRecords: 10,
            namespace: .init(environment: UUID(), account: UUID(), purpose: .localMemoryPendingV1), keyID: UUID(), domain: "CJMemoryPending", key: { key })
        let first = try MemoryPending(command()); try journal.append(first)
        let target = root.appendingPathComponent(digest(Data(first.operationID.utf8)) + ".memory")
        let original = try Data(contentsOf: target)
        let outside = parent.appendingPathComponent("outside")
        try original.write(to: outside)
        let temporary = root.appendingPathComponent(".write-" + UUID().uuidString)
        switch kind {
        case "directory": try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false)
        case "symlink": try FileManager.default.createSymbolicLink(at: temporary, withDestinationURL: outside)
        case "hardlink": try FileManager.default.linkItem(at: outside, to: temporary)
        case "replaced": try original.write(to: temporary)
        default: break
        }
        if ["directory", "symlink", "hardlink"].contains(kind) {
            #expect(throws: MemoryFailure.storageUnavailable) { try journal.prepareRemoval { _ in true } }
        } else {
            let plan = try journal.prepareRemoval { _ in true }
            if kind == "late" { try original.write(to: temporary) }
            else {
                // Keep the displaced inode alive so the replacement cannot reuse its number.
                let displaced = parent.appendingPathComponent("displaced")
                try FileManager.default.moveItem(at: temporary, to: displaced)
                try original.write(to: temporary)
                try FileManager.default.removeItem(at: displaced)
            }
            #expect(throws: MemoryFailure.storageUnavailable) { try journal.performRemoval(plan) }
        }
        #expect(try Data(contentsOf: target) == original)
        #expect(try Data(contentsOf: outside) == original)
        #expect(FileManager.default.fileExists(atPath: temporary.path))
        #expect(try journal.pending().map(\.operationID) == [first.operationID])
    }
}
