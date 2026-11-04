import Foundation
import Testing
@testable import CJNeedsClient

/// A crash or short write during append must leave only a temporary entry, never a
/// partial record under its final name. Invalid final-name records still fail closed.
@Suite @MainActor struct JournalCrashSafetyTests {
    private func names(_ url: URL) throws -> [String] { try FileManager.default.contentsOfDirectory(atPath: url.path).sorted() }
    private func recordFile(_ h: Harness, _ id: String) -> URL { h.root.appendingPathComponent(digest(Data(id.utf8)) + ".needs") }

    @Test func leftoverTemporaryWriteNeitherBlocksNorJoinsTheJournal() throws {
        let h = try Harness(); defer { h.clean(); try? FileManager.default.removeItem(at: h.root.appendingPathExtension("CJNeedsRejections")) }
        let store = try h.store()
        let first = try original("manual-1"), second = try original("manual-2")
        try store.append(first)
        let rejections = h.root.appendingPathExtension("CJNeedsRejections")
        try FileManager.default.createDirectory(at: rejections, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let reopened = try h.store()
        // A crash between the synced temporary write and its rename: complete ciphertext, never committed.
        let complete = try Data(contentsOf: recordFile(h, first.actionID))
        try complete.write(to: h.root.appendingPathComponent(".write-" + UUID().uuidString))
        try complete.prefix(10).write(to: h.root.appendingPathComponent(".write-" + UUID().uuidString))
        try Data().write(to: rejections.appendingPathComponent(".write-" + UUID().uuidString))

        #expect(try reopened.pending().map(\.actionID) == [first.actionID])
        #expect(try reopened.rejection(for: first) == nil)
        try reopened.append(second)
        try reopened.validateInventory([first.actionID, second.actionID])
        #expect(try reopened.pending().map(\.actionID).sorted() == [first.actionID, second.actionID])
        #expect(try names(h.root).filter { $0.hasPrefix(".write-") }.count == 2, "append never adopts or removes another temporary entry")

        try reopened.clearLocalFiles()
        #expect(try names(h.root).isEmpty)
        #expect(try names(rejections).isEmpty)
    }

    @Test(arguments: [0, 10, 40])
    func invalidFinalNameRecordStillFailsClosedUntilCleanup(length: Int) throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store()
        let first = try original("manual-1"), second = try original("manual-2")
        try store.append(first)
        let bytes = try Data(contentsOf: recordFile(h, first.actionID))
        try bytes.prefix(length).write(to: recordFile(h, second.actionID))

        // Short files fail the size bound; longer truncations fail authentication.
        #expect(throws: (any Error).self) { try store.pending() }
        #expect(throws: (any Error).self) { try store.append(second) }
        #expect(try Data(contentsOf: recordFile(h, first.actionID)) == bytes)
        #expect(try Data(contentsOf: recordFile(h, second.actionID)) == bytes.prefix(length))
        try store.clearLocalFiles()
        #expect(try names(h.root).isEmpty)
    }

    @Test func appendNeverReplacesARecordThatAppearsDuringTheLastCallback() throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store()
        let record = try original(), planted = Data("planted".utf8)
        #expect(throws: NeedsFailure.storageUnavailable) {
            try store.append(record) { try planted.write(to: recordFile(h, record.actionID)) }
        }
        #expect(try Data(contentsOf: recordFile(h, record.actionID)) == planted)
        #expect(try names(h.root) == [digest(Data(record.actionID.utf8)) + ".needs"], "no temporary entry survives a refused append")
    }
}
