import Foundation
import Darwin
import CryptoKit
import Testing
import CJMessageKeys
@testable import CJNeedsClient

@MainActor private final class NeedsCleanupFixture {
    let parent = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
    let key = SymmetricKey(size: .bits256)
    let keyID = UUID()
    let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localNeedsPendingV1)
    var root: URL { parent.appendingPathComponent("account-A") }
    init() throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    }
    func dispose() { try? FileManager.default.removeItem(at: parent) }
    func store(at path: URL? = nil, key: (() throws -> SymmetricKey)? = nil) throws -> NeedsPendingStore {
        let material = self.key
        return try NeedsPendingStore(directory: path ?? root, maximumBytes: 524_288, maximumRecords: 20,
            namespace: namespace, keyID: keyID, key: key ?? { material })
    }
}

@MainActor struct LocalJournalCleanupTests {
    @Test func clearsWithoutKeyPreservesOtherAccountAndPermanentlyRetiresOriginalStore() throws {
        let f = try NeedsCleanupFixture(); defer { f.dispose() }
        var keyAvailable = true; var calls = 0
        let journal = try f.store { calls += 1; guard keyAvailable else { throw NeedsFailure.keyUnavailable }; return f.key }
        let record = try original()
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
        #expect(throws: NeedsFailure.storageUnavailable) { try journal.pending() }
        #expect(throws: NeedsFailure.storageUnavailable) { try journal.append(record) }
        try journal.clearLocalFiles()
        #expect(calls == before)
        #expect(try f.store().pending().isEmpty)
    }
    @Test(arguments: ["unknown", "directory", "symlink", "hardlink"])
    func rejectsUnexpectedEntryBeforeErasingAndAllowsOriginalTargetRetry(kind: String) throws {
        let f = try NeedsCleanupFixture(); defer { f.dispose() }
        let journal = try f.store(); let record = try original(); try journal.append(record)
        let originalFile = try #require(FileManager.default.contentsOfDirectory(at: f.root, includingPropertiesForKeys: nil).first)
        let bytes = try Data(contentsOf: originalFile)
        let bad = f.root.appendingPathComponent(kind == "unknown" ? "unexpected" : String(repeating: "a", count: 64) + ".needs")
        switch kind {
        case "directory": try FileManager.default.createDirectory(at: bad, withIntermediateDirectories: false)
        case "symlink": try FileManager.default.createSymbolicLink(at: bad, withDestinationURL: originalFile)
        case "hardlink": try FileManager.default.linkItem(at: originalFile, to: bad)
        default: try Data("unknown".utf8).write(to: bad)
        }
        #expect(throws: NeedsFailure.storageUnavailable) { try journal.clearLocalFiles() }
        #expect(try Data(contentsOf: originalFile) == bytes)
        #expect(throws: NeedsFailure.storageUnavailable) { try journal.append(record) }
        try FileManager.default.removeItem(at: bad)
        try journal.clearLocalFiles()
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test func originalDirectoryReplacementCannotEraseReplacementOrDisplacedData() throws {
        let f = try NeedsCleanupFixture(); defer { f.dispose() }
        let journal = try f.store(); try journal.append(original())
        let displaced = f.parent.appendingPathComponent("displaced")
        try FileManager.default.moveItem(at: f.root, to: displaced)
        try FileManager.default.createDirectory(at: f.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let replacement = try f.store(); try replacement.append(original())
        #expect(throws: NeedsFailure.storageUnavailable) { try journal.clearLocalFiles() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).count == 1)
        #expect(try FileManager.default.contentsOfDirectory(atPath: displaced.path).count == 1)
        try FileManager.default.removeItem(at: f.root)
        try FileManager.default.moveItem(at: displaced, to: f.root)
        try journal.clearLocalFiles()
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test func cleanupInsideLastBindingCallbackPreventsLateAppend() throws {
        let f = try NeedsCleanupFixture(); defer { f.dispose() }
        let journal = try f.store(); let record = try original()
        #expect(throws: NeedsFailure.storageUnavailable) {
            try journal.append(record) { try journal.clearLocalFiles() }
        }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test func cleanupInsideKeyCallbackWithholdsAlreadyDecryptedResult() throws {
        let f = try NeedsCleanupFixture(); defer { f.dispose() }
        var erase = false; var journal: NeedsPendingStore!
        journal = try f.store {
            if erase { try journal.clearLocalFiles() }
            return f.key
        }
        try journal.append(original())
        erase = true
        #expect(throws: NeedsFailure.storageUnavailable) { try journal.pending() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
    }
    @Test func actualRejectedOriginalSidecarIsClearedWithoutKeyAndHeldProofIsRetired() throws {
        let f = try NeedsCleanupFixture(); defer { f.dispose() }
        var keyAvailable = true
        let journal = try f.store { guard keyAvailable else { throw NeedsFailure.keyUnavailable }; return f.key }
        let record = try original(); try journal.append(record)
        let response = NeedsSchema.ErrorResponse(request_id: UUID().uuidString, error: .init(
            code: "NEEDS_CONFLICT", category: "input", message_en: "Unavailable", message_zh: "不可用", outcome: .failed, recovery: .do_not_retry))
        try journal.recordRejection(record, status: 409, response: response, validateBinding: {})
        let observed = try journal.rejectionProof(for: record)
        let proof = try #require(observed)
        keyAvailable = false
        try journal.clearLocalFiles()
        #expect(throws: NeedsFailure.storageUnavailable) { try proof.validateDurability() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.appendingPathExtension("CJNeedsRejections").path).isEmpty)
    }
    @Test(arguments: [true, false])
    func sidecarReplacementOrLateAppearanceCannotBeAdopted(initiallyPresent: Bool) throws {
        let f = try NeedsCleanupFixture(); defer { f.dispose() }
        let sidecar = f.root.appendingPathExtension("CJNeedsRejections")
        if initiallyPresent { try FileManager.default.createDirectory(at: sidecar, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        let journal = try f.store(); try journal.append(original())
        if initiallyPresent { try FileManager.default.moveItem(at: sidecar, to: f.parent.appendingPathComponent("old-sidecar")) }
        try FileManager.default.createDirectory(at: sidecar, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let sentinel = sidecar.appendingPathComponent(String(repeating: "a", count: 64) + ".needs")
        try Data("keep".utf8).write(to: sentinel)
        #expect(throws: NeedsFailure.storageUnavailable) { try journal.clearLocalFiles() }
        #expect(try Data(contentsOf: sentinel) == Data("keep".utf8))
        #expect(try FileManager.default.contentsOfDirectory(atPath: f.root.path).count == 1)
    }

}
