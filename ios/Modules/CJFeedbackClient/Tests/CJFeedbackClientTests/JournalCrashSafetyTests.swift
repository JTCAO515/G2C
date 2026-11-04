import Foundation
import Testing
@testable import CJFeedbackClient

/// A crash or short write during append must leave only a temporary entry, never a
/// partial record under its final name. Invalid final-name records still fail closed.
@Suite @MainActor struct JournalCrashSafetyTests {
    private func names(_ url: URL) throws -> [String] { try FileManager.default.contentsOfDirectory(atPath: url.path).sorted() }
    private func recordFile(_ h: Harness, _ id: String) -> URL { h.root.appendingPathComponent(digest(Data(id.utf8)) + ".feedback") }

    @Test func leftoverTemporaryWriteNeitherBlocksNorJoinsTheJournal() throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store()
        let first = try pending(), second = try pending(actionID: "feedback-second")
        try store.append(first)
        // A crash between the synced temporary write and its rename: complete ciphertext, never committed.
        let complete = try Data(contentsOf: recordFile(h, first.actionID))
        try complete.write(to: h.root.appendingPathComponent(".write-" + UUID().uuidString))
        try complete.prefix(10).write(to: h.root.appendingPathComponent(".write-" + UUID().uuidString))

        #expect(try store.pending().map(\.actionID) == [first.actionID])
        try store.append(second)
        try store.validateInventory([first, second])
        #expect(try store.pending().map(\.actionID).sorted() == [first.actionID, second.actionID].sorted())
        #expect(try names(h.root).filter { $0.hasPrefix(".write-") }.count == 2, "append never adopts or removes another temporary entry")

        try store.clearLocalFiles()
        #expect(try names(h.root).isEmpty)
    }

    @Test(arguments: [0, 10, 40])
    func invalidFinalNameRecordStillFailsClosedUntilCleanup(length: Int) throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store()
        let first = try pending(), second = try pending(actionID: "feedback-second")
        try store.append(first)
        let original = try Data(contentsOf: recordFile(h, first.actionID))
        try original.prefix(length).write(to: recordFile(h, second.actionID))

        // Short files fail the size bound; longer truncations fail authentication.
        #expect(throws: (any Error).self) { try store.pending() }
        #expect(throws: (any Error).self) { try store.append(second) }
        #expect(try Data(contentsOf: recordFile(h, first.actionID)) == original)
        #expect(try Data(contentsOf: recordFile(h, second.actionID)) == original.prefix(length))
        try store.clearLocalFiles()
        #expect(try names(h.root).isEmpty)
    }

    @Test func appendNeverReplacesARecordThatAppearsDuringTheLastCallback() throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store()
        let record = try pending(), planted = Data("planted".utf8)
        #expect(throws: FeedbackFailure.storageUnavailable) {
            try store.append(record) { try planted.write(to: recordFile(h, record.actionID)) }
        }
        #expect(try Data(contentsOf: recordFile(h, record.actionID)) == planted)
        #expect(try names(h.root) == [digest(Data(record.actionID.utf8)) + ".feedback"], "no temporary entry survives a refused append")
    }
}
