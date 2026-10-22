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
