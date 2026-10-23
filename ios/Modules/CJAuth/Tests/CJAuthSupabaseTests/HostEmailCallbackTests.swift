import Foundation
import Testing
import CJAuth
import CJAuthSupabase

private actor CallbackRequestCapture {
    var requests: [URLRequest] = []
    func fetch(_ request: URLRequest) -> (Data, URLResponse) {
        requests.append(request)
        return (Data("{}".utf8), HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                    headerFields: ["Content-Type":"application/json"])!)
    }
}
@Suite @MainActor struct HostEmailCallbackTests {
    private func descriptor(_ text: String, _ purpose: EmailCallbackPurpose, _ kind: EmailCallbackKind = .customScheme) throws -> HostEmailCallback {
        let url = try #require(URL(string: text))
        return try HostEmailCallback(exactDestination: url, kind: kind, purpose: purpose)
    }
    private func adapter(_ configuration: SupabaseAdapterConfiguration, _ flow: AuthFlow,
                         capture: CallbackRequestCapture? = nil) -> SupabaseSDKAdapter {
        SupabaseSDKAdapter(configuration: configuration, fetch: { request in
            guard let capture else { throw URLError(.notConnectedToInternet) }
            return await capture.fetch(request)
        }, isCurrent: { flow.pending == $0 }, material: {
            .email(attempt: $0, address: "synthetic@example.invalid", password: "synthetic-not-a-password")
        })
    }
    private func configuration(verification: HostEmailCallback? = nil, recovery: HostEmailCallback? = nil,
                               legacy: URL? = nil, endpoint: URL? = URL(string:"https://synthetic.invalid/auth/v1")) -> SupabaseAdapterConfiguration {
        .init(authURL: endpoint, publicKey: "sb_publishable_SYNTHETIC_NOT_A_KEY", emailRedirect: legacy,
              emailVerificationCallback: verification, passwordRecoveryCallback: recovery)
    }
    @Test func explicitNativeCallbacksUseOnlyHTTPSServiceAndExactDistinctDestinations() async throws {
        let verify = try descriptor("cj-synthetic://auth/verify", .verifyEmail)
        let recover = try descriptor("cj-synthetic://auth/reset", .resetPassword)
        let capture = CallbackRequestCapture(), flow = AuthFlow()
        let a = adapter(configuration(verification: verify, recovery: recover), flow, capture: capture)
        #expect(a.unavailableReason(for: .emailRegister) == nil && a.unavailableReason(for: .emailRecovery) == nil)
        await flow.run(.emailRegister, using: a); await flow.run(.emailRecovery, using: a)
        let requests = await capture.requests
        #expect(requests.count == 2)
        for (request, expected) in zip(requests, [verify.exactDestination, recover.exactDestination]) {
            #expect(request.url?.scheme == "https" && request.url?.host == "synthetic.invalid")
            #expect(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "redirect_to" })?.value == expected)
        }
    }
    @Test func legacyHTTPSAndDefaultOffRemainCompatible() {
        let flow = AuthFlow()
        let legacy = adapter(configuration(legacy: URL(string:"https://synthetic.invalid/email")), flow)
        #expect(legacy.unavailableReason(for: .emailRegister) == nil && legacy.unavailableReason(for: .emailRecovery) == nil)
        let none = adapter(.init(), flow)
        #expect(none.unavailableReason(for: .emailRegister) == .missingConfiguration)
        let rawNative = adapter(configuration(legacy: URL(string:"cj-synthetic://auth/verify")), flow)
        #expect(rawNative.unavailableReason(for: .emailRegister) == .missingConfiguration)
    }
    @Test func legacyHTTPSRedirectPreservesEncodedPathExactly() throws {
        let url = try #require(URL(string: "https://synthetic.invalid/a%20b/verify"))
        let flow = AuthFlow()
        let bound = adapter(configuration(legacy: url), flow)
        #expect(bound.unavailableReason(for: .emailRegister) == nil)
        let attempt = try #require(flow.begin(.emailRegister, using: bound))
        #expect(bound.emailCallbackContext(for: attempt, purpose: .verifyEmail)?.callback.exactDestination == url.absoluteString)
    }
    @Test func explicitHTTPSCallbackIsPurposeSpecificWithoutFallback() throws {
        let descriptor = try descriptor("https://synthetic.invalid/verify", .verifyEmail, .https)
        let flow = AuthFlow(), config = configuration(verification: descriptor)
        let bound = adapter(config, flow)
        let attempt = try #require(flow.begin(.emailRegister, using: bound))
        #expect(bound.emailCallbackContext(for: attempt, purpose: .verifyEmail)?.callback == descriptor)
        #expect(bound.unavailableReason(for: .emailRecovery) == .missingConfiguration)
    }
    @Test func wrongPurposeConflictingSourcesAndNativeServiceEndpointFailClosed() throws {
        let verify = try descriptor("cj-synthetic://auth/verify", .verifyEmail), flow = AuthFlow()
        #expect(adapter(configuration(recovery: verify), flow).unavailableReason(for: .emailRecovery) == .missingConfiguration)
        #expect(adapter(configuration(verification: verify, legacy: URL(string:"https://synthetic.invalid/email")), flow).unavailableReason(for: .emailRegister) == .missingConfiguration)
        #expect(adapter(configuration(verification: verify, endpoint: URL(string:"cj-synthetic://auth/service")), flow).unavailableReason(for: .emailRegister) == .missingConfiguration)
    }
    @Test func malformedWildcardEncodedAndReservedCallbacksAreRejected() throws {
        for value in ["http://synthetic.invalid/verify", "file://auth/verify", "cj-synthetic://u:p@auth/verify",
                      "cj-synthetic://auth/verify?code=synthetic", "cj-synthetic://auth/verify#token", "cj-synthetic://*/verify",
                      "cj-synthetic://auth/a/../verify", "cj-synthetic://auth/%76erify", "cj-synthetic://auth:123/verify"] {
            #expect(throws: EmailCallbackConfigurationFailure.invalidDestination) { try descriptor(value, .verifyEmail) }
        }
        #expect(throws: EmailCallbackConfigurationFailure.invalidDestination) { try descriptor("cj-synthetic://auth/verify", .verifyEmail, .https) }
        #expect(throws: EmailCallbackConfigurationFailure.invalidDestination) { try descriptor("https://synthetic.invalid/verify", .verifyEmail, .customScheme) }
    }
    @Test func callbackContextRequiresOriginalPurposeAttemptAndAdapter() throws {
        let verify = try descriptor("cj-synthetic://auth/verify", .verifyEmail), flow = AuthFlow()
        let config = configuration(verification: verify)
        let a = adapter(config, flow), other = adapter(config, flow)
        let original = try #require(flow.begin(.emailRegister, using: a))
        let value = try #require(a.emailCallbackContext(for: original, purpose: .verifyEmail))
        #expect(value.callback.exactDestination == verify.exactDestination && a.isEmailCallbackContextCurrent(value))
        #expect(a.emailCallbackContext(for: original, purpose: .resetPassword) == nil)
        #expect(!other.isEmailCallbackContextCurrent(value))
        flow.invalidateIdentity()
        #expect(!a.isEmailCallbackContextCurrent(value))
        let next = try #require(flow.begin(.emailRegister, using: a))
        #expect(a.emailCallbackContext(for: next, purpose: .verifyEmail) != nil)
        #expect(a.emailCallbackContext(for: original, purpose: .verifyEmail) == nil)
    }
    @Test func configuredRouteDoesNotEnableVerificationResetOrLongLivedCallback() throws {
        let flow = AuthFlow()
        let a = adapter(configuration(verification: try descriptor("cj-synthetic://auth/verify", .verifyEmail),
                                      recovery: try descriptor("cj-synthetic://auth/reset", .resetPassword)), flow)
        #expect(a.unavailableReason(for: .emailVerify) == .hostCapabilityRequired)
        #expect(a.unavailableReason(for: .emailReset) == .hostCapabilityRequired)
        let original = try #require(flow.begin(.emailRegister, using: a))
        let context = try #require(a.emailCallbackContext(for: original, purpose: .verifyEmail))
        #expect(flow.accept(.verificationPending, purpose: .register, for: original))
        #expect(!a.isEmailCallbackContextCurrent(context) && !flow.canUseRestrictedBusiness)
    }
}
