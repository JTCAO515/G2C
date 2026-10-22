import Foundation
import Testing
import CJSession

@MainActor private final class ClearSettlementStorage: SessionPersistence {
    var material: SessionMaterial?
    var clearHook: (() throws -> Void)?
    var clearError: (any Error)?
    var saveError: SessionFailure?
    func load() throws -> SessionMaterial? { material }
    func save(_ value: SessionMaterial) throws {
        if let saveError { throw saveError }
        material = value
    }
    func clearAndBlock() throws {
        if let clearError { throw clearError }
        material = nil
        let callback = clearHook; clearHook = nil
        try callback?()
    }
}
private enum OtherStorageError: Error { case synthetic }

@Suite @MainActor struct ClearSettlementTests {
    @Test func normalClearSucceedsEvenThoughOldOperationRetires() throws {
        let storage = ClearSettlementStorage()
        let life = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        let old = try life.beginTrustedSDKSave()
        try life.save(SessionMaterial(trustedSDKBytes: Data("SYNTHETIC-A".utf8)), for: old)
        #expect(life.clearWithSettlement() == .cleared)
        #expect(!life.ownsOperation(old) && life.state == .cleared && storage.material == nil)
        #expect(!life.canUseRestrictedBusiness)
    }
    @Test func genuineOriginalFailurePreservesCanonicalFailureIncludingStaleName() {
        for failure in [SessionFailure.storageUnavailable, .staleOperation, .keychain(-1)] {
            let storage = ClearSettlementStorage(); storage.clearError = failure
            let life = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
            #expect(life.clearWithSettlement() == .failed(failure))
            #expect(life.state == .blocked(failure))
            #expect(throws: SessionFailure.restorationBlocked) { try life.beginUserRestore() }
        }
    }
    @Test func genericStorageErrorIsCanonicalizedWithoutExposingRawError() {
        let storage = ClearSettlementStorage(); storage.clearError = OtherStorageError.synthetic
        let life = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
        #expect(life.clearWithSettlement() == .failed(.storageUnavailable))
        #expect(life.state == .blocked(.storageUnavailable))
    }
    @Test func sameIdentityHealthyReplacementIsReplacedForSuccessOrErrorReturn() throws {
        for outerThrows in [false, true] {
            let storage = ClearSettlementStorage()
            let life = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
            var bOperation: SessionOperation?
            // One lifecycle/namespace; no verifier tuple or UI generation change is used.
            storage.clearHook = {
                try life.clear()
                let b = try life.beginTrustedSDKSave(); bOperation = b
                try life.save(SessionMaterial(trustedSDKBytes: Data("SYNTHETIC-B".utf8)), for: b)
                if outerThrows { throw SessionFailure.staleOperation }
            }
            #expect(life.clearWithSettlement() == .replaced)
            let b = try #require(bOperation)
            #expect(life.isCurrent(b) && life.state == .saved)
            #expect(storage.material?.withBytes { $0 == Data("SYNTHETIC-B".utf8) } == true)
        }
    }
    @Test func failedReplacementIsStillReplacedNotOriginalFailureOrNewAuthority() throws {
        for outerThrows in [false, true] {
            let storage = ClearSettlementStorage()
            let life = SessionLifecycle(persistence: storage, restorePolicy: .userInitiatedOnly)
            var bOperation: SessionOperation?
            storage.clearHook = {
                try life.clear()
                let b = try life.beginTrustedSDKSave(); bOperation = b
                storage.saveError = .storageUnavailable
                #expect(throws: SessionFailure.storageUnavailable) {
                    try life.save(SessionMaterial(trustedSDKBytes: Data("SYNTHETIC-B".utf8)), for: b)
                }
                if outerThrows { throw SessionFailure.staleOperation }
            }
            #expect(life.clearWithSettlement() == .replaced)
            let b = try #require(bOperation)
            #expect(life.ownsOperation(b) && !life.isCurrent(b))
            #expect(life.state == .blocked(.storageUnavailable) && !life.canUseRestrictedBusiness)
        }
    }
    @Test func legacyThrowingClearRetainsItsOriginalSurfaceAndAmbiguity() throws {
        let original = ClearSettlementStorage(); original.clearError = SessionFailure.staleOperation
        let failed = SessionLifecycle(persistence: original, restorePolicy: .userInitiatedOnly)
        #expect(throws: SessionFailure.staleOperation) { try failed.clear() }
        #expect(failed.state == .blocked(.staleOperation))
        let replacedStorage = ClearSettlementStorage()
        let replaced = SessionLifecycle(persistence: replacedStorage, restorePolicy: .userInitiatedOnly)
        var b: SessionOperation?
        replacedStorage.clearHook = {
            try replaced.clear()
            b = try replaced.beginTrustedSDKSave()
        }
        #expect(throws: SessionFailure.staleOperation) { try replaced.clear() }
        #expect(replaced.isCurrent(try #require(b)))
        let plain = SessionLifecycle(persistence: ClearSettlementStorage(), restorePolicy: .userInitiatedOnly)
        try plain.clear()
        #expect(plain.state == .cleared)
    }
}
