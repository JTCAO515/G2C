import Foundation

/// The signed Beta has one origin. Invite responses never choose an endpoint.
enum DemoBetaConfiguration {
    static let endpoint = URL(string: "https://api-beta.go2china.space")!
    static let bundleID = "space.go2china.app"
    static let inviteVersion = "DEMO-invite-session.1"
    static let invitePath = "/v1/demo-invite-sessions"
    static let maximumSessionDuration: TimeInterval = 2 * 60 * 60

    enum Failure: Error, Equatable {
        case invalidInput, inviteDenied, unavailable, invalidResponse, expired
    }

    static func inviteRequest(code: String, consent: Bool) throws -> URLRequest {
        var request = URLRequest(url: endpoint.appending(path: invitePath))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try JSONEncoder().encode(InviteRequest(code: code, consent: consent))
        return request
    }

    static func verifyInviteResponse(_ bytes: Data, status: Int, contentType: String?, now: Date) throws -> DemoInviteGrant {
        guard bytes.count <= 65536, contentType?.split(separator: ";").first?.lowercased() == "application/json" else {
            throw Failure.invalidResponse
        }
        if status == 200 { return try DemoInviteGrant.decode(bytes, now: now) }
        struct Envelope: Decodable {
            struct Detail: Decodable { let code: String }
            let request_id: String
            let error: Detail
        }
        guard let envelope = try? JSONDecoder().decode(Envelope.self, from: bytes),
              UUID(uuidString: envelope.request_id) != nil else { throw Failure.invalidResponse }
        switch (status, envelope.error.code) {
        case (401, "DEMO_INVITE_DENIED"): throw Failure.inviteDenied
        case (400, "INVALID_INPUT"): throw Failure.invalidInput
        case (503, "DEMO_LOGIN_UNAVAILABLE"): throw Failure.unavailable
        default: throw Failure.invalidResponse
        }
    }

    struct InviteRequest: Encodable {
        let version = inviteVersion
        let invite_code: String
        let consent: Bool

        init(code: String, consent: Bool) throws {
            guard consent, !code.isEmpty, code.utf8.count <= 512,
                  code.unicodeScalars.allSatisfy({ !CharacterSet.controlCharacters.contains($0) }) else { throw Failure.invalidInput }
            invite_code = code
            self.consent = consent
        }
    }
}

/// These are server-provisioned selections for one verified owner. They confer
/// no access by themselves; the frozen business endpoints verify each request.
struct DemoCompositionProfile: Codable {
    let conversation_id: String
    let needs_id: String
    let travel_id: String
    let travel_version: Int

    init(language: DemoStarterLanguage, travelID: String, travelVersion: Int) throws {
        conversation_id = language.conversationID
        needs_id = language.needsID
        travel_id = travelID
        travel_version = travelVersion
        try validate()
    }

    func validate() throws {
        guard DemoStarterLanguage.allCases.contains(where: {
            $0.conversationID == conversation_id && $0.needsID == needs_id
        }), travel_version > 0, travel_id.utf8.count == 32,
           travel_id.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else {
            throw DemoBetaConfiguration.Failure.invalidResponse
        }
    }

    static let memory = DevelopmentTypedMemoryProfile(version: "app-memory.2", subjects: ["self"],
        slots: ["quiet.entrance": .init(kind: "preference", collection_allowed: true, semantic_resolved: true)],
        extents: ["long_term"])
}

enum DemoStarterLanguage: String, CaseIterable {
    case zh, en

    var conversationID: String { "demo-starter-" + rawValue }
    var needsID: String { conversationID + "-needs" }
    var travelActionID: String { conversationID + "-travel" }
}

enum DemoStarterReads {
    struct Conversations: Decodable {
        struct Conversation: Decodable {
            let conversation_id: String
            let generation: String
            let list_sequence: Int64
        }
        let request_id: String
        let conversations: [Conversation]
    }
    struct Needs: Decodable {
        struct Snapshot: Decodable { let needs_id: String }
        let request_id: String
        let needs: Snapshot?
    }
    struct Travel: Decodable {
        struct Receipt: Decodable {
            struct Context: Decodable { let id: String; let version: Int; let active: Bool }
            let version: String
            let action_id: String
            let operation: String
            let travel_context: Context
        }
        let request_id: String
        let receipt: Receipt?
    }

    static func profile(language: DemoStarterLanguage, conversations: Conversations, needs: Needs, travel: Travel) throws -> DemoCompositionProfile {
        let matches = conversations.conversations.filter { $0.conversation_id == language.conversationID }
        guard conversations.conversations.count <= 20, matches.count == 1,
              let starter = matches.first, !starter.generation.isEmpty, starter.list_sequence > 0,
              needs.needs?.needs_id == language.needsID,
              let receipt = travel.receipt, receipt.version == "TRAVEL-context-receipt.1",
              receipt.action_id == language.travelActionID, receipt.operation == "create",
              receipt.travel_context.active else { throw DemoBetaConfiguration.Failure.invalidResponse }
        return try .init(language: language, travelID: receipt.travel_context.id, travelVersion: receipt.travel_context.version)
    }
}

/// The invite exchange has four fields. Protected business reads verify the
/// bearer and supply the separate, owner-scoped starter data.
struct DemoInviteGrant: Codable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let version: String
    let access_token: String
    let subject: String
    let expires_at: String

    var description: String { "<redacted demo invite grant>" }
    var debugDescription: String { description }
    var customMirror: Mirror { Mirror(self, children: [:]) }

    static func decode(_ bytes: Data, now: Date) throws -> Self {
        let value: Self
        do { value = try JSONDecoder().decode(Self.self, from: bytes) }
        catch { throw DemoBetaConfiguration.Failure.invalidResponse }
        try value.validate(now: now)
        return value
    }

    func validate(now: Date? = nil) throws {
        let prefix = "m4-synthetic-demo-"
        let identifier = subject.utf8.dropFirst(prefix.utf8.count)
        guard version == DemoBetaConfiguration.inviteVersion, subject.hasPrefix(prefix), identifier.count == 12,
              identifier.allSatisfy({ (48...57).contains($0) || (97...122).contains($0) }),
              let claims = DevelopmentBearerClaims.read(access_token),
              claims.subject == subject, let expiration = claims.expiration, let expiry,
              abs(expiry.timeIntervalSince1970 - expiration) < 1 else {
            throw DemoBetaConfiguration.Failure.invalidResponse
        }
        if let now {
            guard expiry.timeIntervalSince(now) <= DemoBetaConfiguration.maximumSessionDuration else {
                throw DemoBetaConfiguration.Failure.invalidResponse
            }
            guard expiry > now else { throw DemoBetaConfiguration.Failure.expired }
        }
    }

    var expiry: Date? {
        guard expires_at.hasSuffix("Z") || expires_at.hasSuffix("+00:00") else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: expires_at) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: expires_at)
    }
}

/// Keychain-only envelope of the grant and the protected starter selection.
struct DemoInviteSession: Codable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    let grant: DemoInviteGrant
    let composition: DemoCompositionProfile

    var description: String { "<redacted demo invite session>" }
    var debugDescription: String { description }
    var customMirror: Mirror { Mirror(self, children: [:]) }

    static func decode(_ bytes: Data, now: Date? = nil) throws -> Self {
        guard (1...65536).contains(bytes.count) else { throw DemoBetaConfiguration.Failure.invalidResponse }
        let value = try JSONDecoder().decode(Self.self, from: bytes)
        try value.grant.validate(now: now)
        try value.composition.validate()
        return value
    }
}

#if G2C_DEMO_BETA
extension DevelopmentBetaComposition {
    static func demo(_ profile: DemoCompositionProfile) -> Self {
        let endpoint = DemoBetaConfiguration.endpoint
        return Self(endpoint: endpoint, needs: .init(needsID: profile.needs_id),
            typedMemory: .init(travel: .init(version: "app-travel.1", travel_ids: [profile.travel_id]),
                               memory: DemoCompositionProfile.memory, memoryEndpoint: endpoint),
            manualEditing: .init(), feedback: .init(), offline: .init(wallOffset: 0, uptimeOffset: 0, trusted: true))
    }
}
#endif
