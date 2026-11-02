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

    @Test func onlyServerRejectionEntersDeviceContextAndCanonicalClearDoesNotCancelItsReceiptTask() async throws {
        let shell = try makeShell(), store = DevelopmentStore(), checks = DevelopmentChecks()
        store.value = try SessionMaterial(trustedSDKBytes: Data("original-a".utf8))
        var contexts = 0, completed = false
        var host: DevelopmentAccountHost!
        host = DevelopmentAccountHost(shell: shell, choices: [.init(id: "A", label: "A")], persistence: store,
            material: { _ in try SessionMaterial(trustedSDKBytes: Data("original-a".utf8)) },
            verify: { await checks.check($0) }, activate: { _,_,_ in }, invalidate: {},
            rejectedContext: { material, session, operation in
                #expect(session.isCurrent(operation))
                #expect(material.withBytes { $0 } == Data("original-a".utf8))
                contexts += 1; try host.clearForAccountCleanup()
                await Task.yield()
                #expect(!Task.isCancelled)
                completed = true
            })
        for result in [DevelopmentSessionCheck.networkUnknown, .expired, .rejected] {
            let index = checks.replies.count
            host.restore(); await wait { checks.replies.count == index + 1 }
            checks.replies[index].resume(returning: result)
            await wait { host.state != .checking }
            #expect(contexts == 0 && !store.blocked)
        }
        host.restore(); await wait { checks.replies.count == 4 }
        checks.replies[3].resume(returning: .serverRejected)
        await wait { completed }
        #expect(contexts == 1 && store.blocked && host.state == .signedOut)
    }
    @Test func cleanupClearsCanonicalSDKAndCannotResumeRetainedActiveMaterial() async throws {
        let shell = try makeShell(), store = DevelopmentStore(), checks = DevelopmentChecks()
        var changes = 0, activations = 0
        let host = DevelopmentAccountHost(shell: shell, choices: [.init(id: "A", label: "A")], persistence: store,
            material: { try SessionMaterial(trustedSDKBytes: Data($0.utf8)) }, verify: { await checks.check($0) },
            activate: { _,_,_ in activations += 1 }, invalidate: {}, identityWillChange: { changes += 1 })
        host.signIn("A"); await wait { checks.replies.count == 1 }
        checks.replies[0].resume(returning: .accepted(account: "A")); await wait { host.state == .signedIn("A") }
        try host.clearForAccountCleanup()
        #expect(store.blocked && store.value == nil && host.state == .signedOut && shell.messageBindingBlocked)
        #expect(changes == 1) // The original restricted workflow is retained.
        host.suspend(); host.resume()
        for _ in 0..<20 { await Task.yield() }
        #expect(checks.replies.count == 1 && activations == 1)
        host.signOut(); #expect(changes == 2)
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
    @Test func offlineCleanupOnlyOnDepartureAndExplicitServerRejection() async throws {
        let shell = try makeShell(), store = DevelopmentStore(), checks = DevelopmentChecks()
        var localClears = 0, denials = 0
        let host = DevelopmentAccountHost(shell: shell, choices: [.init(id: "A", label: "A"), .init(id: "B", label: "B")],
            persistence: store, material: { try SessionMaterial(trustedSDKBytes: Data($0.utf8)) },
            verify: { await checks.check($0) }, activate: { _, _, _ in }, invalidate: {},
            clearOffline: { localClears += 1 }, serverRejected: { _ in denials += 1 })
        host.signIn("A"); await wait { checks.replies.count == 1 }
        checks.replies[0].resume(returning: .accepted(account: "A")); await wait { host.state == .signedIn("A") }
        #expect(localClears == 1)
        for result in [DevelopmentSessionCheck.networkUnknown, .expired, .rejected] {
            let index = checks.replies.count
            host.restore(); await wait { checks.replies.count == index + 1 }
            checks.replies[index].resume(returning: result)
            await wait { host.state != .checking }
            #expect(localClears == 1 && denials == 0 && store.value != nil)
        }
        let index = checks.replies.count
        host.restore(); await wait { checks.replies.count == index + 1 }
        checks.replies[index].resume(returning: .serverRejected); await wait { host.state == .rejected }
        #expect(denials == 1 && localClears == 1)
        host.signIn("B"); await wait { checks.replies.count == index + 2 }
        #expect(localClears == 2 && store.blocked)
        checks.replies[index + 1].resume(returning: .accepted(account: "B")); await wait { host.state == .signedIn("B") }
        host.signOut()
        #expect(localClears == 3 && store.blocked && host.state == .signedOut)
    }
    @Test func lateRejectionCannotClearTheNewAccountCache() async throws {
        let shell = try makeShell(), store = DevelopmentStore(), checks = DevelopmentChecks()
        var denials = 0
        let host = DevelopmentAccountHost(shell: shell, choices: [.init(id: "A", label: "A"), .init(id: "B", label: "B")],
            persistence: store, material: { try SessionMaterial(trustedSDKBytes: Data($0.utf8)) },
            verify: { await checks.check($0) }, activate: { _, _, _ in }, invalidate: {},
            clearOffline: {}, serverRejected: { _ in denials += 1 })
        host.signIn("A"); await wait { checks.replies.count == 1 }
        host.signIn("B"); await wait { checks.replies.count == 2 }
        checks.replies[1].resume(returning: .accepted(account: "B")); await wait { host.state == .signedIn("B") }
        checks.replies[0].resume(returning: .serverRejected)
        for _ in 0..<30 { await Task.yield() }
        #expect(denials == 0 && host.state == .signedIn("B"))
    }

}
