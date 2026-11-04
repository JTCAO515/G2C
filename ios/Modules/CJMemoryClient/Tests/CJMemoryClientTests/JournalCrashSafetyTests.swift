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
    func names(_ url: URL) throws -> [String] { try FileManager.default.contentsOfDirectory(atPath: url.path).sorted() }
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
        #expect(try f.names(f.root).filter { $0.hasPrefix(".write-") }.count == 2, "append and removal never adopt or remove another temporary entry")

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
}
