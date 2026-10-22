import Foundation
import Testing
@testable import CJMessageClient

@MainActor private final class ReplayStorage: SecureMessageStorage {
    var stored: Snapshot?
    var onSave: (() -> Void)?
    var failSave = false
    func load(scope: StorageScope) throws -> Snapshot? { stored }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {
        let hook = onSave; onSave = nil; hook?()
        if failSave { throw RecoveryError.persistenceUnknown }
        stored = snapshot
    }
}
@Suite @MainActor struct FreshAuthorizationTests {
    private func scope() throws -> StorageScope { try StorageScope(environment:"synthetic-"+UUID().uuidString,account:"a") }
    @Test func clearedSnapshotCannotRegrantInSameProcessOrNewCoordinator() throws {
        let store = ReplayStorage(); let scope = try scope(); let state = MessageRecovery(storage:store)
        let lease = try state.activate(scope); let raw = Data("original fixture".utf8)
        try state.stage(messageID:"m1",originalUTF8:raw,lease:lease)
        _ = try state.beginSubmission(messageID:"m1",lease:lease)
        store.stored = nil
        let next = try state.activate(scope)
        #expect(throws:RecoveryError.self) { try state.stage(messageID:"m1",originalUTF8:raw,lease:next) }
        let other = MessageRecovery(storage:store); let otherLease = try other.activate(scope)
        #expect(throws:RecoveryError.self) { try other.stage(messageID:"new-id",originalUTF8:raw,lease:otherLease) }
    }
    @Test func storageReentryCannotConsumeAuthorizationTwice() throws {
        let store = ReplayStorage(); let state = MessageRecovery(storage:store); let lease = try state.activate(scope())
        try state.stage(messageID:"m1",originalUTF8:Data("original".utf8),lease:lease)
        var secondWasRejected = false
        store.onSave = {
            do { _ = try state.beginSubmission(messageID:"m1",lease:lease) }
            catch { secondWasRejected = true }
        }
        _ = try state.beginSubmission(messageID:"m1",lease:lease)
        #expect(secondWasRejected)
    }
    @Test func callbackScopeSwitchCannotWriteOrInvalidateNewScope() throws {
        for fail in [false, true] {
            let store = ReplayStorage(); let state = MessageRecovery(storage:store)
            let first = try state.activate(scope())
            try state.stage(messageID:"m1",originalUTF8:Data("original".utf8),lease:first)
            let other = try scope(); var nextLease: Lease?
            store.onSave = { nextLease = try? state.activate(other) }
            store.failSave = fail
            #expect(throws:RecoveryError.self) { try state.beginSubmission(messageID:"m1",lease:first) }
            let next = try #require(nextLease)
            try state.validateScope(other,lease:next)
        }
    }

    @Test func loadSaveDoesNotSerializeFreshAuthority() throws {
        let store = ReplayStorage(); let scope = try scope(); let state = MessageRecovery(storage:store)
        let lease = try state.activate(scope)
        try state.stage(messageID:"m1",originalUTF8:Data("original".utf8),lease:lease)
        let encoded = try JSONEncoder().encode(try #require(store.stored))
        store.stored = try JSONDecoder().decode(Snapshot.self,from:encoded)
        let reopened = MessageRecovery(storage:store); let next = try reopened.activate(scope)
        #expect(try reopened.action(messageID:"m1",lease:next)?.phase == .queryRequired)
        #expect(throws:RecoveryError.self) { try reopened.beginSubmission(messageID:"m1",lease:next) }
    }
    @Test func unknownSaveCannotRecoverFreshAuthorityByRestaging() throws {
        let store = ReplayStorage(); let scope = try scope(); let state = MessageRecovery(storage:store)
        let lease = try state.activate(scope)
        store.failSave = true
        #expect(throws:RecoveryError.self) { try state.stage(messageID:"m1",originalUTF8:Data("original".utf8),lease:lease) }
        store.failSave = false; store.stored = nil
        let next = try state.activate(scope)
        #expect(throws:RecoveryError.self) { try state.stage(messageID:"m1",originalUTF8:Data("original".utf8),lease:next) }
    }
}
