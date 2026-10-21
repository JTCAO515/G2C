import Foundation
import CryptoKit
import Testing
@testable import CJMessageClient

@MainActor private final class TestKeys: MessageEncryptionKeyProvider {
    var available = true
    var secret = SymmetricKey(size: .bits256)
    func key(for scope: StorageScope) throws -> SymmetricKey? { available ? secret : nil }
}

@MainActor private final class AmbiguousStorage: SecureMessageStorage {
    let base: EncryptedFileStorage
    var failAfterSave = false
    init(_ base: EncryptedFileStorage) { self.base = base }
    func load(scope: StorageScope) throws -> Snapshot? { try base.load(scope: scope) }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {
        try base.save(snapshot, scope: scope)
        if failAfterSave { throw RecoveryError.persistenceUnknown }
    }
}

@MainActor private struct Fixture {
    let directory: URL
    let keys: TestKeys
    let storage: EncryptedFileStorage
    let scope: StorageScope
    init() throws {
        directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
            .appendingPathComponent("cj009-synthetic-" + UUID().uuidString)
        keys = TestKeys()
        storage = try EncryptedFileStorage(directory: directory, keys: keys)
        scope = try StorageScope(environment: "fixture-local", account: "fixture-a")
    }
    var raw: Data { Data(" {\"message_id\":\"m1\",\"text\":\"合成 private text\"} \n".utf8) }
}

@Suite @MainActor struct RecoveryTests {
    @Test func encryptedReopenRetainsOriginalBytesDraftAndUnknown() throws {
        let f = try Fixture(); let first = MessageRecovery(storage: f.storage)
        let lease = try first.activate(f.scope)
        try first.saveDraft(Data("unsent draft 中文".utf8), conversationID: "chat", lease: lease)
        try first.stage(messageID: "m1", originalUTF8: f.raw, lease: lease)
        let sent = try first.beginSubmission(messageID: "m1", lease: lease)
        #expect(sent.originalUTF8 == f.raw)
        let reopened = MessageRecovery(storage: try EncryptedFileStorage(directory: f.directory, keys: f.keys))
        let newLease = try reopened.activate(f.scope)
        #expect(throws: RecoveryError.self) { try reopened.observeUnknown(sent.operation) }
        #expect(try reopened.action(messageID: "m1", lease: newLease)?.originalUTF8 == f.raw)
        #expect(try reopened.action(messageID: "m1", lease: newLease)?.phase == .queryRequired)
        #expect(try reopened.draft(conversationID: "chat", lease: newLease) == Data("unsent draft 中文".utf8))
        #expect(throws: RecoveryError.self) { try reopened.beginSubmission(messageID: "m1", lease: newLease) }
        let file = try #require(FileManager.default.contentsOfDirectory(at: f.directory, includingPropertiesForKeys: nil).first)
        let encrypted = try Data(contentsOf: file)
        #expect(encrypted.range(of: Data("private text".utf8)) == nil)
        #expect(encrypted.range(of: Data("unsent draft".utf8)) == nil)
    }

    @Test func nullNeverAuthorizesPostAndOriginalIDCannotChange() throws {
        let f = try Fixture(); let state = MessageRecovery(storage: f.storage); let lease = try state.activate(f.scope)
        try state.stage(messageID: "m1", originalUTF8: f.raw, lease: lease)
        let send = try state.beginSubmission(messageID: "m1", lease: lease)
        try state.observeUnknown(send.operation)
        let query = try state.beginQuery(messageID: "m1", lease: lease)
        try state.observeNotObserved(query)
        #expect(try state.action(messageID: "m1", lease: lease)?.phase == .notObserved)
        #expect(throws: RecoveryError.self) { try state.beginSubmission(messageID: "m1", lease: lease) }
        #expect(throws: RecoveryError.self) { try state.stage(messageID: "m1", originalUTF8: f.raw + Data(" ".utf8), lease: lease) }
        #expect(try state.beginQuery(messageID: "m1", lease: lease).messageID == "m1")
    }

    @Test func accountEnvironmentAndSameAccountGenerationRejectOldResults() throws {
        let f = try Fixture(); let state = MessageRecovery(storage: f.storage); let a = try state.activate(f.scope)
        try state.stage(messageID: "m1", originalUTF8: f.raw, lease: a)
        let old = try state.beginSubmission(messageID: "m1", lease: a).operation
        for scope in [try StorageScope(environment: "fixture-local", account: "fixture-b"),
                      try StorageScope(environment: "fixture-other", account: "fixture-a")] {
            let next = try state.activate(scope)
            #expect(try state.action(messageID: "m1", lease: next) == nil)
            #expect(throws: RecoveryError.self) { try state.observeUnknown(old) }
            #expect(throws: RecoveryError.self) { try state.saveDraft(Data(), conversationID: "chat", lease: a) }
        }
        let again = try state.activate(f.scope)
        #expect(again != a)
        #expect(throws: RecoveryError.self) { try state.observeUnknown(old) }
        #expect(try state.action(messageID: "m1", lease: again)?.phase == .queryRequired)
    }

    @Test func latestQueryAndReceiptBindingOnly() throws {
        let f = try Fixture(); let state = MessageRecovery(storage: f.storage); let lease = try state.activate(f.scope)
        try state.stage(messageID: "m1", originalUTF8: f.raw, lease: lease)
        _ = try state.beginSubmission(messageID: "m1", lease: lease)
        let old = try state.beginQuery(messageID: "m1", lease: lease)
        let current = try state.beginQuery(messageID: "m1", lease: lease)
        #expect(throws: RecoveryError.self) { try state.observeNotObserved(old) }
        #expect(throws: RecoveryError.self) { try state.observeReceipt(current, messageID: "other", inputSHA256: "bad", receipt: Data([1])) }
        let record = try #require(try state.action(messageID: "m1", lease: lease))
        try state.observeReceipt(current, messageID: "m1", inputSHA256: record.inputSHA256, receipt: Data("fixture-receipt".utf8))
        #expect(try state.action(messageID: "m1", lease: lease)?.phase == .accepted)
        #expect(throws: RecoveryError.self) { try state.observeUnknown(current) }
    }

    @Test func missingKeyWrongKeyCorruptionNeverMeansEmpty() throws {
        let f = try Fixture(); f.keys.available = false
        let state = MessageRecovery(storage: f.storage)
        #expect(throws: RecoveryError.self) { try state.activate(f.scope) }
        f.keys.available = true
        let lease = try state.activate(f.scope)
        try state.stage(messageID: "m1", originalUTF8: f.raw, lease: lease)
        state.invalidate(); let original = f.keys.secret; f.keys.secret = SymmetricKey(size: .bits256)
        #expect(throws: (any Error).self) { try state.activate(f.scope) }
        f.keys.secret = original
        let file = try #require(FileManager.default.contentsOfDirectory(at: f.directory, includingPropertiesForKeys: nil).first)
        var bytes = try Data(contentsOf: file); bytes[bytes.count - 1] ^= 1; try bytes.write(to: file)
        #expect(throws: (any Error).self) { try state.activate(f.scope) }
    }

    @Test func ambiguousSaveInvalidatesUntilReadback() throws {
        let f = try Fixture(); let ambiguous = AmbiguousStorage(f.storage)
        let state = MessageRecovery(storage: ambiguous); let lease = try state.activate(f.scope)
        try state.stage(messageID: "m1", originalUTF8: f.raw, lease: lease)
        ambiguous.failAfterSave = true
        #expect(throws: RecoveryError.self) { try state.beginSubmission(messageID: "m1", lease: lease) }
        #expect(throws: RecoveryError.self) { try state.action(messageID: "m1", lease: lease) }
        ambiguous.failAfterSave = false
        let restored = try state.activate(f.scope)
        #expect(try state.action(messageID: "m1", lease: restored)?.phase == .queryRequired)
        #expect(throws: RecoveryError.self) { try state.beginSubmission(messageID: "m1", lease: restored) }
    }

    @Test func unicodeOpaqueIDsDoNotAliasAndLanguageDoesNotRewrite() throws {
        let f = try Fixture(); let state = MessageRecovery(storage: f.storage); let lease = try state.activate(f.scope)
        try state.stage(messageID: "é", originalUTF8: Data("first".utf8), lease: lease)
        try state.stage(messageID: "e\u{301}", originalUTF8: Data("second".utf8), lease: lease)
        #expect(try state.action(messageID: "é", lease: lease)?.originalUTF8 == Data("first".utf8))
        #expect(try state.action(messageID: "e\u{301}", lease: lease)?.originalUTF8 == Data("second".utf8))
        try state.saveDraft(Data("new language draft".utf8), conversationID: "chat", lease: lease)
        #expect(try state.action(messageID: "é", lease: lease)?.originalUTF8 == Data("first".utf8))
    }

    @Test func unknownBodyCannotBeRekeyedAndMalformedUTF8Rejected() throws {
        let f = try Fixture(); let state = MessageRecovery(storage: f.storage); let lease = try state.activate(f.scope)
        try state.stage(messageID: "m1", originalUTF8: f.raw, lease: lease)
        _ = try state.beginSubmission(messageID: "m1", lease: lease)
        #expect(throws: RecoveryError.self) { try state.stage(messageID: "new-id", originalUTF8: f.raw, lease: lease) }
        #expect(throws: RecoveryError.self) { try state.stage(messageID: "bad", originalUTF8: Data([0xff]), lease: lease) }
        #expect(try state.action(messageID: "new-id", lease: lease) == nil)
    }

    @Test func ciphertextCannotMoveBetweenScopesEvenWithSameKey() throws {
        let f = try Fixture(); let state = MessageRecovery(storage: f.storage); let lease = try state.activate(f.scope)
        try state.stage(messageID: "m1", originalUTF8: f.raw, lease: lease)
        let source = try #require(FileManager.default.contentsOfDirectory(at: f.directory, includingPropertiesForKeys: nil).first)
        let other = try StorageScope(environment: "fixture-local", account: "fixture-b")
        let next = try state.activate(other)
        try state.saveDraft(Data("b".utf8), conversationID: "chat", lease: next)
        let target = try #require(FileManager.default.contentsOfDirectory(at: f.directory, includingPropertiesForKeys: nil).first(where: { $0 != source }))
        try Data(contentsOf: source).write(to: target)
        #expect(throws: (any Error).self) { try state.activate(other) }
    }
}
