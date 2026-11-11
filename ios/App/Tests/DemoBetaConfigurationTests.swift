import Foundation
import Testing
@testable import G2CDevelopmentConfiguration

struct DemoBetaConfigurationTests {
    private let now = Date(timeIntervalSince1970: 1_795_000_000)

    private func reply(subject: String = "m4-synthetic-demo-0123456789ab", tokenOwner: String? = nil,
                       lifetime: TimeInterval = 3600, version: String = "DEMO-invite-session.2") throws -> Data {
        let expiry = now.addingTimeInterval(lifetime)
        let claims: [String: Any] = [
            "sub": tokenOwner ?? subject, "iss": "https://local.g2c.invalid", "aud": "g2c-local",
            "exp": expiry.timeIntervalSince1970,
        ]
        let encoded = try JSONSerialization.data(withJSONObject: claims).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
        let response: [String: Any] = [
            "version": version,
            "access_token": "stub.\(encoded).signature",
            "subject": subject,
            "expires_at": ISO8601DateFormatter().string(from: expiry),
        ]
        return try JSONSerialization.data(withJSONObject: response)
    }

    @Test func inviteRequestIsFixedOriginAndConsentGated() throws {
        let request = try DemoBetaConfiguration.inviteRequest(code: "Opaque-Case_sensitive", consent: true)
        #expect(request.url?.absoluteString == "https://api-beta.go2china.space/v2/demo-invite-sessions")
        #expect(request.httpMethod == "POST")
        #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
        let body = try #require(request.httpBody)
        let json = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(Set(json.keys) == ["version", "invite_code", "consent"])
        #expect(json["invite_code"] as? String == "Opaque-Case_sensitive")
        #expect(json["consent"] as? Bool == true)
        #expect(throws: DemoBetaConfiguration.Failure.invalidInput) {
            try DemoBetaConfiguration.inviteRequest(code: "code", consent: false)
        }
    }

    @Test func fourFieldInviteGrantAndKeychainEnvelopeStaySeparate() throws {
        let grant = try DemoBetaConfiguration.verifyInviteResponse(reply(), status: 200,
            contentType: "application/json; charset=utf-8", now: now)
        #expect(grant.subject == "m4-synthetic-demo-0123456789ab")
        #expect(grant.expiry == now.addingTimeInterval(3600))
        let profile = try DemoCompositionProfile(language: .zh, travelID: "0123456789abcdef0123456789abcdef", travelVersion: 1)
        let encoded = try JSONEncoder().encode(DemoInviteSession(grant: grant, composition: profile))
        let session = try DemoInviteSession.decode(encoded, now: now)
        #expect(session.composition.needs_id == "demo-starter-zh-needs")
        #expect(DemoCompositionProfile.memory.slots["quiet.entrance"]?.collection_allowed == true)
        #expect(!String(reflecting: grant).contains("stub."))
        #expect(Mirror(reflecting: session).children.isEmpty)
        #expect(throws: (any Error).self) { try DemoInviteSession.decode(reply(), now: now) }
    }

    @Test func rejectsOtherOwnerNonDemoExpiredOrOverlongGrant() throws {
        let wrongOwner = try reply(tokenOwner: "other-owner")
        let wrongScope = try reply(subject: "other-owner")
        let tooLong = try reply(lifetime: 604801)
        for body in [wrongOwner, wrongScope, tooLong] {
            #expect(throws: DemoBetaConfiguration.Failure.invalidResponse) { try DemoInviteGrant.decode(body, now: now) }
        }
        let expired = try reply(lifetime: -1)
        #expect(throws: DemoBetaConfiguration.Failure.expired) { try DemoInviteGrant.decode(expired, now: now) }
    }

    @Test func legacyAndSevenDaySessionsKeepSeparateExpiryBounds() throws {
        for (version, maximum) in [("DEMO-invite-session.1", 7200.0), ("DEMO-invite-session.2", 604800.0)] {
            _ = try DemoInviteGrant.decode(reply(lifetime: maximum, version: version), now: now)
            #expect(throws: DemoBetaConfiguration.Failure.invalidResponse) {
                try DemoInviteGrant.decode(reply(lifetime: maximum + 1, version: version), now: now)
            }
        }
        #expect(throws: DemoBetaConfiguration.Failure.invalidResponse) {
            try DemoBetaConfiguration.verifyInviteResponse(reply(version: "DEMO-invite-session.1"),
                status: 200, contentType: "application/json", now: now)
        }
    }

    @Test func renewalOnlyUsesAnUnexpiredBearerWithinOneDayOfExpiry() throws {
        let legacy = try DemoInviteGrant.decode(reply(lifetime: 7200, version: "DEMO-invite-session.1"), now: now)
        let request = try #require(try DemoBetaConfiguration.renewalRequest(grant: legacy, now: now))
        #expect(request.url?.absoluteString == "https://api-beta.go2china.space/v2/demo-session-renewals")
        #expect(request.httpMethod == "POST" && request.value(forHTTPHeaderField: "Authorization") == "Bearer " + legacy.access_token)
        let body = try #require(request.httpBody)
        let fields = try #require(try JSONSerialization.jsonObject(with: body) as? [String: String])
        #expect(fields == ["version": "DEMO-session-renewal.1"])
        let fresh = try DemoInviteGrant.decode(reply(lifetime: 604800), now: now)
        #expect(try DemoBetaConfiguration.renewalRequest(grant: fresh, now: now) == nil)
        #expect(try DemoBetaConfiguration.renewalRequest(grant: fresh, now: now.addingTimeInterval(518400)) != nil)
        #expect(throws: DemoBetaConfiguration.Failure.expired) {
            try DemoBetaConfiguration.renewalRequest(grant: legacy, now: now.addingTimeInterval(7200))
        }
    }

    @Test func renewedGrantPreservesOwnerAndStarterSelectionAndAcceptsTheServerCap() throws {
        let grant = try DemoInviteGrant.decode(reply(version: "DEMO-invite-session.1"), now: now)
        let composition = try DemoCompositionProfile(language: .en, travelID: "0123456789abcdef0123456789abcdef", travelVersion: 3)
        let previous = DemoInviteSession(grant: grant, composition: composition)
        // A qualification expiring sooner than seven days caps the new grant.
        let renewed = try DemoBetaConfiguration.verifyRenewalResponse(reply(lifetime: 1800), status: 200,
            contentType: "application/json", previous: previous, now: now)
        #expect(renewed.grant.subject == grant.subject && renewed.grant.expiry == now.addingTimeInterval(1800))
        #expect(renewed.composition.conversation_id == composition.conversation_id && renewed.composition.needs_id == composition.needs_id)
        #expect(renewed.composition.travel_id == composition.travel_id && renewed.composition.travel_version == composition.travel_version)
        for bytes in [try reply(subject: "m4-synthetic-demo-abcdef012345"), try reply(version: "DEMO-invite-session.1")] {
            #expect(throws: DemoBetaConfiguration.Failure.invalidResponse) {
                try DemoBetaConfiguration.verifyRenewalResponse(bytes, status: 200, contentType: "application/json", previous: previous, now: now)
            }
        }
        for (status, failure) in [(401, DemoBetaConfiguration.Failure.inviteDenied), (503, .unavailable)] {
            let bytes = try JSONSerialization.data(withJSONObject: ["request_id": UUID().uuidString, "error": ["code": "documented-denial"]])
            #expect(throws: failure) {
                try DemoBetaConfiguration.verifyRenewalResponse(bytes, status: status, contentType: "application/json", previous: previous, now: now)
            }
        }
    }

    @Test(arguments: DemoStarterLanguage.allCases)
    func starterReadKeepsNeedsTravelAndConversationInTheSameLocale(_ language: DemoStarterLanguage) throws {
        let requestID = UUID().uuidString
        let conversations = DemoStarterReads.Conversations(request_id: requestID,
            conversations: [.init(conversation_id: language.conversationID, generation: "generation", list_sequence: 1)])
        let needs = DemoStarterReads.Needs(request_id: requestID, needs: .init(needs_id: language.needsID))
        let context = DemoStarterReads.Travel.Receipt.Context(id: "0123456789abcdef0123456789abcdef", version: 1, active: true)
        let travel = DemoStarterReads.Travel(request_id: requestID, receipt: .init(version: "TRAVEL-context-receipt.1",
            action_id: language.travelActionID, operation: "create", travel_context: context))
        let profile = try DemoStarterReads.profile(language: language, conversations: conversations, needs: needs, travel: travel)
        #expect(profile.conversation_id == language.conversationID && profile.travel_id == context.id)
        let other: DemoStarterLanguage = language == .zh ? .en : .zh
        #expect(throws: DemoBetaConfiguration.Failure.invalidResponse) {
            try DemoStarterReads.profile(language: other, conversations: conversations, needs: needs, travel: travel)
        }
        #expect(throws: DemoBetaConfiguration.Failure.invalidResponse) {
            try DemoStarterReads.profile(language: language, conversations: conversations,
                                         needs: .init(request_id: requestID, needs: nil), travel: travel)
        }
    }

    @Test(arguments: [
        (400, "INVALID_INPUT", DemoBetaConfiguration.Failure.invalidInput),
        (401, "DEMO_INVITE_DENIED", DemoBetaConfiguration.Failure.inviteDenied),
        (503, "DEMO_LOGIN_UNAVAILABLE", DemoBetaConfiguration.Failure.unavailable),
        (302, "DEMO_INVITE_DENIED", DemoBetaConfiguration.Failure.invalidResponse),
    ])
    func mapsOnlyDocumentedErrors(status: Int, code: String, error: DemoBetaConfiguration.Failure) throws {
        let body = try JSONSerialization.data(withJSONObject: ["request_id": UUID().uuidString, "error": ["code": code]])
        #expect(throws: error) {
            try DemoBetaConfiguration.verifyInviteResponse(body, status: status, contentType: "application/json", now: now)
        }
    }
}
