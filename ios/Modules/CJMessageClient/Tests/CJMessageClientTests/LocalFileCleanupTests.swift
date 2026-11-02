import Foundation
import CryptoKit
import Darwin
import Testing
@testable import CJMessageClient

@MainActor private final class CleanupKeys: MessageEncryptionKeyProvider {
    let key = MessageStorageKey(id: UUID(), key: SymmetricKey(size: .bits256))
    var lookups = 0
    func existing(for scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey? {
        lookups += 1; return key
    }
}

@Suite @MainActor struct LocalFileCleanupTests {
    private func root() -> URL {
        FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj-message-cleanup-" + UUID().uuidString)
    }
    @Test func physicalRemovalIsScopeLimitedIdempotentAndUsesNoKey() throws {
        let keys = CleanupKeys(), directory = root()
        defer { try? FileManager.default.removeItem(at: directory) }
        let storage = try EncryptedFileStorage(directory: directory, keys: keys)
        let a = try StorageScope(environment: "local", account: "a")
        let b = try StorageScope(environment: "local", account: "b")
        try storage.save(Snapshot(), scope: a); try storage.save(Snapshot(), scope: b)
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).count == 2)
        let before = keys.lookups
        try storage.clearLocalSnapshot(scope: a)
        try storage.clearLocalSnapshot(scope: a)
        #expect(keys.lookups == before)
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).count == 1)
        let reopened = try EncryptedFileStorage(directory: directory, keys: keys)
        #expect(try reopened.load(scope: a) == nil)
        #expect(try reopened.load(scope: b) != nil)
    }
    @Test func rejectsLinksAndReplacedDirectoryWithoutDeletingOtherData() throws {
        let keys = CleanupKeys(), directory = root()
        let scope = try StorageScope(environment: "local", account: "a")
        let storage = try EncryptedFileStorage(directory: directory, keys: keys)
        let moved = directory.appendingPathExtension("original")
        defer { try? FileManager.default.removeItem(at: directory); try? FileManager.default.removeItem(at: moved) }
        try storage.save(Snapshot(), scope: scope)
        let file = try #require(FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil).first)
        let other = directory.appendingPathComponent("keep")
        try FileManager.default.moveItem(at: file, to: other)
        let original = try Data(contentsOf: other)
        try FileManager.default.createSymbolicLink(at: file, withDestinationURL: other)
        #expect(throws: RecoveryError.self) { try storage.clearLocalSnapshot(scope: scope) }
        try FileManager.default.removeItem(at: file)
        #expect(link(other.path, file.path) == 0)
        #expect(throws: RecoveryError.self) { try storage.clearLocalSnapshot(scope: scope) }
        #expect(try Data(contentsOf: other) == original)
        try FileManager.default.moveItem(at: directory, to: moved)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        #expect(throws: RecoveryError.self) { try storage.clearLocalSnapshot(scope: scope) }
        #expect(try Data(contentsOf: moved.appendingPathComponent("keep")) == original)
    }
}
