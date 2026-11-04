import Foundation
import CryptoKit
import Testing
import CJMessageKeys
@testable import CJTripClient

/// A crash or short write during append must leave only a temporary entry, never a
/// partial record under its final name. Invalid final-name records still fail closed.
@Suite @MainActor struct JournalCrashSafetyTests {
    private func names(_ url: URL) throws -> [String] { try FileManager.default.contentsOfDirectory(atPath: url.path).sorted() }
    private func recordFile(_ h: Harness, _ id: String) -> URL { h.root.appendingPathComponent(digest(Data(id.utf8)) + ".trip") }

    @Test func leftoverTemporaryWriteNeitherBlocksNorJoinsTheJournal() throws {
        let h = try Harness(); defer {
            h.clean(); for url in TripPendingStore.manualNamespaceDirectories(at: h.root) { try? FileManager.default.removeItem(at: url) }
        }
        let store = try h.store()
        try store.append(pending(.accept))
        let manual: TripEncryptedRecords<TripPending> = try #require(try store.manualRecords(maximumBytes: 100_000, maximumRecords: 10, create: true))
        // A crash between the synced temporary write and its rename: complete ciphertext, never committed.
        let complete = try Data(contentsOf: recordFile(h, "accept1"))
        try complete.write(to: h.root.appendingPathComponent(".write-" + UUID().uuidString))
        try complete.prefix(10).write(to: h.root.appendingPathComponent(".write-" + UUID().uuidString))
        try Data().write(to: h.root.appendingPathExtension("CJTripManual").appendingPathComponent(".write-" + UUID().uuidString))

        #expect(try store.pending().map(\.actionID) == ["accept1"])
        #expect(try manual.pending().isEmpty)
        try store.requireLegacyWritesAllowed()
        try store.append(pending(.reject))
        try store.validateInventory(["accept1", "reject1"])
        #expect(try store.pending().map(\.actionID).sorted() == ["accept1", "reject1"])
        #expect(try names(h.root).filter { $0.hasPrefix(".write-") }.count == 2, "append never adopts or removes another temporary entry")

        try store.clearLocalFiles()
        for url in [h.root, h.root.appendingPathExtension("CJTripManual")] { #expect(try names(url).isEmpty) }
        // Key creation still needs a literally empty namespace.
        try Data().write(to: h.root.appendingPathComponent(".write-" + UUID().uuidString))
        #expect(throws: TripFailure.keyUnavailable) { try TripPendingStore.requireEmptyNamespace(directory: h.root) }
    }

    @Test(arguments: [0, 10, 40])
    func invalidFinalNameRecordStillFailsClosedUntilCleanup(length: Int) throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store()
        try store.append(pending(.accept))
        let original = try Data(contentsOf: recordFile(h, "accept1"))
        try original.prefix(length).write(to: recordFile(h, "reject1"))

        // Short files fail the size bound; longer truncations fail authentication.
        #expect(throws: (any Error).self) { try store.pending() }
        #expect(throws: (any Error).self) { try store.append(pending(.reject)) }
        #expect(try Data(contentsOf: recordFile(h, "accept1")) == original)
        #expect(try Data(contentsOf: recordFile(h, "reject1")) == original.prefix(length))
        try store.clearLocalFiles()
        #expect(try names(h.root).isEmpty)
    }

    @Test func appendNeverReplacesARecordThatAppearsDuringTheLastCallback() throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store()
        let planted = Data("planted".utf8)
        #expect(throws: TripFailure.storageUnavailable) {
            try store.append(pending(.accept)) { try planted.write(to: recordFile(h, "accept1")) }
        }
        #expect(try Data(contentsOf: recordFile(h, "accept1")) == planted)
        #expect(try names(h.root) == [digest(Data("accept1".utf8)) + ".trip"], "no temporary entry survives a refused append")
    }
}
