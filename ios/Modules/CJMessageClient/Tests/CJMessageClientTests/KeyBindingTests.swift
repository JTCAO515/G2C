import Foundation
import CryptoKit
import Testing
@testable import CJMessageClient
import CJMessageKeyBridge
@testable import CJMessageKeys

@MainActor private final class BoundKeys: CJMessageClient.MessageEncryptionKeyProvider {
    var id = UUID()
    let secret = SymmetricKey(size: .bits256)
    var expected: [UUID?] = []
    func existing(for scope: StorageScope, expectedID: UUID?) throws -> MessageStorageKey? {
        expected.append(expectedID)
        return MessageStorageKey(id: id, key: secret)
    }
}
@MainActor private final class OfficialFixture: CJMessageKeys.MessageEncryptionKeyProvider {
    let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localMessageStorageV1)
    let instance = UUID(); let generation = UUID(); var current: MessageKeyOperation?
    var fail = false; var missing = false; var active = true; var createCalls = 0
    let keyID = UUID()
    func begin(_ action: MessageKeyAction) throws -> MessageKeyOperation {
        guard active else { throw MessageKeyFailure.inactiveNamespace }
        let op = MessageKeyOperation(instance: instance, generation: generation, action: action); current = op; return op
    }
    func isCurrent(_ operation: MessageKeyOperation) -> Bool { active && operation == current }
    func existing(expectedID: UUID?, for operation: MessageKeyOperation) throws -> MessageEncryptionKey? {
        if fail { throw MessageKeyFailure.storageUnavailable }
        if missing { return nil }
        return try MessageEncryptionKey(id: keyID, namespace: namespace, bytes: Data(repeating: 7, count: 32))
    }
    func create(storageState: EncryptedStorageState, for operation: MessageKeyOperation) throws -> MessageEncryptionKey { createCalls += 1; throw MessageKeyFailure.creationUnconfirmed }
    func reconcileCreation(for operation: MessageKeyOperation) throws -> MessageEncryptionKey { throw MessageKeyFailure.creationUnconfirmed }
    func clear(expectedID: UUID, storageState: EncryptedStorageState, for operation: MessageKeyOperation) throws { throw MessageKeyFailure.clearUnconfirmed }
    func reconcileClear(for operation: MessageKeyOperation) throws -> Bool { throw MessageKeyFailure.clearUnconfirmed }
    func invalidate() { active = false }
}

@Suite @MainActor struct KeyBindingTests {
    private func directory() -> URL { FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cj009-key-v2-"+UUID().uuidString) }
    @Test func keyIDReadbackAndAuthenticatedHeader() throws {
        let keys = BoundKeys(); let dir = directory(); let scope = try StorageScope(environment:"test",account:"a")
        let storage = try EncryptedFileStorage(directory:dir, keys:keys)
        try storage.save(Snapshot(),scope:scope)
        _ = try storage.load(scope:scope)
        #expect(keys.expected.last! == keys.id)
        let file = try #require(FileManager.default.contentsOfDirectory(at:dir,includingPropertiesForKeys:nil).first)
        var bytes = try Data(contentsOf:file)
        let original = bytes
        keys.id = UUID() // Same AES bytes, different purported ID: AAD must reject substitution.
        bytes.replaceSubrange(8..<44, with:Data(keys.id.uuidString.utf8)); try bytes.write(to:file)
        #expect(throws:(any Error).self) { try storage.load(scope:scope) }
        #expect(throws:(any Error).self) { try storage.save(Snapshot(),scope:scope) }
        #expect(try Data(contentsOf:file) == bytes)
        #expect(bytes != original)
    }
    @Test func legacyCiphertextNotOverwrittenOrGuessed() throws {
        let keys = BoundKeys(); let dir = directory(); let scope = try StorageScope(environment:"test",account:"a")
        let storage = try EncryptedFileStorage(directory:dir, keys:keys)
        try storage.save(Snapshot(),scope:scope)
        let file = try #require(FileManager.default.contentsOfDirectory(at:dir,includingPropertiesForKeys:nil).first)
        let legacy = try #require(AES.GCM.seal(Data("old synthetic snapshot".utf8),using:keys.secret,authenticating:scope.binding).combined)
        try legacy.write(to:file)
        #expect(throws:RecoveryError.self) { try storage.load(scope:scope) }
        #expect(throws:RecoveryError.self) { try storage.save(Snapshot(),scope:scope) }
        #expect(try Data(contentsOf:file) == legacy)
    }
    @Test func officialExistingAdapterBindsScopeAndNeverCreates() throws {
        let provider = OfficialFixture(); let scope = try StorageScope(environment:"host-env",account:"host-account")
        let adapter = try ExistingMessageKeyAdapter(provider:provider,scope:scope,namespace:provider.namespace)
        let key = try #require(try adapter.existing(for:scope,expectedID:provider.keyID))
        #expect(key.id == provider.keyID)
        #expect(throws:MessageKeyFailure.self) { try adapter.existing(for:scope,expectedID:UUID()) }
        #expect(throws:MessageKeyFailure.self) { try adapter.existing(for:StorageScope(environment:"host-env",account:"other"),expectedID:nil) }
        provider.missing = true
        #expect(try adapter.existing(for:scope,expectedID:nil) == nil)
        provider.fail = true
        #expect(throws:MessageKeyFailure.self) { try adapter.existing(for:scope,expectedID:nil) }
        #expect(provider.createCalls == 0)
        adapter.invalidate()
        #expect(throws:MessageKeyFailure.self) { try adapter.existing(for:scope,expectedID:nil) }
    }
    @Test func hostMappingMismatchRejected() throws {
        let provider = OfficialFixture(); let scope = try StorageScope(environment:"host-env",account:"host-account")
        let other = MessageKeyNamespace(environment:provider.namespace.environment,account:UUID(),purpose:.localMessageStorageV1)
        #expect(throws:MessageKeyFailure.self) { try ExistingMessageKeyAdapter(provider:provider,scope:scope,namespace:other) }
    }
}
