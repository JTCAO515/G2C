import Testing
@testable import CJAuth

/// Explicit synthetic adapter; never ships in the library product.
@MainActor private final class FixtureAdapter: AuthSDKAdapter {
    var unavailable: UnavailableReason?
    var calls = 0
    var continuation: CheckedContinuation<SDKEvent, Never>?
    func unavailableReason(for action: AuthAction) -> UnavailableReason? { unavailable }
    func perform(_ attempt: AuthAttempt) async -> SDKEvent {
        calls += 1
        return await withCheckedContinuation { continuation = $0 }
    }
}

@Suite @MainActor struct AuthFlowTests {
    @Test func everyEntryFailsExplicitlyWithoutConfiguration() async {
        let flow = AuthFlow()
        for action in AuthAction.allCases {
            await flow.run(action, using: UnconfiguredSDKAdapter())
            #expect(flow.state == .unavailable(.missingConfiguration))
            #expect(flow.pending == nil && !flow.canUseRestrictedBusiness)
        }
    }

    @Test func unavailableNeverInvokesAdapter() async {
        let adapter = FixtureAdapter(); adapter.unavailable = .sdkAdapterNotInstalled
        let flow = AuthFlow(); await flow.run(.googleSignIn, using: adapter)
        #expect(adapter.calls == 0)
        #expect(flow.state == .unavailable(.sdkAdapterNotInstalled))
    }

    @Test func cancelledLateAndDuplicateCallbacksCannotMutate() throws {
        let flow = AuthFlow(); let adapter = FixtureAdapter()
        let old = try #require(flow.begin(.appleSignIn, using: adapter))
        #expect(flow.cancel(old))
        #expect(!flow.accept(.identityNeedsServerCheck, purpose: .signIn, for: old))
        #expect(flow.state == .cancelledLocally)
        let next = try #require(flow.begin(.emailSignIn, using: adapter))
        #expect(flow.accept(.identityNeedsServerCheck, purpose: .signIn, for: next))
        #expect(!flow.accept(.rejected, purpose: .signIn, for: next))
        #expect(flow.state == .identityNeedsServerCheck && !flow.canUseRestrictedBusiness)
    }

    @Test func purposeConfusionCannotSignInThroughRecovery() throws {
        let flow = AuthFlow(); let adapter = FixtureAdapter()
        let recovery = try #require(flow.begin(.emailRecovery, using: adapter))
        #expect(!flow.accept(.identityNeedsServerCheck, purpose: .signIn, for: recovery))
        #expect(flow.state == .callbackPurposeMismatch)
        let reset = try #require(flow.begin(.emailReset, using: adapter))
        #expect(!flow.accept(.identityNeedsServerCheck, purpose: .resetPassword, for: reset))
        #expect(!flow.canUseRestrictedBusiness)
    }

    @Test func supersededProviderAndOtherInstanceCannotWrite() throws {
        let flow = AuthFlow(); let adapter = FixtureAdapter(); let other = AuthFlow()
        let google = try #require(flow.begin(.googleSignIn, using: adapter))
        let apple = try #require(flow.begin(.appleSignIn, using: adapter))
        #expect(!flow.cancel(google))
        #expect(!flow.accept(.identityNeedsServerCheck, purpose: .signIn, for: google))
        #expect(!other.accept(.identityNeedsServerCheck, purpose: .signIn, for: apple))
        #expect(flow.pending == apple)
    }

    @Test func identityInvalidationRejectsPriorLifetime() throws {
        let flow = AuthFlow(); let adapter = FixtureAdapter()
        let old = try #require(flow.begin(.emailVerify, using: adapter))
        flow.invalidateIdentity()
        let current = try #require(flow.begin(.emailVerify, using: adapter))
        #expect(old != current)
        #expect(!flow.accept(.identityNeedsServerCheck, purpose: .verifyEmail, for: old))
        #expect(flow.accept(.identityNeedsServerCheck, purpose: .verifyEmail, for: current))
    }

    @Test func emailOutcomesRemainDistinctAndNeverAuthorize() throws {
        let samples: [(AuthAction, SDKEvent, FlowState)] = [
            (.emailRegister, .verificationPending, .verificationPending),
            (.emailRecovery, .recoveryRequestAcknowledged, .recoveryRequestAcknowledged),
            (.emailReset, .passwordUpdatedRequiresSignIn, .passwordUpdatedRequiresSignIn),
            (.emailSignIn, .networkUnknown, .networkUnknown),
            (.emailSignIn, .rejected, .rejected),
            (.emailSignIn, .userCancelled, .cancelledLocally)]
        let flow = AuthFlow(); let adapter = FixtureAdapter()
        for (action, event, expected) in samples {
            let attempt = try #require(flow.begin(action, using: adapter))
            #expect(flow.accept(event, purpose: action.purpose, for: attempt))
            #expect(flow.state == expected && !flow.canUseRestrictedBusiness)
        }
    }

    @Test func actualSuspensionThenSwitchDropsLateCompletion() async throws {
        let flow = AuthFlow(); let adapter = FixtureAdapter()
        let task = Task { await flow.run(.googleSignIn, using: adapter) }
        // Yield only until the synthetic adapter reaches its controlled suspension.
        while adapter.continuation == nil { await Task.yield() }
        let continuation = try #require(adapter.continuation)
        flow.invalidateIdentity()
        let next = try #require(flow.begin(.appleSignIn, using: adapter))
        continuation.resume(returning: .identityNeedsServerCheck)
        await task.value
        #expect(flow.pending == next && flow.state == .waiting(.appleSignIn))
    }
}
