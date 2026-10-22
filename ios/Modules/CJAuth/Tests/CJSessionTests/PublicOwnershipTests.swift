import Foundation
import Testing
import CJSession

@MainActor private final class OwnershipStorage: SessionPersistence {
    var fail = false
    func load() throws -> SessionMaterial? { if fail { throw SessionFailure.storageUnavailable }; return nil }
    func save(_ material: SessionMaterial) throws { if fail { throw SessionFailure.storageUnavailable } }
    func clearAndBlock() throws { if fail { throw SessionFailure.storageUnavailable } }
}
@Suite @MainActor struct PublicOwnershipTests {
    @Test func originalOperationRemainsOwnedAfterGenuineBlockButNotUsable() throws {
        let storage = OwnershipStorage()
        let lifecycle = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        let operation = try lifecycle.beginUserRestore()
        #expect(lifecycle.ownsOperation(operation) && lifecycle.isCurrent(operation))
        storage.fail = true
        #expect(throws: SessionFailure.storageUnavailable) { try lifecycle.load(for: operation) }
        #expect(lifecycle.ownsOperation(operation) && !lifecycle.isCurrent(operation))
        #expect(!lifecycle.canUseRestrictedBusiness)
    }
    @Test func newOperationReplacesOldOwnership() throws {
        let lifecycle = SessionLifecycle(persistence: OwnershipStorage(), restorePolicy: .userInitiatedOnly)
        let old = try lifecycle.beginUserRestore()
        let next = try lifecycle.beginTrustedSDKSave()
        #expect(!lifecycle.ownsOperation(old) && lifecycle.ownsOperation(next))
    }
    @Test func clearSuccessAndFailureBothRetirePriorOperation() throws {
        for fail in [false, true] {
            let storage = OwnershipStorage()
            let lifecycle = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
            let old = try lifecycle.beginUserRestore()
            storage.fail = fail
            if fail { #expect(throws: SessionFailure.storageUnavailable) { try lifecycle.clear() } }
            else { try lifecycle.clear() }
            #expect(!lifecycle.ownsOperation(old) && !lifecycle.isCurrent(old))
        }
    }
    @Test func differentLifecycleCannotOwnTokenEvenUsingSameStorage() throws {
        let storage = OwnershipStorage()
        let a = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        let b = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        let operation = try a.beginUserRestore()
        #expect(a.ownsOperation(operation) && !b.ownsOperation(operation))
    }
}
