import CJMessageClient
import CryptoKit
import Foundation
import Testing
@testable import CJLioUser
@testable import CJMessageKeys
@testable import LioPositionStoreAcceptance

@MainActor private final class PositionKeys: MessageKeyPersistence {
    var record: MessageKeyRecord?
    var additions = 0
    func read() throws -> MessageKeyRecord? { record }
    func add(_ value: MessageKeyRecord) throws { additions += 1; record = value }
    func remove(expectedID: UUID) throws { record = nil }
}
@MainActor private final class PositionFixture {
    let directory: URL
    let namespace: MessageKeyNamespace
    let records = PositionKeys()
    let keys: ScopedMessageKeyProvider
    var active = true
    init() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("synthetic-lio-position-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        namespace = .init(environment: UUID(), account: UUID(), purpose: .localMessageStorageV1)
        keys = ScopedMessageKeyProvider(namespace: namespace, persistence: records, randomBytes: { Data(repeating: 7, count: 32) })
        _ = try keys.create(storageState: .confirmedEmpty, for: keys.begin(.create))
    }
    func store() throws -> LioChatPositionStore {
        try .init(directory: directory, namespace: namespace, keys: keys, validate: { [self] in
            guard active else { throw RecoveryError.inactive }
        })
    }
    func cleanup() {
        do { try FileManager.default.removeItem(at: directory) }
        catch { Issue.record("Synthetic position directory cleanup failed") }
    }
}
@MainActor struct LioChatPositionStoreTests {
    @Test func authenticatedBindingLoadsTheOldPositionAndKeepsLaterDraftChanges() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        let original = LioChatContinuity()
        original.draft = "  北京三天原草稿\n "
        original.selectedID = Data("synthetic-selected".utf8)
        let store = try f.store()
        try store.save(original.encodedPosition())
        let current = LioChatContinuity()
        try restoreLioChatPosition(current, store: store)
        #expect(current.draft == original.draft && current.selectedID == original.selectedID)
        current.draft = "  最后一个字符也保留。 "
        let reopened = LioChatContinuity()
        try reopened.restorePosition(try #require(try store.load()))
        #expect(reopened.draft.utf8.elementsEqual(current.draft.utf8))
    }
    @Test func unreadablePositionIsNotSilentlyReplacedByABlankState() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        let store = try f.store()
        let original = Data("synthetic invalid position".utf8)
        try store.save(original)
        let current = LioChatContinuity(); current.draft = "Keep the visible draft"
        #expect(throws: RecoveryError.invalidSnapshot) { try restoreLioChatPosition(current, store: store) }
        #expect(current.draft == "Keep the visible draft")
        #expect(try store.load() == original)
    }
    @Test func encryptedStateSurvivesASeparateStoreWithoutPlaintext() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        let original = Data("synthetic draft: 北京三日; first ID and original bytes stay unchanged".utf8)
        try f.store().save(original)
        let reopened = try f.store()
        #expect(try reopened.load() == original)
        let file = f.directory.appendingPathComponent(LioChatPositionStore.filename)
        let encrypted = try Data(contentsOf: file)
        #expect(encrypted.range(of: original) == nil)
        #expect((try FileManager.default.attributesOfItem(atPath: file.path)[.posixPermissions] as? NSNumber)?.intValue == 0o600)
    }
    @Test func missingKeyNeverCreatesAReplacementOrTreatsStateAsEmpty() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        try f.store().save(Data("synthetic private draft".utf8))
        f.records.record = nil
        #expect(throws: (any Error).self) { _ = try f.store().load() }
        #expect(throws: (any Error).self) { try f.store().save(Data("replacement".utf8)) }
        #expect(f.records.additions == 1)
    }
    @Test func corruptedCiphertextIsNotOverwritten() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        try f.store().save(Data("synthetic original draft".utf8))
        let file = f.directory.appendingPathComponent(LioChatPositionStore.filename)
        var damaged = try Data(contentsOf: file); damaged[damaged.count - 1] ^= 1
        try damaged.write(to: file)
        #expect(throws: (any Error).self) { _ = try f.store().load() }
        #expect(throws: (any Error).self) { try f.store().save(Data("replacement".utf8)) }
        #expect(try Data(contentsOf: file) == damaged)
    }
    @Test func differentAccountCannotReadTheSameCiphertextEvenWithTheSameSyntheticKey() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        try f.store().save(Data("synthetic account-bound draft".utf8))
        let otherRecords = PositionKeys(); otherRecords.record = f.records.record
        let other = MessageKeyNamespace(environment: f.namespace.environment, account: UUID(), purpose: .localMessageStorageV1)
        let keys = ScopedMessageKeyProvider(namespace: other, persistence: otherRecords, randomBytes: { Data(repeating: 7, count: 32) })
        let store = try LioChatPositionStore(directory: f.directory, namespace: other, keys: keys, validate: {})
        #expect(throws: (any Error).self) { _ = try store.load() }
        #expect(throws: (any Error).self) { try store.save(Data("replacement".utf8)) }
    }
    @Test func linkedPositionFilesAreRejectedWithoutTouchingTheirTarget() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        let store = try f.store()
        try store.save(Data("synthetic protected draft".utf8))
        let path = f.directory.appendingPathComponent(LioChatPositionStore.filename)
        let alias = f.directory.appendingPathComponent("synthetic-other-link")
        let encrypted = try Data(contentsOf: path)
        try FileManager.default.linkItem(at: path, to: alias)
        #expect(throws: RecoveryError.unsafeDirectory) { _ = try store.load() }
        #expect(throws: RecoveryError.unsafeDirectory) { try store.save(Data("replacement".utf8)) }
        #expect(throws: RecoveryError.unsafeDirectory) { try store.clearRetiredPosition() }
        #expect(try Data(contentsOf: alias) == encrypted)
    }
    @Test func aSymlinkCannotRedirectThePositionWriter() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        let target = f.directory.appendingPathComponent("synthetic-target")
        let original = Data("synthetic original target".utf8)
        try original.write(to: target)
        let path = f.directory.appendingPathComponent(LioChatPositionStore.filename)
        try FileManager.default.createSymbolicLink(at: path, withDestinationURL: target)
        let store = try f.store()
        #expect(throws: RecoveryError.unsafeDirectory) { _ = try store.load() }
        #expect(throws: RecoveryError.unsafeDirectory) { try store.save(Data("replacement".utf8)) }
        #expect(throws: RecoveryError.unsafeDirectory) { try store.clearRetiredPosition() }
        #expect(try Data(contentsOf: target) == original)
    }
    @Test func explicitRetiredCleanupOnlyRemovesItsOwnPositionFile() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        let store = try f.store()
        try store.save(Data("synthetic draft".utf8))
        let journal = f.directory.appendingPathComponent("synthetic-original-journal")
        let original = Data("Original unresolved action bytes must stay unchanged".utf8)
        try original.write(to: journal)
        f.active = false
        try store.clearRetiredPosition()
        #expect(!FileManager.default.fileExists(atPath: f.directory.appendingPathComponent(LioChatPositionStore.filename).path))
        #expect(try Data(contentsOf: journal) == original)
    }
    @Test func retiredOwnerCannotReadOrOverwriteTheDraft() throws {
        let f = try PositionFixture(); defer { f.cleanup() }
        let store = try f.store()
        try store.save(Data("synthetic preserved draft".utf8))
        f.active = false
        #expect(throws: RecoveryError.inactive) { _ = try store.load() }
        #expect(throws: RecoveryError.inactive) { try store.save(Data("replacement".utf8)) }
        f.active = true
        #expect(try store.load() == Data("synthetic preserved draft".utf8))
    }
}
