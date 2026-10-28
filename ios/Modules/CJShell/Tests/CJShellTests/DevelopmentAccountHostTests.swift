import Foundation
import Testing
import CJSession
@testable import CJShell

@MainActor private final class DevelopmentStore: SessionPersistence {
    var value: SessionMaterial?
    var clears = 0
    var loads = 0
    var blocked = false
    func load() throws -> SessionMaterial? {
        loads += 1
        if blocked { throw SessionFailure.restorationBlocked }
        return value
    }
    func save(_ material: SessionMaterial) throws { value = material; blocked = false }
    func clearAndBlock() throws { value = nil; blocked = true; clears += 1 }
}

@MainActor private final class DevelopmentChecks {
    var replies: [CheckedContinuation<DevelopmentSessionCheck, Never>] = []
    func check(_ material: SessionMaterial) async -> DevelopmentSessionCheck {
        await withCheckedContinuation { replies.append($0) }
    }
}

@Suite @MainActor struct DevelopmentAccountHostTests {
    private func makeShell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "cj161.\(UUID().uuidString)")))
    }
    private func wait(_ predicate: () -> Bool) async {
        for _ in 0..<1000 { if predicate() { return }; await Task.yield() }
        #expect(predicate())
    }
    private func make(_ shell: ShellState, _ store: DevelopmentStore, _ checks: DevelopmentChecks,
                      activate: @escaping () -> Void = {}) -> DevelopmentAccountHost {
        DevelopmentAccountHost(shell: shell, choices: [.init(id: "A", label: "A"), .init(id: "B", label: "B")],
            persistence: store, material: { try SessionMaterial(trustedSDKBytes: Data($0.utf8)) },
            verify: { await checks.check($0) }, activate: { _, _, _ in activate() }, invalidate: {})
    }

    @Test func lateLoginCannotReplaceSwitchedIdentityOrRevivePrivateUI() async throws {
        let shell = try makeShell(), store = DevelopmentStore(), checks = DevelopmentChecks()
        var activations = 0
        let host = make(shell, store, checks) { activations += 1 }
        shell.draft = "private A draft"
        host.signIn("A")
        #expect(shell.draft.isEmpty && shell.memoryPath == [.account])
        await wait { checks.replies.count == 1 }
        host.signIn("B")
        await wait { checks.replies.count == 2 }
        checks.replies[1].resume(returning: .accepted(account: "B"))
        await wait { host.state == .signedIn("B") }
        checks.replies[0].resume(returning: .accepted(account: "A"))
        for _ in 0..<20 { await Task.yield() }
        #expect(host.state == .signedIn("B") && activations == 1)
        #expect(!shell.messageBindingBlocked)
        #expect(store.value?.withBytes { String(data: $0, encoding: .utf8) } == "B")
    }

    @Test func restoreNetworkUnknownPreservesCredentialAndLogoutRejectsLateResult() async throws {
        let shell = try makeShell(), store = DevelopmentStore(), checks = DevelopmentChecks()
        store.value = try SessionMaterial(trustedSDKBytes: Data("A".utf8))
        var activations = 0
        let host = make(shell, store, checks) { activations += 1 }
        host.restore(); await wait { checks.replies.count == 1 }
        checks.replies[0].resume(returning: .networkUnknown)
        await wait { host.state == .networkUnknown }
        #expect(store.value != nil && store.clears == 0 && activations == 0)
        #expect(shell.messageBindingBlocked)
        host.restore(); await wait { checks.replies.count == 2 }
        shell.draft = "private visible content"
        host.signOut()
        #expect(shell.draft.isEmpty && store.value == nil && store.clears == 1)
        checks.replies[1].resume(returning: .accepted(account: "A"))
        for _ in 0..<20 { await Task.yield() }
        #expect(host.state == .signedOut && activations == 0)
        #expect(shell.messageBindingBlocked)
    }

    @Test func foregroundRevalidatesMemoryWithoutAutomaticKeychainRestore() async throws {
        let shell = try makeShell(), store = DevelopmentStore(), checks = DevelopmentChecks()
        let host = make(shell, store, checks)
        host.resume()
        #expect(store.loads == 0 && checks.replies.isEmpty)
        host.signIn("A"); await wait { checks.replies.count == 1 }
        checks.replies[0].resume(returning: .accepted(account: "A"))
        await wait { host.state == .signedIn("A") }
        shell.draft = "private content"
        host.suspend()
        #expect(host.state == .paused && shell.draft.isEmpty && store.clears == 0)
        host.resume(); await wait { checks.replies.count == 2 }
        #expect(store.loads == 0)
        checks.replies[1].resume(returning: .networkUnknown)
        await wait { host.state == .networkUnknown }
        #expect(store.value != nil && store.clears == 0)
    }
}
