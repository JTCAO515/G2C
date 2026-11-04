import Foundation
import CryptoKit
import Testing
import CJMessageKeys
import CJTripClient
@testable import CJManualPreviewClient

/// A crash or short write during append must leave only a temporary entry, never a
/// partial record under its final name. Invalid final-name records still fail closed.
private struct CrashRecord: ScopedJournalRecord {
    let actionID: String
    func validate() throws { }
}
@MainActor private final class CrashFixture {
    let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
    let key = SymmetricKey(size: .bits256)
    let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localTripPendingV1)
    let keyID = UUID()
    init() throws { try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
    func dispose() { try? FileManager.default.removeItem(at: root) }
    func journal() throws -> ScopedJournal<CrashRecord> {
        let material = key
        return try ScopedJournal(directory: root, maximumBytes: 100_000, maximumRecords: 20,
            namespace: namespace, keyID: keyID, domain: "CJScopedOriginal.1", key: { material })
    }
    func file(_ id: String) -> URL {
        root.appendingPathComponent(SHA256.hash(data: Data(id.utf8)).map { String(format: "%02x", $0) }.joined() + ".scoped")
    }
    func names() throws -> [String] { try FileManager.default.contentsOfDirectory(atPath: root.path).sorted() }
}

@MainActor struct JournalCrashSafetyTests {
    @Test func leftoverTemporaryWriteNeitherBlocksNorJoinsTheJournal() throws {
        let f = try CrashFixture(); defer { f.dispose() }
        let journal = try f.journal()
        try journal.append(CrashRecord(actionID: "first"))
        // A crash between the synced temporary write and its rename: complete ciphertext, never committed.
        let complete = try Data(contentsOf: f.file("first"))
        try complete.write(to: f.root.appendingPathComponent(".write-" + UUID().uuidString))
        try complete.prefix(10).write(to: f.root.appendingPathComponent(".write-" + UUID().uuidString))

        #expect(try journal.pending().map(\.actionID) == ["first"])
        try journal.append(CrashRecord(actionID: "second"))
        #expect(try journal.pending().map(\.actionID).sorted() == ["first", "second"])
        #expect(try f.names().filter { $0.hasPrefix(".write-") }.count == 2, "append never adopts or removes another temporary entry")

        try journal.finishCleanup(journal.prepareCleanup())
        #expect(try f.names().isEmpty)
    }

    @Test(arguments: [0, 10, 40])
    func invalidFinalNameRecordStillFailsClosedUntilCleanup(length: Int) throws {
        let f = try CrashFixture(); defer { f.dispose() }
        let journal = try f.journal()
        try journal.append(CrashRecord(actionID: "first"))
        let bytes = try Data(contentsOf: f.file("first"))
        try bytes.prefix(length).write(to: f.file("second"))

        // Short files fail the size bound; longer truncations fail authentication.
        #expect(throws: (any Error).self) { try journal.pending() }
        #expect(throws: (any Error).self) { try journal.append(CrashRecord(actionID: "second")) }
        #expect(try Data(contentsOf: f.file("first")) == bytes)
        #expect(try Data(contentsOf: f.file("second")) == bytes.prefix(length))
        try journal.finishCleanup(journal.prepareCleanup())
        #expect(try f.names().isEmpty)
    }

    @Test func appendNeverReplacesARecordThatAppearsDuringTheLastCallback() throws {
        let f = try CrashFixture(); defer { f.dispose() }
        let journal = try f.journal()
        let planted = Data("planted".utf8)
        #expect(throws: TripFailure.storageUnavailable) {
            try journal.append(CrashRecord(actionID: "first")) { try planted.write(to: f.file("first")) }
        }
        #expect(try Data(contentsOf: f.file("first")) == planted)
        #expect(try f.names() == [f.file("first").lastPathComponent], "no temporary entry survives a refused append")
    }
}
