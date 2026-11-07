import Foundation
import Testing
import CryptoKit
import CJMessageKeys
@testable import CJMemoryClient

/// A crash or short write during append must leave only a temporary entry, never a
/// partial record under its final name. Invalid final-name records still fail closed.
@MainActor private final class CrashFixture {
    let parent = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
    let key = SymmetricKey(size: .bits256)
    let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localMemoryPendingV1)
    let keyID = UUID()
    var root: URL { parent.appendingPathComponent("account-A") }
    var rejections: URL { root.appendingPathExtension("CJMemoryRejections") }
    init() throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    }
    func dispose() { try? FileManager.default.removeItem(at: parent) }
    func journal() throws -> MemoryEncryptedRecords<MemoryPending> {
        let material = key
        return try MemoryEncryptedRecords(directory: root, maximumBytes: 100_000, maximumRecords: 10,
            namespace: namespace, keyID: keyID, domain: "CJMemoryPending", key: { material })
    }
    func file(_ record: MemoryPending) -> URL { root.appendingPathComponent(digest(Data(record.operationID.utf8)) + ".memory") }
    func temporary(in directory: URL? = nil) -> URL { (directory ?? root).appendingPathComponent(".write-" + UUID().uuidString) }
    func names(_ url: URL) throws -> [String] { try FileManager.default.contentsOfDirectory(atPath: url.path).sorted() }
    /// A crash after the synced temporary write and before its rename: the record's
    /// complete ciphertext exists only under the writer's temporary name.
    func crashBeforeRename(_ record: MemoryPending) throws -> (temporary: URL, ciphertext: Data) {
        try journal().append(record)
        let ciphertext = try Data(contentsOf: file(record)), temporary = temporary()
        try FileManager.default.moveItem(at: file(record), to: temporary)
        return (temporary, ciphertext)
    }
}

@MainActor struct JournalCrashSafetyTests {
    @Test func leftoverTemporaryWriteNeitherBlocksNorJoinsTheJournal() throws {
        let f = try CrashFixture(); defer { f.dispose() }
        try f.journal().append(MemoryPending(command()))
        try FileManager.default.createDirectory(at: f.rejections, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let journal = try f.journal()
        let first = try #require(try journal.pending().first)
        var other = command(); other.item_id = "other-item"
        let second = try MemoryPending(other)
        // A crash between the synced temporary write and its rename: complete ciphertext, never committed.
        let complete = try Data(contentsOf: f.file(first))
        try complete.write(to: f.root.appendingPathComponent(".write-" + UUID().uuidString))
        try complete.prefix(10).write(to: f.root.appendingPathComponent(".write-" + UUID().uuidString))
        try Data().write(to: f.rejections.appendingPathComponent(".write-" + UUID().uuidString))

        #expect(try journal.pending().map(\.operationID) == [first.operationID])
        #expect(try journal.rejection(for: first, domain: "CJMemoryRejections") == nil)
        try journal.append(second)
        try journal.validateInventory([first, second])
        let plan = try journal.prepareRemoval { same($0.itemID, first.itemID) }
        try journal.performRemoval(plan)
        #expect(try journal.pending().map(\.operationID) == [second.operationID])
        // Item erasure cannot attribute an uncommitted (possibly truncated) ciphertext to an
        // item without a key, so it erases every crash leftover in the directory it plans.
        // The rejection sidecar's leftover belongs to that sidecar's own removal plan.
        #expect(try f.names(f.root) == [f.file(second).lastPathComponent], "removal erases this directory's temporary entries")
        #expect(try f.names(f.rejections).filter { $0.hasPrefix(".write-") }.count == 1)

        try journal.clearLocalFiles()
        #expect(try f.names(f.root).isEmpty)
        #expect(try f.names(f.rejections).isEmpty)
    }

    @Test(arguments: [0, 10, 40])
    func invalidFinalNameRecordStillFailsClosedUntilCleanup(length: Int) throws {
        let f = try CrashFixture(); defer { f.dispose() }
        let journal = try f.journal()
        let first = try MemoryPending(command()), second = try MemoryPending(command())
        try journal.append(first)
        let bytes = try Data(contentsOf: f.file(first))
        try bytes.prefix(length).write(to: f.file(second))

        // Short files fail the size bound; longer truncations fail authentication.
        #expect(throws: (any Error).self) { try journal.pending() }
        #expect(throws: (any Error).self) { try journal.append(second) }
        #expect(throws: (any Error).self) { try journal.prepareRemoval { _ in true } }
        #expect(try Data(contentsOf: f.file(first)) == bytes)
        #expect(try Data(contentsOf: f.file(second)) == bytes.prefix(length))
        try journal.clearLocalFiles()
        #expect(try f.names(f.root).isEmpty)
    }

    @Test func appendNeverReplacesARecordThatAppearsDuringTheLastCallback() throws {
        let f = try CrashFixture(); defer { f.dispose() }
        let journal = try f.journal()
        let record = try MemoryPending(command()), planted = Data("planted".utf8)
        #expect(throws: MemoryFailure.storageUnavailable) {
            try journal.append(record) { try planted.write(to: f.file(record)) }
        }
        #expect(try Data(contentsOf: f.file(record)) == planted)
        #expect(try f.names(f.root) == [f.file(record).lastPathComponent], "no temporary entry survives a refused append")
    }

    @Test func itemRemovalErasesTheItemsOnlyCiphertextLeftByACrashBeforeRename() throws {
        let f = try CrashFixture(); defer { f.dispose() }
        let target = try MemoryPending(command()), other = try MemoryPending(command())
        let crash = try f.crashBeforeRename(target)
        let journal = try f.journal()
        try journal.append(other)
        try crash.ciphertext.prefix(40).write(to: f.temporary())
        let otherBytes = try Data(contentsOf: f.file(other))
        #expect(try journal.pending().map(\.operationID) == [other.operationID])

        // No committed record matches the item, yet its ciphertext must not outlive the erasure.
        let plan = try journal.prepareRemoval { same($0.itemID, target.itemID) }
        try journal.performRemoval(plan)
        #expect(try f.names(f.root) == [f.file(other).lastPathComponent])
        #expect(try Data(contentsOf: f.file(other)) == otherBytes)
        #expect(try journal.pending().map(\.operationID) == [other.operationID])
    }

    @Test(arguments: ["symlink", "directory", "hardlink"])
    func itemRemovalRefusesUnsafeTemporaryEntriesBeforeAnyUnlink(kind: String) throws {
        let f = try CrashFixture(); defer { f.dispose() }
        let journal = try f.journal()
        let target = try MemoryPending(command()); try journal.append(target)
        let bytes = try Data(contentsOf: f.file(target))
        let outside = f.parent.appendingPathComponent("outside"), marker = Data("outside".utf8)
        try marker.write(to: outside)
        let entry = f.temporary()
        switch kind {
        case "symlink": try FileManager.default.createSymbolicLink(at: entry, withDestinationURL: outside)
        case "directory": try FileManager.default.createDirectory(at: entry, withIntermediateDirectories: false)
        default: try FileManager.default.linkItem(at: outside, to: entry)
        }
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.prepareRemoval { _ in true } }
        #expect(try Data(contentsOf: f.file(target)) == bytes)
        #expect(try f.names(f.root).contains(entry.lastPathComponent))
        #expect(try Data(contentsOf: outside) == marker)
    }

    @Test(arguments: ["added", "replaced", "hardlinked", "removed"])
    func itemRemovalRefusesTemporaryEntriesChangedAfterPreflight(kind: String) throws {
        let f = try CrashFixture(); defer { f.dispose() }
        let journal = try f.journal()
        let target = try MemoryPending(command()); try journal.append(target)
        let bytes = try Data(contentsOf: f.file(target))
        let leftover = f.temporary(); try bytes.write(to: leftover)
        let plan = try journal.prepareRemoval { _ in true }
        switch kind {
        case "added": try Data().write(to: f.temporary())
        case "replaced":
            let replacement = f.parent.appendingPathComponent("replacement")
            try bytes.write(to: replacement)
            try FileManager.default.removeItem(at: leftover)
            try FileManager.default.moveItem(at: replacement, to: leftover)
        case "hardlinked": try FileManager.default.linkItem(at: leftover, to: f.parent.appendingPathComponent("held"))
        default: try FileManager.default.removeItem(at: leftover)
        }
        #expect(throws: MemoryFailure.storageUnavailable) { try journal.performRemoval(plan) }
        #expect(try Data(contentsOf: f.file(target)) == bytes, "no unlink follows a failed recheck")
    }
}
