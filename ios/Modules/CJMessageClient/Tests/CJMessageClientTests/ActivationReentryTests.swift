import Foundation
import Testing
@testable import CJMessageClient

private enum LoadFault: Error { case injected }
@MainActor private final class CallbackLoadStore: SecureMessageStorage {
    var onLoad: (() throws -> Void)?
    func load(scope: StorageScope) throws -> Snapshot? {
        var value = Snapshot()
        let id = scope.account
        value.actions[Data(id.utf8).base64EncodedString()] = ActionRecord(messageID:id,originalUTF8:Data(id.utf8),phase:.staged)
        let hook = onLoad; onLoad = nil
        try hook?()
        return value
    }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { }
}
@Suite @MainActor struct ActivationReentryTests {
    @Test func oldLoadCannotReplaceCallbackActivatedAccount() throws {
        let store=CallbackLoadStore(); let state=MessageRecovery(storage:store)
        let env=UUID().uuidString
        let a=try StorageScope(environment:env,account:"a"), b=try StorageScope(environment:env,account:"b")
        var bLease: Lease?
        store.onLoad = { bLease = try state.activate(b) }
        #expect(throws:RecoveryError.self) { try state.activate(a) }
        let current=try #require(bLease)
        try state.validateScope(b,lease:current)
        #expect(try state.action(messageID:"b",lease:current) != nil)
        #expect(try state.action(messageID:"a",lease:current) == nil)
    }
    @Test func invalidationDuringLoadCannotReactivateOldAccount() throws {
        let store=CallbackLoadStore(); let state=MessageRecovery(storage:store)
        let a=try StorageScope(environment:UUID().uuidString,account:"a")
        store.onLoad = { state.invalidate() }
        #expect(throws:RecoveryError.self) { try state.activate(a) }
    }
    @Test func oldLoadErrorDoesNotInvalidateCallbackActivatedAccount() throws {
        let store=CallbackLoadStore(); let state=MessageRecovery(storage:store)
        let env=UUID().uuidString
        let a=try StorageScope(environment:env,account:"a"), b=try StorageScope(environment:env,account:"b")
        var bLease: Lease?
        store.onLoad = { bLease = try state.activate(b); throw LoadFault.injected }
        #expect(throws:LoadFault.self) { try state.activate(a) }
        let current=try #require(bLease)
        try state.validateScope(b,lease:current)
        #expect(try state.action(messageID:"a",lease:current) == nil)
        #expect(try state.action(messageID:"b",lease:current) != nil)
    }
    @Test func normalActivationAndFailedLoadRemainExplicit() throws {
        let store=CallbackLoadStore(); let state=MessageRecovery(storage:store)
        let a=try StorageScope(environment:UUID().uuidString,account:"a")
        let first=try state.activate(a)
        #expect(try state.action(messageID:"a",lease:first)?.phase == .queryRequired)
        store.onLoad = { throw LoadFault.injected }
        #expect(throws:LoadFault.self) { try state.activate(a) }
        #expect(throws:RecoveryError.self) { try state.action(messageID:"a",lease:first) }
        let recovered=try state.activate(a)
        #expect(try state.action(messageID:"a",lease:recovered)?.phase == .queryRequired)
    }
}
