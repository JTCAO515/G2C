import Foundation
import Testing
import CJAuth
@testable import CJAuthSupabase

private actor Capture {
    var requests: [URLRequest] = []
    var hold = false
    var gate: CheckedContinuation<Void, Never>?
    func setHold() { hold = true }
    func release() { gate?.resume(); gate = nil }
    var waiting: Bool { gate != nil }
    func fetch(_ request: URLRequest) async throws -> (Data, URLResponse) {
        requests.append(request)
        if hold { await withCheckedContinuation { gate = $0 } }
        let recovering = request.url?.path.hasSuffix("/recover") == true
        let status = recovering ? 200 : 400
        let body = recovering ? "{}" : "{\"msg\":\"synthetic rejection\",\"code\":\"test_rejection\"}"
        return (Data(body.utf8), HTTPURLResponse(url: request.url!, statusCode: status,
                    httpVersion: nil, headerFields: ["Content-Type": "application/json", "X-Supabase-Api-Version": "2024-01-01"])!)
    }
}

@Suite @MainActor struct SupabaseSDKAdapterTests {
    // Reserved .invalid domain; no transport in this suite calls a socket/URLSession.
    let config = SupabaseAdapterConfiguration(authURL: URL(string: "https://synthetic.invalid/auth/v1"),
        publicKey: "sb_publishable_SYNTHETIC_NOT_A_KEY", emailRedirect: URL(string: "https://synthetic.invalid/email"),
        googleClientID: "synthetic-google", appleClientID: "synthetic-apple")

    private func adapter(_ flow: AuthFlow, _ capture: Capture,
                 configuration: SupabaseAdapterConfiguration? = nil) -> SupabaseSDKAdapter {
        SupabaseSDKAdapter(configuration: configuration ?? config, fetch: { try await capture.fetch($0) },
            isCurrent: { flow.pending == $0 }, material: { attempt in
                if attempt.action == .googleSignIn || attempt.action == .appleSignIn {
                    return .native(attempt: attempt, provider: attempt.action.provider,
                        clientID: attempt.action == .googleSignIn ? "synthetic-google" : "synthetic-apple",
                        idToken: "SYNTHETIC_NOT_A_TOKEN", nonce: "SYNTHETIC_NOT_A_NONCE", accessToken: nil)
                }
                return .email(attempt: attempt, address: "synthetic@example.invalid", password: "SYNTHETIC_NOT_A_PASSWORD")
            })
    }

    @Test func missingConfigurationAndCallbacksNeverReachSDKTransport() async {
        let flow = AuthFlow(); let capture = Capture()
        for action in AuthAction.allCases {
            await flow.run(action, using: adapter(flow, capture, configuration: .init()))
            #expect(flow.state == .unavailable(.missingConfiguration))
        }
        for action in [AuthAction.emailVerify, .emailReset] {
            await flow.run(action, using: adapter(flow, capture))
            #expect(flow.state == .unavailable(.hostCapabilityRequired))
        }
        #expect(await capture.requests.isEmpty)
    }

    @Test func officialSDKBuildsEmailRequestsAndRecoveryAcknowledgement() async throws {
        let flow = AuthFlow(); let capture = Capture(); let a = adapter(flow, capture)
        for action in [AuthAction.emailSignIn, .emailRegister, .emailRecovery] { await flow.run(action, using: a) }
        let requests = await capture.requests
        #expect(requests.count == 3)
        #expect(requests.map { $0.url?.path } == ["/auth/v1/token", "/auth/v1/signup", "/auth/v1/recover"])
        #expect(requests.allSatisfy { $0.httpMethod == "POST" })
        #expect(requests[0].url?.query == "grant_type=password")
        let bytes = try #require(requests[0].httpBody)
        let body = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        #expect(body["email"] as? String == "synthetic@example.invalid")
        #expect(body["password"] as? String == "SYNTHETIC_NOT_A_PASSWORD")
        #expect(requests[1].url?.query?.contains("redirect_to=") == true)
        #expect(flow.state == .recoveryRequestAcknowledged && !flow.canUseRestrictedBusiness)
    }

    @Test func officialSDKBuildsGoogleAppleExchangesButNeverRealOAuth() async throws {
        let flow = AuthFlow(); let capture = Capture(); let a = adapter(flow, capture)
        for action in [AuthAction.googleSignIn, .appleSignIn] { await flow.run(action, using: a) }
        let requests = await capture.requests
        #expect(requests.count == 2)
        for (index, provider) in ["google", "apple"].enumerated() {
            #expect(requests[index].url?.query == "grant_type=id_token")
            let bytes = try #require(requests[index].httpBody)
            let body = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
            #expect(body["provider"] as? String == provider)
            #expect(body["nonce"] as? String == "SYNTHETIC_NOT_A_NONCE")
        }
        #expect(flow.state == .rejected && !flow.canUseRestrictedBusiness)
    }

    @Test func missingNonceOrWrongAttemptMaterialSendsNothing() async throws {
        let flow = AuthFlow(); let capture = Capture()
        var old: AuthAttempt?
        let a = SupabaseSDKAdapter(configuration: config, fetch: { try await capture.fetch($0) },
            isCurrent: { flow.pending == $0 }, material: { attempt in
                .native(attempt: old ?? attempt, provider: .google, clientID: "synthetic-google",
                        idToken: "SYNTHETIC_NOT_A_TOKEN", nonce: old == nil ? "" : "synthetic", accessToken: nil)
            })
        let original = try #require(flow.begin(.googleSignIn, using: a))
        old = original
        #expect(flow.cancel(original))
        await flow.run(.googleSignIn, using: a)
        #expect(flow.state == .unavailable(.missingRuntimeMaterial))
        old = nil
        await flow.run(.googleSignIn, using: a)
        #expect(flow.state == .unavailable(.missingRuntimeMaterial))
        #expect(await capture.requests.isEmpty)
    }

    @Test func nativeProviderAndClientIDMustMatchOriginalAttempt() async {
        for wrongProvider in [true, false] {
            let flow = AuthFlow(); let capture = Capture()
            let a = SupabaseSDKAdapter(configuration: config, fetch: { try await capture.fetch($0) },
                isCurrent: { flow.pending == $0 }, material: { attempt in
                    .native(attempt: attempt, provider: wrongProvider ? .apple : .google,
                        clientID: wrongProvider ? "synthetic-google" : "wrong-client",
                        idToken: "SYNTHETIC_NOT_A_TOKEN", nonce: "synthetic", accessToken: nil)
                })
            await flow.run(.googleSignIn, using: a)
            #expect(flow.state == .unavailable(.missingRuntimeMaterial))
            #expect(await capture.requests.isEmpty)
        }
    }

    @Test func cancelledDuringMaterialAcquisitionSendsNothing() async {
        let flow = AuthFlow(); let capture = Capture()
        let a = SupabaseSDKAdapter(configuration: config, fetch: { try await capture.fetch($0) },
            isCurrent: { flow.pending == $0 }, material: { attempt in
                flow.cancel(attempt)
                return .email(attempt: attempt, address: "synthetic@example.invalid", password: "synthetic")
            })
        await flow.run(.emailSignIn, using: a)
        #expect(flow.state == .cancelledLocally)
        #expect(await capture.requests.isEmpty)
    }

    @Test func networkUnknownAndDefaultTransportNeverGrantAccess() async {
        let flow = AuthFlow()
        let a = SupabaseSDKAdapter(configuration: config, isCurrent: { flow.pending == $0 }, material: {
            .email(attempt: $0, address: "synthetic@example.invalid", password: "synthetic")
        })
        await flow.run(.emailSignIn, using: a) // default fetch throws, never URLSession
        #expect(flow.state == .networkUnknown && !flow.canUseRestrictedBusiness)
    }

    @Test func cancelledSDKResponseCannotOverwriteNewAttempt() async throws {
        let flow = AuthFlow(); let capture = Capture(); await capture.setHold()
        let a = adapter(flow, capture)
        let task = Task { await flow.run(.emailRecovery, using: a) }
        while !(await capture.waiting) { await Task.yield() }
        flow.invalidateIdentity()
        let current = try #require(flow.begin(.googleSignIn, using: a))
        await capture.release(); await task.value
        #expect(flow.pending == current && flow.state == .waiting(.googleSignIn))
    }

    @Test func unverifiedEmailIsNotGenericRejection() async {
        let flow = AuthFlow()
        let a = SupabaseSDKAdapter(configuration: config, fetch: { request in
            (Data("{\"msg\":\"synthetic\",\"code\":\"email_not_confirmed\"}".utf8),
             HTTPURLResponse(url: request.url!, statusCode: 400, httpVersion: nil,
                             headerFields: ["Content-Type": "application/json", "X-Supabase-Api-Version": "2024-01-01"])!)
        }, isCurrent: { flow.pending == $0 }, material: {
            .email(attempt: $0, address: "synthetic@example.invalid", password: "synthetic")
        })
        await flow.run(.emailSignIn, using: a)
        #expect(flow.state == .emailVerificationRequired && !flow.canUseRestrictedBusiness)
    }

    @Test func sdkAutomaticPostRetryCannotRepeatUnknownWrite() async {
        let flow = AuthFlow(); let counter = RequestCounter()
        let a = SupabaseSDKAdapter(configuration: config, fetch: { request in
            await counter.increment()
            return (Data("{}".utf8), HTTPURLResponse(url: request.url!, statusCode: 503,
                        httpVersion: nil, headerFields: nil)!)
        }, isCurrent: { flow.pending == $0 }, material: {
            .email(attempt: $0, address: "synthetic@example.invalid", password: "synthetic")
        })
        await flow.run(.emailRecovery, using: a)
        #expect(await counter.count == 1)
        #expect(flow.state == .networkUnknown && !flow.canUseRestrictedBusiness)
    }

    @Test func badConfigurationDoesNotFallBack() async {
        let flow = AuthFlow(); let capture = Capture()
        let samples = [SupabaseAdapterConfiguration(authURL: URL(string: "http://synthetic.invalid"), publicKey: "public"),
                       SupabaseAdapterConfiguration(authURL: config.authURL, publicKey: "sb_secret_DO_NOT_USE"),
                       SupabaseAdapterConfiguration(authURL: config.authURL, publicKey: " ")]
        for sample in samples {
            await flow.run(.emailSignIn, using: adapter(flow, capture, configuration: sample))
            #expect(flow.state == .unavailable(.missingConfiguration))
        }
        let noProviders = SupabaseAdapterConfiguration(authURL: config.authURL, publicKey: config.publicKey)
        for action in [AuthAction.googleSignIn, .appleSignIn, .emailRegister, .emailRecovery] {
            await flow.run(action, using: adapter(flow, capture, configuration: noProviders))
            #expect(flow.state == .unavailable(.missingConfiguration))
        }
        #expect(await capture.requests.isEmpty)
    }
}


private actor RequestCounter {
    var count = 0
    func increment() { count += 1 }
}
