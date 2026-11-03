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
    var deletes = 0
    var deleteStatus: OSStatus = errSecSuccess
    var keepAfterDelete = false
    var readbackStatus: OSStatus?
    var operations: KeychainOperations {
        KeychainOperations(copy: { query in
            self.lastQuery = query
            if self.deletes > 0, let status = self.readbackStatus { return (status, nil) }
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
        }, delete: { query in
            self.lastQuery = query; self.deletes += 1
            guard self.deleteStatus == errSecSuccess else { return self.deleteStatus }
            if !self.keepAfterDelete { self.data = nil }
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
    @Test func conditionalControlRemovalUsesExactQueryAndChecksPhysicalAbsence() throws {
        let scope = try KeychainSessionScope(namespace: .init(environment: UUID(), slot: "M3.Cleanup.Device.A"), applicationIdentifier: "SYNTHETIC.app")
        let fake = FakeKeychain(), expected = try material()
        let store = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly, operations: fake.operations)
        try store.save(expected)
        #expect(try store.removeIfMatching(expected))
        #expect(fake.data == nil && fake.deletes == 1)
        #expect(fake.lastQuery[kSecAttrService as String] as? String == scope.namespace.service)
        #expect(fake.lastQuery[kSecAttrAccount as String] as? String == scope.namespace.slot)
        #expect(fake.lastQuery[kSecAttrAccessGroup as String] as? String == scope.applicationIdentifier)
        #expect(fake.lastQuery[kSecAttrSynchronizable as String] as? Bool == false)
        #expect(try store.load() == nil)
        #expect(try !store.removeIfMatching(expected))
        #expect(fake.deletes == 1)
    }
    @Test func changedControlSelectedPointerAndBlockedRecordAreNeverDeleted() throws {
        let scope = try KeychainSessionScope(namespace: .init(environment: UUID(), slot: "M3.Cleanup.Selected"), applicationIdentifier: "SYNTHETIC.app")
        let fake = FakeKeychain(), expected = try material()
        let store = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly, operations: fake.operations)
        let replacement = try SessionMaterial(trustedSDKBytes: Data("OTHER-ACCOUNT-CONTROL".utf8))
        try store.save(replacement); let before = fake.data
        #expect(try !store.removeIfMatching(expected))
        #expect(fake.data == before && fake.deletes == 0)
        try store.clearAndBlock(); let blocked = fake.data
        #expect(try !store.removeIfMatching(expected))
        #expect(fake.data == blocked && fake.deletes == 0)
    }
    @Test func conditionalRemovalFailureOrUnconfirmedReadbackCannotBecomeSuccess() throws {
        let scope = try KeychainSessionScope(namespace: .init(environment: UUID(), slot: "M3.Cleanup.Account.A"), applicationIdentifier: "SYNTHETIC.app")
        let expected = try material()
        for stage in ["locked", "delete", "retained", "readback"] {
            let fake = FakeKeychain()
            let store = KeychainSessionStore(scope: scope, protection: .whenUnlockedThisDeviceOnly, operations: fake.operations)
            try store.save(expected)
            switch stage {
            case "locked": fake.status = errSecInteractionNotAllowed
            case "delete": fake.deleteStatus = errSecNotAvailable
            case "retained": fake.keepAfterDelete = true
            default: fake.readbackStatus = errSecInteractionNotAllowed
            }
            #expect(throws: (any Error).self) { try store.removeIfMatching(expected) }
            #expect(fake.deletes == (stage == "locked" ? 0 : 1))
        }
    }
    @Test func conditionalRemovalKeepsAnotherAccountAndEnvironmentInTheSameKeychain() throws {
        var records: [[String]: Data] = [:]
        func key(_ query: [String: Any]) -> [String] {
            #expect(query[kSecClass as String] as? String == kSecClassGenericPassword as String)
            #expect(query[kSecAttrSynchronizable as String] as? Bool == false)
            return [kSecAttrService, kSecAttrAccount, kSecAttrAccessGroup].map { query[$0 as String] as! String }
        }
        let operations = KeychainOperations(copy: { query in
            guard let data = records[key(query)] else { return (errSecItemNotFound, nil) }
            return (errSecSuccess, data)
        }, add: { query in
            let id = key(query); guard records[id] == nil else { return errSecDuplicateItem }
            records[id] = query[kSecValueData as String] as? Data; return errSecSuccess
        }, update: { query, values in
            let id = key(query); guard records[id] != nil else { return errSecItemNotFound }
            records[id] = values[kSecValueData as String] as? Data; return errSecSuccess
        }, delete: { query in
            guard records.removeValue(forKey: key(query)) != nil else { return errSecItemNotFound }
            return errSecSuccess
        })
        let environment = UUID(), secret = try material()
        func store(_ env: UUID, _ account: String) throws -> KeychainSessionStore {
            KeychainSessionStore(scope: try .init(namespace: .init(environment: env, slot: account), applicationIdentifier: "SYNTHETIC.app"),
                protection: .whenUnlockedThisDeviceOnly, operations: operations)
        }
        let a = try store(environment, "M3.Cleanup.Device.A"), b = try store(environment, "M3.Cleanup.Device.B")
        let otherEnvironment = try store(UUID(), "M3.Cleanup.Device.A")
        try a.save(secret); try b.save(secret); try otherEnvironment.save(secret)
        let before = records
        #expect(try a.removeIfMatching(secret))
        #expect(records.count == 2)
        for (id, data) in records { #expect(before[id] == data) }
        #expect(try b.load()?.withBytes { $0 } == secret.withBytes { $0 })
        #expect(try otherEnvironment.load()?.withBytes { $0 } == secret.withBytes { $0 })
    }
}
