import Foundation
import Testing
import CJAuth
import CJSession
import CJMessageClient
@testable import CJShell

@MainActor private final class IdentityMessages: SecureMessageStorage {
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
}
@MainActor private final class IdentitySession: SessionPersistence {
    var clears = 0
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws { clears += 1 }
}

@Suite @MainActor struct IdentityCallbackReentryTests {
    @Test func outerCleanupCannotOverwriteCallbackInstalledB() throws {
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: "identity-reentry-" + UUID().uuidString)))
        let a = MessageRecovery(storage: IdentityMessages()), b = MessageRecovery(storage: IdentityMessages())
        let sa = try StorageScope(environment: UUID().uuidString, account: "a")
        let sb = try StorageScope(environment: UUID().uuidString, account: "b")
        let la = try a.activate(sa), lb = try b.activate(sb)
        let host = AssistantMessageHost(shell: shell)
        let store = IdentitySession()
        let identity = AccountHost(shell: shell, session: SessionLifecycle(persistence: store, restorePolicy: .userInitiatedOnly)) { _, _ in UnconfiguredSDKAdapter() }
        var once = true, rebound = false
        var bGeneration: ShellGeneration?
        #expect(host.bind(AssistantMessageBinding(recovery: a, scope: sa, lease: la, generation: shell.generation,
            conversationID: "a", synthetic: true, isCurrent: { true }, invalidateResources: {
                if once {
                    once = false
                    identity.clearLocalSession()
                    bGeneration = shell.generation
                    rebound = host.bind(AssistantMessageBinding(recovery: b, scope: sb, lease: lb, generation: shell.generation,
                        conversationID: "b", synthetic: true, isCurrent: { true }, invalidateResources: {}))
                    shell.draft = "synthetic reentrant B editor"
                    shell.memoryPath = [.privacy]
                    shell.apply(ShellPresentation(assistantBody: "synthetic B body"), for: shell.generation)
                }
            })))
        identity.clearLocalSession()
        #expect(rebound && host.isConfigured)
        #expect(shell.generation == bGeneration)
        #expect(shell.draft == "synthetic reentrant B editor")
        #expect(shell.memoryPath == [.privacy] && shell.assistantBody == "synthetic B body")
        #expect(store.clears == 1, "Only nested B lifecycle cleanup may proceed; stale outer cleanup must not touch its store")
        try b.validateScope(sb, lease: lb)
    }
    @Test func normalInvalidationClearsBeforeResourceCallback() throws {
        let shell = ShellState(preferences: try #require(UserDefaults(suiteName: "identity-normal-" + UUID().uuidString)))
        let recovery = MessageRecovery(storage: IdentityMessages())
        let scope = try StorageScope(environment: UUID().uuidString, account: "a")
        let lease = try recovery.activate(scope)
        let host = AssistantMessageHost(shell: shell)
        let old = shell.generation
        var sawCleared = false
        #expect(host.bind(AssistantMessageBinding(recovery: recovery, scope: scope, lease: lease, generation: old,
            conversationID: "a", synthetic: true, isCurrent: { true }, invalidateResources: {
                sawCleared = shell.generation != old && shell.draft.isEmpty && shell.memoryPath.isEmpty
                    && shell.presentation == ShellPresentation() && shell.messageBindingBlocked
            })))
        shell.draft = "synthetic old"
        shell.memoryPath = [.account]
        shell.apply(ShellPresentation(assistantBody: "synthetic old body"), for: old)
        shell.invalidateIdentity()
        #expect(sawCleared && !host.isConfigured && shell.messageBindingBlocked)
        #expect(!shell.apply(ShellPresentation(assistantBody: "late"), for: old))
    }
}
