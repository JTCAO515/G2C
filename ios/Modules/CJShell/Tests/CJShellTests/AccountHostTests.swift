import Foundation
import Testing
import CJAuth
@testable import CJShell

@MainActor private final class ControlledAdapter: AuthSDKAdapter {
    var calls = 0
    var materialConsumed = false
    var passwordPresent = false
    var repeatedTakeWasNil = false
    var attempts: [AuthAttempt] = []
    var replies: [CheckedContinuation<SDKEvent, Never>] = []
    let channel: AccountMaterialChannel
    init(_ channel: AccountMaterialChannel) { self.channel = channel }
    func unavailableReason(for action: AuthAction) -> UnavailableReason? { nil }
    func perform(_ attempt: AuthAttempt) async -> SDKEvent {
        calls += 1
        attempts.append(attempt)
        if let material = channel.take(for: attempt) {
            materialConsumed = true
            passwordPresent = material.password?.isEmpty == false
        }
        repeatedTakeWasNil = channel.take(for: attempt) == nil
        return await withCheckedContinuation { replies.append($0) }
    }
    func reply(_ event: SDKEvent) { replies.removeFirst().resume(returning: event) }
}

@Suite @MainActor struct AccountHostTests {
    private func shell() throws -> ShellState {
        ShellState(preferences: try #require(UserDefaults(suiteName: "cj006.host.tests.\(UUID().uuidString)")))
    }
    private func wait(_ condition: () -> Bool) async {
        for _ in 0..<1000 { if condition() { return }; await Task.yield() }
        #expect(condition(), "Controlled local task did not reach expected state")
    }
    private func fixture(_ shell: ShellState) -> (AccountHost, ControlledAdapter) {
        var controlled: ControlledAdapter?
        let host = AccountHost(shell: shell) { channel, _ in
            let adapter = ControlledAdapter(channel); controlled = adapter; return adapter
        }
        return (host, controlled!) // factory is synchronous and always assigns
    }

    @Test func defaultUnavailableDoesNotInvalidateOrDispatch() throws {
        let shell = try shell()
        shell.draft = "retained private draft"
        let generation = shell.generation
        let host = AccountHost(shell: shell)
        for action in [AuthAction.emailSignIn, .emailRegister, .emailRecovery, .googleSignIn, .appleSignIn] {
            var secret = "synthetic-only"
            host.submit(action, email: "fixture@example.invalid", password: &secret)
            #expect(secret.isEmpty)
            #expect(host.state == .unavailable(.missingConfiguration))
        }
        #expect(shell.generation == generation && shell.draft == "retained private draft")
        #expect(!host.canUseRestrictedBusiness)
    }

    @Test func signInClearsPrivateProjectionAndConsumesMaterialOnce() async throws {
        let shell = try shell()
        shell.draft = "old private draft"
        shell.memoryPath = [.group(.facts)]
        shell.apply(ShellPresentation(context: ShellContext(conversationReference: "old-chat"), assistantBody: "old body"), for: shell.generation)
        let old = shell.generation
        let (host, adapter) = fixture(shell)
        var secret = "synthetic-only"
        host.submit(.emailSignIn, email: "fixture@example.invalid", password: &secret)
        #expect(secret.isEmpty)
        #expect(shell.generation != old && shell.draft.isEmpty)
        #expect(shell.presentation == ShellPresentation() && shell.memoryPath == [.account])
        await wait { adapter.calls == 1 }
        #expect(adapter.materialConsumed && adapter.passwordPresent && adapter.repeatedTakeWasNil)
        adapter.reply(.identityNeedsServerCheck)
        await wait { host.state == .identityNeedsServerCheck }
        #expect(!host.canUseRestrictedBusiness)
    }

    @Test func languageDuringWaitingPreservesAttemptAndCurrentDraft() async throws {
        let shell = try shell()
        let (host, adapter) = fixture(shell)
        var secret = "synthetic-only"
        host.submit(.emailSignIn, email: "fixture@example.invalid", password: &secret)
        await wait { adapter.calls == 1 }
        let generation = shell.generation
        shell.draft = "current unsent draft"
        shell.selectLanguage(.chinese)
        #expect(shell.generation == generation && shell.draft == "current unsent draft")
        #expect(host.state == .waiting(.emailSignIn) && adapter.calls == 1)
        adapter.reply(.rejected)
        await wait { host.state == .rejected }
    }

    @Test func unknownAndReentryNeverCreateReplacementAttempt() async throws {
        let shell = try shell()
        let (host, adapter) = fixture(shell)
        var secret = "synthetic-only"
        host.submit(.emailRegister, email: "fixture@example.invalid", password: &secret)
        await wait { adapter.calls == 1 }
        host.submit(.emailRegister, email: "fixture@example.invalid", password: &secret)
        #expect(adapter.calls == 1)
        adapter.reply(.networkUnknown)
        await wait { host.requiresReconciliation }
        let generation = shell.generation
        host.submit(.googleSignIn, password: &secret)
        #expect(adapter.calls == 1 && shell.generation == generation)
        #expect(host.state == .networkUnknown)
        host.invalidateIdentity()
        host.submit(.appleSignIn, password: &secret)
        #expect(host.requiresReconciliation && adapter.calls == 1)
    }

    @Test func cancelledAndIdentityChangedLateResultsCannotRepopulate() async throws {
        let shell = try shell()
        let (host, adapter) = fixture(shell)
        var secret = "synthetic-only"
        host.submit(.emailSignIn, email: "fixture@example.invalid", password: &secret)
        await wait { adapter.calls == 1 }
        host.cancel()
        #expect(host.state == .cancelledLocally && host.requiresReconciliation)
        host.invalidateIdentity()
        let clean = shell.generation
        adapter.reply(.identityNeedsServerCheck)
        for _ in 0..<10 { await Task.yield() }
        #expect(host.state == .idle && shell.generation == clean)
        #expect(shell.draft.isEmpty && shell.memoryPath.isEmpty && shell.presentation == ShellPresentation())
        #expect(!host.canUseRestrictedBusiness)
    }

    @Test func recoveryDoesNotBecomeLoginOrClearDraft() async throws {
        let shell = try shell()
        shell.draft = "keep"
        let generation = shell.generation
        let (host, adapter) = fixture(shell)
        var secret = "synthetic-not-needed"
        host.submit(.emailRecovery, email: "fixture@example.invalid", password: &secret)
        await wait { adapter.calls == 1 }
        #expect(!adapter.passwordPresent && secret.isEmpty)
        adapter.reply(.recoveryRequestAcknowledged)
        await wait { host.state == .recoveryRequestAcknowledged }
        #expect(shell.generation == generation && shell.draft == "keep")
        #expect(!host.canUseRestrictedBusiness)
    }
}
