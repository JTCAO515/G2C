import Foundation
import Testing
import CJAuth
import CJSession
@testable import CJShell

@MainActor private final class MemorySessionStore: SessionPersistence {
    var loads = 0
    var clears = 0
    var blocked = false
    var failClear = false
    var failLoad = false
    var material: SessionMaterial? = try! SessionMaterial(trustedSDKBytes: Data([1, 2, 3]))
    func load() throws -> SessionMaterial? {
        loads += 1
        if failLoad { throw SessionFailure.storageUnavailable }
        if blocked { throw SessionFailure.restorationBlocked }
        return material
    }
    func save(_ material: SessionMaterial) throws { self.material = material; blocked = false }
    func clearAndBlock() throws {
        clears += 1
        if failClear { throw SessionFailure.storageUnavailable }
        material = nil; blocked = true
    }
}
@MainActor private final class RestoreControl {
    var reply: CheckedContinuation<RestoreCheckResult, Never>?
    var operation: SessionOperation?
    func verify(_ material: SessionMaterial, _ operation: SessionOperation) async -> RestoreCheckResult {
        self.operation = operation
        return await withCheckedContinuation { reply = $0 }
    }
    func finish(_ value: RestoreCheckResult) { let pending = reply; reply = nil; pending?.resume(returning: value) }
}
@MainActor private final class CountAdapter: AuthSDKAdapter {
    var calls = 0
    func unavailableReason(for action: AuthAction) -> UnavailableReason? { nil }
    func perform(_ attempt: AuthAttempt) async -> SDKEvent { calls += 1; return .networkUnknown }
}

@Suite @MainActor struct LocalSessionHostTests {
    private func shell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "cj006.session.tests.\(UUID().uuidString)")))
    }
    private func wait(_ condition: () -> Bool) async {
        for _ in 0..<1000 { if condition() { return }; await Task.yield() }
        #expect(condition(), "Synthetic session task did not reach expected state")
    }
    @Test func unconfiguredNeverRestores() throws {
        let shell = try shell(); let host = AccountHost(shell: shell)
        let generation = shell.generation
        host.restoreSession()
        #expect(host.localSessionStatus == .notConfigured && !host.canRestoreSession)
        #expect(shell.generation == generation && !host.hasSessionStore)
    }
    @Test func explicitReadOnlyNeedsVerificationAndDoesNotGrant() throws {
        let shell = try shell(); shell.draft = "old private"
        let store = MemorySessionStore()
        let host = AccountHost(shell: shell, session: SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)) { _, _ in UnconfiguredSDKAdapter() }
        #expect(store.loads == 0)
        host.restoreSession()
        #expect(store.loads == 1 && store.clears == 0)
        #expect(host.localSessionStatus == .needsVerification && !host.canUseRestrictedBusiness)
        #expect(shell.draft.isEmpty && shell.presentation == ShellPresentation())
        #expect(!host.canRestoreSession)
    }
    @Test func clearFailureFencesPrivateUIAndPreventsDispatchUntilExplicitRetry() async throws {
        let shell = try shell(); shell.draft = "old private"
        let store = MemorySessionStore(); store.failClear = true
        let adapter = CountAdapter()
        let host = AccountHost(shell: shell, session: SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)) { _, _ in adapter }
        var password = "synthetic-only"
        host.submit(.emailSignIn, email: "fixture@example.invalid", password: &password)
        #expect(password.isEmpty && shell.draft.isEmpty && shell.memoryPath == [.account])
        #expect(host.localSessionStatus == .blocked(.storageUnavailable))
        #expect(adapter.calls == 0 && !host.canRestoreSession && !host.canSubmitAccount)
        host.restoreSession(); #expect(store.loads == 0)
        store.failClear = false
        host.clearLocalSession()
        #expect(host.localSessionStatus == .cleared && host.canSubmitAccount && !host.canRestoreSession)
    }
    @Test func pendingRestoreClearAndLateResultCannotRevivePrivateState() async throws {
        let shell = try shell(); let store = MemorySessionStore(); let control = RestoreControl()
        let lifecycle = SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)
        let host = AccountHost(shell: shell, session: lifecycle, verifyRestored: control.verify) { _, _ in UnconfiguredSDKAdapter() }
        host.restoreSession(); await wait { control.reply != nil }
        let operation = try #require(control.operation)
        host.clearLocalSession()
        #expect(!lifecycle.isCurrent(operation) && shell.memoryPath == [.account])
        let clean = shell.generation
        control.finish(.needsServerVerification)
        for _ in 0..<10 { await Task.yield() }
        #expect(host.localSessionStatus == .cleared && shell.generation == clean)
        #expect(shell.presentation == ShellPresentation() && host.requiresReconciliation)
    }
    @Test func restoreUnknownPreservesStoreAndBlocksReplacementEvenAfterClear() async throws {
        let shell = try shell(); let store = MemorySessionStore(); let control = RestoreControl()
        let lifecycle = SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)
        let adapter = CountAdapter()
        let host = AccountHost(shell: shell, session: lifecycle, verifyRestored: control.verify) { _, _ in adapter }
        host.restoreSession(); await wait { control.reply != nil }
        let generation = shell.generation
        let operation = try #require(control.operation)
        control.finish(.networkUnknown); await wait { host.localSessionStatus == .unknown }
        #expect(store.clears == 0 && store.material != nil && shell.generation == generation)
        #expect(lifecycle.isCurrent(operation) && host.requiresReconciliation)
        host.restoreSession(); #expect(store.loads == 1)
        host.clearLocalSession()
        var password = "synthetic-only"
        host.submit(.emailSignIn, email: "fixture@example.invalid", password: &password)
        #expect(host.requiresReconciliation && adapter.calls == 0)
    }
    @Test func languageDoesNotReplaceRestoreAndRejectedIsNotLogin() async throws {
        let shell = try shell(); let store = MemorySessionStore(); let control = RestoreControl()
        let lifecycle = SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)
        let host = AccountHost(shell: shell, session: lifecycle, verifyRestored: control.verify) { _, _ in UnconfiguredSDKAdapter() }
        host.restoreSession(); await wait { control.reply != nil }
        let generation = shell.generation
        let operation = try #require(control.operation)
        shell.selectLanguage(.chinese)
        #expect(shell.generation == generation && lifecycle.isCurrent(operation) && store.loads == 1)
        control.finish(.rejected); await wait { host.localSessionStatus == .verificationFailed }
        #expect(!host.canUseRestrictedBusiness && store.clears == 0)
    }
    @Test func storageLoadFailureBlocksRestoreWithoutReportingMissing() throws {
        let shell = try shell(); let store = MemorySessionStore(); store.failLoad = true
        let host = AccountHost(shell: shell, session: SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)) { _, _ in UnconfiguredSDKAdapter() }
        host.restoreSession()
        #expect(host.localSessionStatus == .blocked(.storageUnavailable))
        #expect(!host.canRestoreSession && !host.canSubmitAccount)
    }
    @Test func externalUIInvalidationCannotLeaveStaleRestoreWaitingForever() async throws {
        let shell = try shell(); let store = MemorySessionStore(); let control = RestoreControl()
        let host = AccountHost(shell: shell, session: SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly), verifyRestored: control.verify) { _, _ in UnconfiguredSDKAdapter() }
        host.restoreSession(); await wait { control.reply != nil }
        shell.invalidateIdentity()
        control.finish(.needsServerVerification)
        await wait { !host.isRestoring }
        #expect(host.localSessionStatus == .unknown && host.requiresReconciliation)
        #expect(shell.presentation == ShellPresentation() && store.clears == 0)
    }

    @Test func localCleanupCannotBypassOriginalAuthAttemptUnknown() async throws {
        let shell = try shell(); let store = MemorySessionStore(); let adapter = CountAdapter()
        let host = AccountHost(shell: shell, session: SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)) { _, _ in adapter }
        var password = "synthetic-only"
        host.submit(.emailSignIn, email: "fixture@example.invalid", password: &password)
        await wait { host.state == .networkUnknown }
        #expect(adapter.calls == 1 && host.requiresReconciliation)
        host.clearLocalSession()
        #expect(host.localSessionStatus == .cleared && host.requiresReconciliation)
        host.restoreSession()
        host.submit(.googleSignIn, password: &password)
        #expect(adapter.calls == 1 && store.loads == 0 && !host.canSubmitAccount)
    }

}
