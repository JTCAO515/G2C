import Foundation
import Darwin
import CryptoKit
import Testing
import CJMessageKeys
import CJTripClient
@testable import CJManualPreviewClient

private struct ErasureRecord: ScopedJournalRecord {
    let actionID: String
    func validate() throws { }
}
@MainActor private final class ErasureFixture {
    let parent = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
    var root: URL { parent.appendingPathComponent("original") }
    let key = SymmetricKey(size: .bits256)
    let keyID = UUID()
    let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localTripPendingV1)
    init() throws { try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700]) }
    func journal(key: (() throws -> SymmetricKey)? = nil) throws -> ScopedJournal<ErasureRecord> {
        let material = self.key
        return try ScopedJournal(directory: root, maximumBytes: 100_000, maximumRecords: 20,
            namespace: namespace, keyID: keyID, domain: "CJScopedOriginal.1", key: key ?? { material })
    }
    func dispose() { try? FileManager.default.removeItem(at: parent) }
}
@MainActor struct ScopedJournalCleanupTests {
    @Test func exactNoKeyErasureKeepsSiblingAndRetiresJournal() throws {
        let f = try ErasureFixture(); defer { f.dispose() }
        var available = true; var calls = 0
        let journal = try f.journal { calls += 1; guard available else { throw TripFailure.keyUnavailable }; return f.key }
        try journal.append(ErasureRecord(actionID: "original"))
        let sibling = f.parent.appendingPathComponent("other"); try Data("other account".utf8).write(to: sibling)
        available = false; let before = calls
        try journal.finishCleanup(journal.prepareCleanup())
        #expect(calls == before)
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
        #expect(try Data(contentsOf: sibling) == Data("other account".utf8))
        #expect(throws: TripFailure.storageUnavailable) { try journal.pending() }
        #expect(throws: TripFailure.storageUnavailable) { try journal.append(ErasureRecord(actionID: "late")) }
    }
    @Test(arguments: ["unknown", "symlink", "hardlink", "directory"])
    func unexpectedEntryRefusesBeforeUnlinkAndOriginalRetrySucceeds(kind: String) throws {
        let f = try ErasureFixture(); defer { f.dispose() }; let journal = try f.journal()
        try journal.append(ErasureRecord(actionID: "original"))
        let original = try #require(FileManager.default.contentsOfDirectory(at: f.root, includingPropertiesForKeys: nil).first)
        let bytes = try Data(contentsOf: original)
        let bad = f.root.appendingPathComponent(kind == "unknown" ? "unknown" : String(repeating: "a", count: 64) + ".scoped")
        switch kind {
        case "symlink": try FileManager.default.createSymbolicLink(at: bad, withDestinationURL: original)
        case "hardlink": try FileManager.default.linkItem(at: original, to: bad)
        case "directory": try FileManager.default.createDirectory(at: bad, withIntermediateDirectories: false)
        default: try Data("unknown".utf8).write(to: bad)
        }
        #expect(throws: TripFailure.storageUnavailable) { try journal.prepareCleanup() }
        #expect(try Data(contentsOf: original) == bytes)
        #expect(throws: TripFailure.storageUnavailable) { try journal.pending() }
        try FileManager.default.removeItem(at: bad)
        try journal.finishCleanup(journal.prepareCleanup())
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test func directoryAndNamedFileReplacementCannotBecomeCleanupTarget() throws {
        let f = try ErasureFixture(); defer { f.dispose() }; let journal = try f.journal()
        try journal.append(ErasureRecord(actionID: "original"))
        let proof = try journal.prepareCleanup()
        let file = try #require(FileManager.default.contentsOfDirectory(at: f.root, includingPropertiesForKeys: nil).first)
        let saved = f.parent.appendingPathComponent("saved.scoped")
        try FileManager.default.moveItem(at: file, to: saved)
        try Data("replacement".utf8).write(to: file)
        #expect(throws: TripFailure.exchangeUnknown) { try journal.finishCleanup(proof) }
        #expect(try Data(contentsOf: file) == Data("replacement".utf8))
        try FileManager.default.removeItem(at: file); try FileManager.default.moveItem(at: saved, to: file)
        let displaced = f.parent.appendingPathComponent("displaced")
        try FileManager.default.moveItem(at: f.root, to: displaced)
        try FileManager.default.createDirectory(at: f.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let sentinel = f.root.appendingPathComponent(file.lastPathComponent); try Data("other".utf8).write(to: sentinel)
        #expect(throws: TripFailure.storageUnavailable) { try journal.prepareCleanup() }
        #expect(try Data(contentsOf: sentinel) == Data("other".utf8))
        #expect(try FileManager.default.contentsOfDirectory(atPath: displaced.path).count == 1)
    }
    @Test func clearInsideFinalBindingAndKeyCallbacksWithholdsReadAndWrite() throws {
        let f = try ErasureFixture(); defer { f.dispose() }
        let journal = try f.journal()
        #expect(throws: TripFailure.storageUnavailable) {
            try journal.append(ErasureRecord(actionID: "late")) {
                try journal.finishCleanup(journal.prepareCleanup())
            }
        }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
        var erase = false; var reopened: ScopedJournal<ErasureRecord>!
        reopened = try f.journal {
            if erase { try reopened.finishCleanup(reopened.prepareCleanup()) }
            return f.key
        }
        try reopened.append(ErasureRecord(actionID: "read")); erase = true
        #expect(throws: TripFailure.storageUnavailable) { try reopened.pending() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
}
