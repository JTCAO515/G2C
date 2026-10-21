import Foundation
import Security
import Testing
@testable import CJSession

@MainActor private final class MemoryPersistence: SessionPersistence {
    var material: SessionMaterial?
    var tombstone = false
    var failure: SessionFailure?
    var loads = 0
    func load() throws -> SessionMaterial? {
        loads += 1
        if let failure { throw failure }
        if tombstone { throw SessionFailure.restorationBlocked }
        return material
    }
    func save(_ value: SessionMaterial) throws { if let failure { throw failure }; material = value; tombstone = false }
    func clearAndBlock() throws { if let failure { throw failure }; material = nil; tombstone = true }
}

@MainActor private final class FakeKeychain {
    var data: Data?
    var status: OSStatus = errSecSuccess
    var lastQuery: [String: Any] = [:]
    var lastValues: [String: Any] = [:]
    var adds = 0
    var operations: KeychainOperations {
        KeychainOperations(copy: { query in
            self.lastQuery = query
            if self.status != errSecSuccess { return (self.status, nil) }
            return self.data.map { (errSecSuccess, $0) } ?? (errSecItemNotFound, nil)
        }, add: { query in
            self.adds += 1; self.lastQuery = query
            if self.status != errSecSuccess { return self.status }
            self.data = query[kSecValueData as String] as? Data
            return errSecSuccess
        }, update: { query, values in
            self.lastQuery = query; self.lastValues = values
            if self.status != errSecSuccess { return self.status }
            guard self.data != nil else { return errSecItemNotFound }
            self.data = values[kSecValueData as String] as? Data
            return errSecSuccess
        })
    }
}

@Suite @MainActor struct SessionStoreTests {
    func material() throws -> SessionMaterial { try .init(trustedSDKBytes: Data("SYNTHETIC-SESSION-NOT-A-TOKEN".utf8)) }
    @Test func saveLoadRedactionAndNoBusinessGrant() throws {
        let storage = MemoryPersistence(); let lifecycle = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        let secret = try material()
        try lifecycle.save(secret, for: lifecycle.beginTrustedSDKSave())
        let operation = try lifecycle.beginUserRestore()
        let restored = try lifecycle.load(for: operation)
        let loaded = try #require(restored)
        #expect(loaded.withBytes { $0 == secret.withBytes { $0 } })
        #expect(lifecycle.state == .loadedNeedsVerification && !lifecycle.canUseRestrictedBusiness)
        #expect(!String(reflecting: loaded).contains("SYNTHETIC"))
        #expect(Mirror(reflecting: loaded).children.isEmpty)
    }
    @Test func automaticRestoreNeverTouchesStorageEvenAfterRecreation() throws {
        let storage = MemoryPersistence(); storage.material = try material()
        for _ in 0..<2 {
            let lifecycle = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
            #expect(throws: SessionFailure.automaticRestoreUnavailable) { try lifecycle.restoreAutomatically() }
        }
        #expect(storage.loads == 0)
    }
    @Test func lateDuplicateWrongPurposeAndOtherInstanceRejected() throws {
        let storage = MemoryPersistence(); let a = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        let b = SessionLifecycle(persistence: MemoryPersistence(), restorePolicy: .userInitiatedOnly)
        let old = try a.beginTrustedSDKSave(); let secret = try material()
        #expect(throws: SessionFailure.staleOperation) { try b.save(secret, for: old) }
        try a.clear()
        #expect(throws: SessionFailure.staleOperation) { try a.save(secret, for: old) }
        let current = try a.beginTrustedSDKSave()
        #expect(throws: SessionFailure.staleOperation) { try a.load(for: current) }
        try a.save(secret, for: current)
        #expect(throws: SessionFailure.staleOperation) { try a.save(secret, for: current) }
    }
    @Test func clearFailureBlocksLoadSaveAndRetryClearFencesOldWork() throws {
        let storage = MemoryPersistence(); let lifecycle = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        let old = try lifecycle.beginTrustedSDKSave()
        storage.failure = .keychain(errSecInteractionNotAllowed)
        #expect(throws: SessionFailure.keychain(errSecInteractionNotAllowed)) { try lifecycle.clear() }
        #expect(throws: SessionFailure.restorationBlocked) { try lifecycle.beginUserRestore() }
        #expect(throws: SessionFailure.restorationBlocked) { try lifecycle.beginTrustedSDKSave() }
        lifecycle.noteNetworkUnknown()
        #expect(lifecycle.state == .blocked(.keychain(errSecInteractionNotAllowed)))
        storage.failure = nil; try lifecycle.clear()
        let secret = try material()
        #expect(throws: SessionFailure.staleOperation) { try lifecycle.save(secret, for: old) }
        let recreated = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        #expect(throws: SessionFailure.restorationBlocked) { try recreated.load(for: recreated.beginUserRestore()) }
    }
    @Test func networkUnknownPreservesBytesAndBinding() throws {
        let storage = MemoryPersistence(); let lifecycle = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        try lifecycle.save(material(), for: lifecycle.beginTrustedSDKSave())
        let original = try lifecycle.beginUserRestore()
        lifecycle.noteNetworkUnknown()
        #expect(lifecycle.isCurrent(original))
        #expect(try lifecycle.load(for: original) != nil)
        #expect(!storage.tombstone)
    }
    @Test func loadAndSaveFailureAreExplicitNotMissing() throws {
        for load in [true, false] {
            let storage = MemoryPersistence(); storage.failure = .storageUnavailable
            let lifecycle = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
            #expect(throws: SessionFailure.storageUnavailable) {
                if load { _ = try lifecycle.load(for: lifecycle.beginUserRestore()) }
                else { try lifecycle.save(material(), for: lifecycle.beginTrustedSDKSave()) }
            }
            #expect(lifecycle.state == .blocked(.storageUnavailable))
        }
    }
    @Test func keychainQueriesAreExactAndTombstoneSurvivesAdapterRecreation() throws {
        let ns = try SessionNamespace(environment: UUID(), slot: "synthetic-slot")
        let scope = try KeychainSessionScope(namespace: ns, applicationIdentifier: "SYNTHETIC.local.cj007")
        let fake = FakeKeychain()
        let store = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly, operations: fake.operations)
        try store.save(material())
        #expect(fake.lastQuery[kSecAttrService as String] as? String == ns.service)
        #expect(fake.lastQuery[kSecAttrAccount as String] as? String == ns.slot)
        #expect(fake.lastQuery[kSecAttrAccessGroup as String] as? String == scope.applicationIdentifier)
        #expect(fake.lastQuery[kSecAttrSynchronizable as String] as? Bool == false)
        #expect(fake.lastQuery[kSecAttrAccessible as String] as? String == kSecAttrAccessibleWhenUnlockedThisDeviceOnly as String)
        #expect(try store.load() != nil)
        try store.clearAndBlock()
        let recreated = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly, operations: fake.operations)
        #expect(throws: SessionFailure.restorationBlocked) { try recreated.load() }
        #expect(fake.data?.count == 5) // no session bytes left
    }
    @Test func keychainLockedAndCorruptAreNotNotFoundAndNoBlindFallback() throws {
        let scope = try KeychainSessionScope(namespace: .init(environment: UUID(), slot: "synthetic"), applicationIdentifier: "SYNTHETIC.app")
        let fake = FakeKeychain()
        let store = KeychainSessionStore(scope: scope, protection: .afterFirstUnlockThisDeviceOnly, operations: fake.operations)
        #expect(try store.load() == nil)
        fake.data = Data([1, 2, 3])
        #expect(throws: SessionFailure.malformedRecord) { try store.load() }
        fake.status = errSecInteractionNotAllowed
        #expect(throws: SessionFailure.keychain(errSecInteractionNotAllowed)) { try store.load() }
        #expect(throws: SessionFailure.keychain(errSecInteractionNotAllowed)) { try store.clearAndBlock() }
        #expect(fake.adds == 0)
    }
    @Test func emptyOrBroadConfigurationRejected() throws {
        #expect(throws: SessionFailure.invalidConfiguration) { try SessionNamespace(environment: UUID(), slot: "") }
        #expect(throws: SessionFailure.invalidConfiguration) { try SessionNamespace(environment: UUID(), slot: "user@example.invalid") }
        let ns = try SessionNamespace(environment: UUID(), slot: "synthetic")
        #expect(throws: SessionFailure.invalidConfiguration) { try KeychainSessionScope(namespace: ns, applicationIdentifier: "*") }
        #expect(throws: SessionFailure.emptyMaterial) { try SessionMaterial(trustedSDKBytes: Data()) }
    }
}
