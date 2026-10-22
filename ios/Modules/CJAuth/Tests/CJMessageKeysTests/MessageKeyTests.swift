import Foundation
import CryptoKit
import Security
import Testing
@testable import CJMessageKeys

@MainActor private final class Storage: MessageKeyPersistence {
    var value: MessageKeyRecord?
    var readError: MessageKeyFailure?
    var failAdd = false
    var commitBeforeAddError = false
    var failRemove = false
    var commitBeforeRemoveError = false
    var adds = 0
    var deletes = 0
    func read() throws -> MessageKeyRecord? { if let readError { throw readError }; return value }
    func add(_ record: MessageKeyRecord) throws {
        adds += 1
        if value != nil { throw MessageKeyFailure.keychain(errSecDuplicateItem) }
        if !failAdd || commitBeforeAddError { value = record }
        if failAdd { throw MessageKeyFailure.storageUnavailable }
    }
    func remove(expectedID: UUID) throws {
        deletes += 1
        guard value?.id == expectedID else { throw MessageKeyFailure.keyMismatch }
        if !failRemove || commitBeforeRemoveError { value = nil }
        if failRemove { throw MessageKeyFailure.storageUnavailable }
    }
}

@Suite @MainActor struct MessageKeyTests {
    func namespace() -> MessageKeyNamespace { .init(environment: UUID(), account: UUID(), purpose: .localMessageStorageV1) }

    @Test func platformRandomKeyRoundTripAndRedaction() throws {
        let storage = Storage(); let provider = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage)
        let key = try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create))
        let plaintext = Data("synthetic-message-only".utf8)
        let sealed = try key.withSymmetricKey { try AES.GCM.seal(plaintext, using: $0) }
        let result = try provider.existing(expectedID: key.id, for: provider.begin(.lookup))
        let loaded = try #require(result)
        #expect(try loaded.withSymmetricKey { try AES.GCM.open(sealed, using: $0) } == plaintext)
        #expect(loaded.namespace == provider.namespace && !provider.canUseRestrictedBusiness)
        #expect(String(reflecting: loaded) == "<redacted message encryption key>")
        #expect(Mirror(reflecting: loaded).children.isEmpty)
        #expect(storage.value?.bytes.count == 32)
    }
    @Test func missingOrUnknownDoesNotAutomaticallyGenerate() throws {
        let storage = Storage(); var randomCalls = 0
        let p = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage, randomBytes: {
            randomCalls += 1; return Data(repeating: 1, count: 32)
        })
        #expect(try p.existing(expectedID: nil, for: p.begin(.lookup)) == nil)
        for state in [EncryptedStorageState.unknown, .containsCiphertext] {
            #expect(throws: MessageKeyFailure.storageNotConfirmedEmpty) { try p.create(storageState: state, for: p.begin(.create)) }
        }
        storage.readError = .keychain(errSecInteractionNotAllowed)
        #expect(throws: MessageKeyFailure.keychain(errSecInteractionNotAllowed)) { try p.create(storageState: .confirmedEmpty, for: p.begin(.create)) }
        #expect(randomCalls == 0 && storage.adds == 0)
    }
    @Test func randomFailureOrWrongLengthNeverPersists() throws {
        let storage = Storage()
        let failing = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage, randomBytes: { throw MessageKeyFailure.random(-1) })
        #expect(throws: MessageKeyFailure.random(-1)) { try failing.create(storageState: .confirmedEmpty, for: failing.begin(.create)) }
        let short = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage, randomBytes: { Data(repeating: 0, count: 31) })
        #expect(throws: MessageKeyFailure.malformedRecord) { try short.create(storageState: .confirmedEmpty, for: short.begin(.create)) }
        #expect(storage.adds == 0)
    }
    @Test func unknownCreateReconcilesOriginalWithoutGeneratingAgain() throws {
        let storage = Storage(); storage.failAdd = true; storage.commitBeforeAddError = true
        var randomCalls = 0
        let p = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage, randomBytes: {
            randomCalls += 1; return Data(repeating: 5, count: 32)
        })
        #expect(throws: MessageKeyFailure.storageUnavailable) { try p.create(storageState: .confirmedEmpty, for: p.begin(.create)) }
        let original = try #require(storage.value)
        #expect(throws: MessageKeyFailure.creationUnconfirmed) { try p.create(storageState: .confirmedEmpty, for: p.begin(.create)) }
        #expect(throws: MessageKeyFailure.creationUnconfirmed) { try p.existing(expectedID: nil, for: p.begin(.lookup)) }
        let recovered = try p.reconcileCreation(for: p.begin(.reconcileCreation))
        #expect(recovered.id == original.id && randomCalls == 1 && storage.adds == 1)
    }
    @Test func unknownCreateMissingOrDifferentBytesCannotBeSettled() throws {
        let storage = Storage(); storage.failAdd = true
        let p = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage)
        #expect(throws: MessageKeyFailure.storageUnavailable) { try p.create(storageState: .confirmedEmpty, for: p.begin(.create)) }
        #expect(throws: MessageKeyFailure.creationUnconfirmed) { try p.reconcileCreation(for: p.begin(.reconcileCreation)) }
        storage.value = MessageKeyRecord(id: UUID(), bytes: Data(repeating: 9, count: 32))
        #expect(throws: MessageKeyFailure.keyMismatch) { try p.reconcileCreation(for: p.begin(.reconcileCreation)) }
        #expect(storage.adds == 1)
    }
    @Test func existingKeyCannotRotateAndCiphertextPreventsClear() throws {
        let storage = Storage(); let p = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage)
        let original = try p.create(storageState: .confirmedEmpty, for: p.begin(.create))
        #expect(throws: MessageKeyFailure.alreadyExists) { try p.create(storageState: .confirmedEmpty, for: p.begin(.create)) }
        #expect(throws: MessageKeyFailure.storageNotConfirmedEmpty) { try p.clear(expectedID: original.id, storageState: .containsCiphertext, for: p.begin(.clear)) }
        #expect(storage.value?.id == original.id && storage.adds == 1 && storage.deletes == 0)
    }
    @Test func staleCrossInstanceAndInvalidatedOperationsCannotClear() throws {
        let storage = Storage(); let ns = namespace()
        let p = ScopedMessageKeyProvider(namespace: ns, persistence: storage)
        let other = ScopedMessageKeyProvider(namespace: ns, persistence: storage)
        let key = try p.create(storageState: .confirmedEmpty, for: p.begin(.create))
        let old = try p.begin(.clear)
        #expect(throws: MessageKeyFailure.staleOperation) { try other.clear(expectedID: key.id, storageState: .confirmedEmpty, for: old) }
        _ = try p.begin(.lookup)
        #expect(throws: MessageKeyFailure.staleOperation) { try p.clear(expectedID: key.id, storageState: .confirmedEmpty, for: old) }
        let next = try p.begin(.clear); p.invalidate()
        #expect(throws: MessageKeyFailure.staleOperation) { try p.clear(expectedID: key.id, storageState: .confirmedEmpty, for: next) }
        #expect(throws: MessageKeyFailure.inactiveNamespace) { try p.begin(.lookup) }
        #expect(storage.deletes == 0)
    }
    @Test func expectedOldKeyIDNeverDeletesReplacement() throws {
        let storage = Storage(); let p = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage)
        let old = try p.create(storageState: .confirmedEmpty, for: p.begin(.create))
        let replacement = MessageKeyRecord(id: UUID(), bytes: Data(repeating: 3, count: 32))
        storage.value = replacement
        #expect(throws: MessageKeyFailure.keyMismatch) { try p.clear(expectedID: old.id, storageState: .confirmedEmpty, for: p.begin(.clear)) }
        #expect(storage.value == replacement && storage.deletes == 0)
    }
    @Test func unknownClearIsReadOnlyUntilOriginalOutcomeObserved() throws {
        let storage = Storage(); let p = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage)
        let key = try p.create(storageState: .confirmedEmpty, for: p.begin(.create))
        storage.failRemove = true
        #expect(throws: MessageKeyFailure.storageUnavailable) { try p.clear(expectedID: key.id, storageState: .confirmedEmpty, for: p.begin(.clear)) }
        #expect(try p.reconcileClear(for: p.begin(.reconcileClear)) == false)
        #expect(throws: MessageKeyFailure.clearUnconfirmed) { try p.create(storageState: .confirmedEmpty, for: p.begin(.create)) }
        storage.value = nil // synthetic authoritative observation of completed deletion
        #expect(try p.reconcileClear(for: p.begin(.reconcileClear)))
        #expect(storage.deletes == 1 && storage.adds == 1)
    }
    @Test func committedClearWithLostAcknowledgementDoesNotCreateOrDeleteAgain() throws {
        let storage = Storage(); let p = ScopedMessageKeyProvider(namespace: namespace(), persistence: storage)
        let key = try p.create(storageState: .confirmedEmpty, for: p.begin(.create))
        storage.failRemove = true; storage.commitBeforeRemoveError = true
        #expect(throws: MessageKeyFailure.storageUnavailable) { try p.clear(expectedID: key.id, storageState: .confirmedEmpty, for: p.begin(.clear)) }
        #expect(storage.value == nil)
        #expect(throws: MessageKeyFailure.clearUnconfirmed) { try p.create(storageState: .confirmedEmpty, for: p.begin(.create)) }
        #expect(try p.reconcileClear(for: p.begin(.reconcileClear)))
        #expect(storage.deletes == 1 && storage.adds == 1)
    }
    @Test func namespacesSeparateAccountsEnvironmentsAndSessionStorage() {
        let a = namespace()
        let b = MessageKeyNamespace(environment: a.environment, account: UUID(), purpose: a.purpose)
        let c = MessageKeyNamespace(environment: UUID(), account: a.account, purpose: a.purpose)
        #expect(a.slot != b.slot && a.service == b.service)
        #expect(a.service != c.service)
        #expect(!a.service.hasPrefix("G2C.CJAuth.session."))
    }
    @Test func nativeAdapterUsesExactScopeAndExpectedIDPredicateWithNoRetry() throws {
        let ns = namespace(); let group = "PROPOSAL.local.g2c.cj007"
        var record: [String: Any]?
        var lastQuery: [String: Any] = [:]
        var deletes = 0
        let ops = MessageKeychainOperations(read: { query in
            lastQuery = query; return record.map { (errSecSuccess, $0) } ?? (errSecItemNotFound, nil)
        }, add: { query in
            lastQuery = query
            guard record == nil else { return errSecDuplicateItem }
            record = query; return errSecSuccess
        }, delete: { query in
            lastQuery = query; deletes += 1
            guard query[kSecAttrGeneric as String] as? Data == record?[kSecAttrGeneric as String] as? Data else { return errSecItemNotFound }
            record = nil; return errSecSuccess
        })
        let store = try KeychainMessageKeys(namespace: ns, applicationIdentifier: group, protection: .whenUnlockedThisDeviceOnly, operations: ops)
        let key = MessageKeyRecord(id: UUID(), bytes: Data(repeating: 7, count: 32))
        try store.add(key)
        #expect(lastQuery[kSecAttrService as String] as? String == ns.service)
        #expect(lastQuery[kSecAttrAccount as String] as? String == ns.slot)
        #expect(lastQuery[kSecAttrAccessGroup as String] as? String == group)
        #expect(lastQuery[kSecAttrSynchronizable as String] as? Bool == false)
        #expect(try store.read() == key)
        #expect(throws: MessageKeyFailure.keychain(errSecDuplicateItem)) {
            try store.add(MessageKeyRecord(id: UUID(), bytes: Data(repeating: 8, count: 32)))
        }
        #expect(try store.read() == key)
        #expect(throws: MessageKeyFailure.keychain(errSecItemNotFound)) { try store.remove(expectedID: UUID()) }
        #expect(record != nil && deletes == 1)
        try store.remove(expectedID: key.id)
        #expect(record == nil && deletes == 2)
    }
}

@MainActor private final class ScopedKeychainFixture {
    private var records: [[String]: [String: Any]] = [:]
    private func scope(_ query: [String: Any]) -> [String]? {
        guard let service = query[kSecAttrService as String] as? String,
              let account = query[kSecAttrAccount as String] as? String,
              let group = query[kSecAttrAccessGroup as String] as? String else { return nil }
        return [service, account, group]
    }
    var operations: MessageKeychainOperations {
        MessageKeychainOperations(read: { query in
            guard let scope = self.scope(query) else { return (errSecParam, nil) }
            return self.records[scope].map { (errSecSuccess, $0) } ?? (errSecItemNotFound, nil)
        }, add: { query in
            guard let scope = self.scope(query) else { return errSecParam }
            guard self.records[scope] == nil else { return errSecDuplicateItem }
            self.records[scope] = query
            return errSecSuccess
        }, delete: { query in
            guard let scope = self.scope(query),
                  self.records[scope]?[kSecAttrGeneric as String] as? Data == query[kSecAttrGeneric as String] as? Data else { return errSecItemNotFound }
            self.records.removeValue(forKey: scope)
            return errSecSuccess
        })
    }
}

extension MessageKeyTests {
    @Test func memoryPurposeHasDedicatedSlotWithoutChangingMessageBytes() throws {
        let environment = try #require(UUID(uuidString: "11111111-1111-4111-8111-111111111111"))
        let account = try #require(UUID(uuidString: "22222222-2222-4222-8222-222222222222"))
        let message = MessageKeyNamespace(environment: environment, account: account, purpose: .localMessageStorageV1)
        let memory = MessageKeyNamespace(environment: environment, account: account, purpose: .localMemoryPendingV1)
        #expect(message.service == "G2C.CJAuth.message-key.11111111-1111-4111-8111-111111111111")
        #expect(message.slot == "22222222-2222-4222-8222-222222222222.local-message-storage-v1")
        #expect(memory.service == message.service)
        #expect(memory.slot == "22222222-2222-4222-8222-222222222222.local-memory-pending-v1")
        #expect(memory.slot != message.slot)
    }
    @Test func memoryPurposeAccountEnvironmentAndExpectedIDCannotCrossKeys() throws {
        let environment = UUID(), account = UUID(), fixture = ScopedKeychainFixture()
        let namespaces = [
            MessageKeyNamespace(environment: environment, account: account, purpose: .localMessageStorageV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localMemoryPendingV1),
            MessageKeyNamespace(environment: environment, account: UUID(), purpose: .localMemoryPendingV1),
            MessageKeyNamespace(environment: UUID(), account: account, purpose: .localMemoryPendingV1)]
        let providers = try namespaces.map { namespace in
            ScopedMessageKeyProvider(namespace: namespace, persistence: try KeychainMessageKeys(namespace: namespace,
                applicationIdentifier: "SYNTHETIC.local.memory-test", protection: .whenUnlockedThisDeviceOnly, operations: fixture.operations))
        }
        let keys = try providers.map { try $0.create(storageState: .confirmedEmpty, for: $0.begin(.create)) }
        #expect(Set(keys.map(\.id)).count == 4)
        let memoryKey = keys[1], memoryProvider = providers[1]
        let sealed = try memoryKey.withSymmetricKey { try AES.GCM.seal(Data("synthetic-memory-pending".utf8), using: $0) }
        for index in [0, 2, 3] {
            #expect(throws: (any Error).self) { try keys[index].withSymmetricKey { try AES.GCM.open(sealed, using: $0) } }
            #expect(throws: MessageKeyFailure.keyMismatch) {
                try providers[index].existing(expectedID: memoryKey.id, for: providers[index].begin(.lookup))
            }
            #expect(throws: MessageKeyFailure.keyMismatch) {
                try providers[index].clear(expectedID: memoryKey.id, storageState: .confirmedEmpty, for: providers[index].begin(.clear))
            }
            let foreignOperation = try providers[index].begin(.lookup)
            #expect(throws: MessageKeyFailure.staleOperation) { try memoryProvider.existing(expectedID: memoryKey.id, for: foreignOperation) }
        }
        let recovered = try memoryProvider.existing(expectedID: memoryKey.id, for: memoryProvider.begin(.lookup))
        let ownKey = try #require(recovered)
        #expect(ownKey.namespace == namespaces[1])
        #expect(try ownKey.withSymmetricKey { try AES.GCM.open(sealed, using: $0) } == Data("synthetic-memory-pending".utf8))
        try memoryProvider.clear(expectedID: memoryKey.id, storageState: .confirmedEmpty, for: memoryProvider.begin(.clear))
        #expect(try memoryProvider.existing(expectedID: memoryKey.id, for: memoryProvider.begin(.lookup)) == nil)
        #expect(try providers[0].existing(expectedID: keys[0].id, for: providers[0].begin(.lookup))?.id == keys[0].id)
    }
    @Test func memoryPendingUnknownCreationReusesOriginalReconciliation() throws {
        let storage = Storage(); storage.failAdd = true; storage.commitBeforeAddError = true
        let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localMemoryPendingV1)
        let provider = ScopedMessageKeyProvider(namespace: namespace, persistence: storage)
        #expect(throws: MessageKeyFailure.storageUnavailable) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        let original = try #require(storage.value)
        #expect(throws: MessageKeyFailure.creationUnconfirmed) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        let recovered = try provider.reconcileCreation(for: provider.begin(.reconcileCreation))
        #expect(recovered.id == original.id && recovered.namespace == namespace && storage.adds == 1)
    }
}

extension MessageKeyTests {
    @Test func tripPurposeKeepsMessageAndMemoryNamespaceBytesUnchanged() throws {
        let environment = try #require(UUID(uuidString: "11111111-1111-4111-8111-111111111111"))
        let account = try #require(UUID(uuidString: "22222222-2222-4222-8222-222222222222"))
        let purposes: [MessageKeyPurpose] = [.localMessageStorageV1, .localMemoryPendingV1, .localTripPendingV1]
        let expected = ["local-message-storage-v1", "local-memory-pending-v1", "local-trip-pending-v1"]
        for (purpose, suffix) in zip(purposes, expected) {
            let namespace = MessageKeyNamespace(environment: environment, account: account, purpose: purpose)
            #expect(namespace.service == "G2C.CJAuth.message-key.11111111-1111-4111-8111-111111111111")
            #expect(namespace.slot == "22222222-2222-4222-8222-222222222222." + suffix)
        }
    }
    @Test func tripPurposeAccountEnvironmentAndCleanupRemainIsolated() throws {
        let environment = UUID(), account = UUID(), fixture = ScopedKeychainFixture()
        let namespaces = [
            MessageKeyNamespace(environment: environment, account: account, purpose: .localMessageStorageV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localMemoryPendingV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localTripPendingV1),
            MessageKeyNamespace(environment: environment, account: UUID(), purpose: .localTripPendingV1),
            MessageKeyNamespace(environment: UUID(), account: account, purpose: .localTripPendingV1)]
        let providers = try namespaces.map { namespace in
            ScopedMessageKeyProvider(namespace: namespace, persistence: try KeychainMessageKeys(namespace: namespace,
                applicationIdentifier: "SYNTHETIC.local.trip-test", protection: .whenUnlockedThisDeviceOnly, operations: fixture.operations))
        }
        let keys = try providers.map { try $0.create(storageState: .confirmedEmpty, for: $0.begin(.create)) }
        #expect(Set(keys.map(\.id)).count == 5)
        let original = Data("synthetic-original-trip-action-bytes".utf8)
        let sealed = try keys[2].withSymmetricKey { try AES.GCM.seal(original, using: $0) }
        for index in [0, 1, 3, 4] {
            #expect(throws: (any Error).self) { try keys[index].withSymmetricKey { try AES.GCM.open(sealed, using: $0) } }
            #expect(throws: MessageKeyFailure.keyMismatch) { try providers[index].existing(expectedID: keys[2].id, for: providers[index].begin(.lookup)) }
            #expect(throws: MessageKeyFailure.keyMismatch) { try providers[index].clear(expectedID: keys[2].id, storageState: .confirmedEmpty, for: providers[index].begin(.clear)) }
            let wrongOperation = try providers[index].begin(.lookup)
            #expect(throws: MessageKeyFailure.staleOperation) { try providers[2].existing(expectedID: keys[2].id, for: wrongOperation) }
        }
        // Cleaning another purpose does not remove Trip's original key.
        try providers[1].clear(expectedID: keys[1].id, storageState: .confirmedEmpty, for: providers[1].begin(.clear))
        let restored = try providers[2].existing(expectedID: keys[2].id, for: providers[2].begin(.lookup))
        let tripKey = try #require(restored)
        #expect(tripKey.namespace == namespaces[2])
        #expect(try tripKey.withSymmetricKey { try AES.GCM.open(sealed, using: $0) } == original)
        let newMemoryKey = try providers[1].create(storageState: .confirmedEmpty, for: providers[1].begin(.create))
        try providers[2].clear(expectedID: keys[2].id, storageState: .confirmedEmpty, for: providers[2].begin(.clear))
        #expect(try providers[2].existing(expectedID: keys[2].id, for: providers[2].begin(.lookup)) == nil)
        #expect(try providers[1].existing(expectedID: newMemoryKey.id, for: providers[1].begin(.lookup))?.id == newMemoryKey.id)
        for index in [0, 3, 4] {
            #expect(try providers[index].existing(expectedID: keys[index].id, for: providers[index].begin(.lookup))?.id == keys[index].id)
        }
    }
    @Test func tripPendingUnknownCreationReconcilesOnlyOriginalKey() throws {
        let storage = Storage(); storage.failAdd = true; storage.commitBeforeAddError = true
        let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localTripPendingV1)
        let provider = ScopedMessageKeyProvider(namespace: namespace, persistence: storage)
        #expect(throws: MessageKeyFailure.storageUnavailable) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        let original = try #require(storage.value)
        #expect(throws: MessageKeyFailure.creationUnconfirmed) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        let reconciled = try provider.reconcileCreation(for: provider.begin(.reconcileCreation))
        #expect(reconciled.id == original.id && reconciled.namespace == namespace && storage.adds == 1)
        #expect(!provider.canUseRestrictedBusiness)
    }
}

extension MessageKeyTests {
    @Test func needsPurposePreservesAllExistingNamespaceBytes() throws {
        let environment = try #require(UUID(uuidString: "11111111-1111-4111-8111-111111111111"))
        let account = try #require(UUID(uuidString: "22222222-2222-4222-8222-222222222222"))
        let purposes: [MessageKeyPurpose] = [.localMessageStorageV1, .localMemoryPendingV1, .localTripPendingV1, .localNeedsPendingV1]
        let expected = ["local-message-storage-v1", "local-memory-pending-v1", "local-trip-pending-v1", "local-needs-pending-v1"]
        for (purpose, suffix) in zip(purposes, expected) {
            let namespace = MessageKeyNamespace(environment: environment, account: account, purpose: purpose)
            #expect(namespace.service == "G2C.CJAuth.message-key.11111111-1111-4111-8111-111111111111")
            #expect(namespace.slot == "22222222-2222-4222-8222-222222222222." + suffix)
        }
    }
    @Test func needsPurposeScopeAndCleanupCannotCrossExistingKeys() throws {
        let environment = UUID(), account = UUID(), fixture = ScopedKeychainFixture()
        let namespaces = [
            MessageKeyNamespace(environment: environment, account: account, purpose: .localMessageStorageV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localMemoryPendingV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localTripPendingV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localNeedsPendingV1),
            MessageKeyNamespace(environment: environment, account: UUID(), purpose: .localNeedsPendingV1),
            MessageKeyNamespace(environment: UUID(), account: account, purpose: .localNeedsPendingV1)]
        let providers = try namespaces.map { namespace in
            ScopedMessageKeyProvider(namespace: namespace, persistence: try KeychainMessageKeys(namespace: namespace,
                applicationIdentifier: "SYNTHETIC.local.needs-test", protection: .whenUnlockedThisDeviceOnly, operations: fixture.operations))
        }
        var keys = try providers.map { try $0.create(storageState: .confirmedEmpty, for: $0.begin(.create)) }
        #expect(Set(keys.map(\.id)).count == 6)
        let original = Data("synthetic-original-needs-action-bytes".utf8)
        let sealed = try keys[3].withSymmetricKey { try AES.GCM.seal(original, using: $0) }
        for index in [0, 1, 2, 4, 5] {
            #expect(throws: (any Error).self) { try keys[index].withSymmetricKey { try AES.GCM.open(sealed, using: $0) } }
            #expect(throws: MessageKeyFailure.keyMismatch) { try providers[index].existing(expectedID: keys[3].id, for: providers[index].begin(.lookup)) }
            #expect(throws: MessageKeyFailure.keyMismatch) { try providers[index].clear(expectedID: keys[3].id, storageState: .confirmedEmpty, for: providers[index].begin(.clear)) }
            let foreign = try providers[index].begin(.lookup)
            #expect(throws: MessageKeyFailure.staleOperation) { try providers[3].existing(expectedID: keys[3].id, for: foreign) }
        }
        for index in [0, 1, 2] {
            try providers[index].clear(expectedID: keys[index].id, storageState: .confirmedEmpty, for: providers[index].begin(.clear))
            let result = try providers[3].existing(expectedID: keys[3].id, for: providers[3].begin(.lookup))
            let restored = try #require(result)
            #expect(restored.namespace == namespaces[3])
            #expect(try restored.withSymmetricKey { try AES.GCM.open(sealed, using: $0) } == original)
            keys[index] = try providers[index].create(storageState: .confirmedEmpty, for: providers[index].begin(.create))
        }
        try providers[3].clear(expectedID: keys[3].id, storageState: .confirmedEmpty, for: providers[3].begin(.clear))
        #expect(try providers[3].existing(expectedID: keys[3].id, for: providers[3].begin(.lookup)) == nil)
        for index in [0, 1, 2, 4, 5] {
            #expect(try providers[index].existing(expectedID: keys[index].id, for: providers[index].begin(.lookup))?.id == keys[index].id)
        }
    }
    @Test func needsPendingUnknownCreateAndClearUseOriginalReadback() throws {
        let storage = Storage(); storage.failAdd = true; storage.commitBeforeAddError = true
        let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localNeedsPendingV1)
        let provider = ScopedMessageKeyProvider(namespace: namespace, persistence: storage)
        #expect(throws: MessageKeyFailure.storageUnavailable) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        let original = try #require(storage.value)
        #expect(throws: MessageKeyFailure.creationUnconfirmed) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        let reconciled = try provider.reconcileCreation(for: provider.begin(.reconcileCreation))
        #expect(reconciled.id == original.id && reconciled.namespace == namespace && storage.adds == 1)
        storage.failRemove = true; storage.commitBeforeRemoveError = true
        #expect(throws: MessageKeyFailure.storageUnavailable) { try provider.clear(expectedID: original.id, storageState: .confirmedEmpty, for: provider.begin(.clear)) }
        #expect(throws: MessageKeyFailure.clearUnconfirmed) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        #expect(try provider.reconcileClear(for: provider.begin(.reconcileClear)))
        #expect(storage.adds == 1 && storage.deletes == 1 && !provider.canUseRestrictedBusiness)
    }
}

extension MessageKeyTests {
    @Test func feedbackPurposePreservesAllExistingNamespaceBytes() throws {
        let environment = try #require(UUID(uuidString: "11111111-1111-4111-8111-111111111111"))
        let account = try #require(UUID(uuidString: "22222222-2222-4222-8222-222222222222"))
        let purposes: [MessageKeyPurpose] = [.localMessageStorageV1, .localMemoryPendingV1, .localTripPendingV1, .localNeedsPendingV1, .localFeedbackPendingV1]
        let expected = ["local-message-storage-v1", "local-memory-pending-v1", "local-trip-pending-v1", "local-needs-pending-v1", "local-feedback-pending-v1"]
        for (purpose, suffix) in zip(purposes, expected) {
            let namespace = MessageKeyNamespace(environment: environment, account: account, purpose: purpose)
            #expect(namespace.service == "G2C.CJAuth.message-key.11111111-1111-4111-8111-111111111111")
            #expect(namespace.slot == "22222222-2222-4222-8222-222222222222." + suffix)
        }
    }
    @Test func feedbackPurposeScopeAndCleanupCannotCrossExistingKeys() throws {
        let environment = UUID(), account = UUID(), fixture = ScopedKeychainFixture()
        let namespaces = [
            MessageKeyNamespace(environment: environment, account: account, purpose: .localMessageStorageV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localMemoryPendingV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localTripPendingV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localNeedsPendingV1),
            MessageKeyNamespace(environment: environment, account: account, purpose: .localFeedbackPendingV1),
            MessageKeyNamespace(environment: environment, account: UUID(), purpose: .localFeedbackPendingV1),
            MessageKeyNamespace(environment: UUID(), account: account, purpose: .localFeedbackPendingV1)]
        let providers = try namespaces.map { namespace in
            ScopedMessageKeyProvider(namespace: namespace, persistence: try KeychainMessageKeys(namespace: namespace,
                applicationIdentifier: "SYNTHETIC.local.feedback-test", protection: .whenUnlockedThisDeviceOnly, operations: fixture.operations))
        }
        var keys = try providers.map { try $0.create(storageState: .confirmedEmpty, for: $0.begin(.create)) }
        #expect(Set(keys.map(\.id)).count == 7)
        let original = Data("synthetic-original-feedback-action-bytes".utf8)
        let sealed = try keys[4].withSymmetricKey { try AES.GCM.seal(original, using: $0) }
        for index in [0, 1, 2, 3, 5, 6] {
            #expect(throws: (any Error).self) { try keys[index].withSymmetricKey { try AES.GCM.open(sealed, using: $0) } }
            #expect(throws: MessageKeyFailure.keyMismatch) { try providers[index].existing(expectedID: keys[4].id, for: providers[index].begin(.lookup)) }
            #expect(throws: MessageKeyFailure.keyMismatch) { try providers[index].clear(expectedID: keys[4].id, storageState: .confirmedEmpty, for: providers[index].begin(.clear)) }
            let foreign = try providers[index].begin(.lookup)
            #expect(throws: MessageKeyFailure.staleOperation) { try providers[4].existing(expectedID: keys[4].id, for: foreign) }
        }
        for index in [0, 1, 2, 3] {
            try providers[index].clear(expectedID: keys[index].id, storageState: .confirmedEmpty, for: providers[index].begin(.clear))
            let result = try providers[4].existing(expectedID: keys[4].id, for: providers[4].begin(.lookup))
            let restored = try #require(result)
            #expect(restored.namespace == namespaces[4])
            #expect(try restored.withSymmetricKey { try AES.GCM.open(sealed, using: $0) } == original)
            keys[index] = try providers[index].create(storageState: .confirmedEmpty, for: providers[index].begin(.create))
        }
        try providers[4].clear(expectedID: keys[4].id, storageState: .confirmedEmpty, for: providers[4].begin(.clear))
        #expect(try providers[4].existing(expectedID: keys[4].id, for: providers[4].begin(.lookup)) == nil)
        for index in [0, 1, 2, 3, 5, 6] {
            #expect(try providers[index].existing(expectedID: keys[index].id, for: providers[index].begin(.lookup))?.id == keys[index].id)
        }
    }
    @Test func feedbackPendingUnknownCreateAndClearUseOriginalReadback() throws {
        let storage = Storage(); storage.failAdd = true; storage.commitBeforeAddError = true
        let namespace = MessageKeyNamespace(environment: UUID(), account: UUID(), purpose: .localFeedbackPendingV1)
        let provider = ScopedMessageKeyProvider(namespace: namespace, persistence: storage)
        #expect(throws: MessageKeyFailure.storageUnavailable) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        let original = try #require(storage.value)
        #expect(throws: MessageKeyFailure.creationUnconfirmed) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        let reconciled = try provider.reconcileCreation(for: provider.begin(.reconcileCreation))
        #expect(reconciled.id == original.id && reconciled.namespace == namespace && storage.adds == 1)
        storage.failRemove = true; storage.commitBeforeRemoveError = true
        #expect(throws: MessageKeyFailure.storageUnavailable) { try provider.clear(expectedID: original.id, storageState: .confirmedEmpty, for: provider.begin(.clear)) }
        #expect(throws: MessageKeyFailure.clearUnconfirmed) { try provider.create(storageState: .confirmedEmpty, for: provider.begin(.create)) }
        #expect(try provider.reconcileClear(for: provider.begin(.reconcileClear)))
        #expect(storage.adds == 1 && storage.deletes == 1 && !provider.canUseRestrictedBusiness)
    }
}
