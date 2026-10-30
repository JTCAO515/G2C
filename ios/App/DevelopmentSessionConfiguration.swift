import Foundation
#if DEBUG
import CryptoKit
#endif

/// Operator-owned choices only. Actual travel ownership/currentness must be
/// established by the existing signed GET before an explicit selection is used.
struct DevelopmentTravelProfile: Decodable {
    let version: String
    let travel_ids: [String]
    enum ConfigurationFailure: Error { case invalidTravelProfile }
    static func read(_ environment: [String:String]) throws -> Self? {
        #if DEBUG
        guard let raw = environment["G2C_DEV_TRAVEL_PROFILE"] else { return nil }
        guard let data = raw.data(using:.utf8),data.count <= 16384 else { throw ConfigurationFailure.invalidTravelProfile }
        let value = try JSONDecoder().decode(Self.self,from:data)
        guard value.version == "app-travel.1",value.travel_ids.count <= 100,
              Set(value.travel_ids).count == value.travel_ids.count,
              value.travel_ids.allSatisfy({ id in
                  id.utf8.count == 32 && id.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) })
              }) else { throw ConfigurationFailure.invalidTravelProfile }
        return value
        #else
        return nil
        #endif
    }
}

/// Development-only input, never a production identity or an authorization proof.
struct DevelopmentSessionConfiguration: CustomStringConvertible, CustomReflectable {
    var description: String { "<redacted development configuration>" }
    var customMirror: Mirror { Mirror(self, children: [:]) }

    #if DEBUG
    let endpoint: URL
    let token: String
    let proposalID: String?
    let environmentID: UUID
    let accountID: UUID
    let subject: String
    let expiresAt: Double?

    static func readEndpoint(_ environment: [String: String], key: String = "G2C_DEV_API_BASE_URL") -> URL? {
        guard let rawURL = environment[key],
              var url = URLComponents(string: rawURL), url.scheme == "http", url.host == "127.0.0.1",
              let port = url.port, (1...65535).contains(port), url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil, ["", "/"].contains(url.path) else { return nil }
        url.path = ""
        return url.url
    }

    static func placeToolsEnabled(_ environment: [String:String]) throws -> Bool {
        guard let value = environment["G2C_DEV_PLACE_TOOLS"] else { return false }
        guard value == "synthetic-v1" else { throw DevelopmentToolsFailure.invalidProfile }
        return true
    }
    enum DevelopmentToolsFailure: Error { case invalidProfile }

    static func environmentNamespace(_ endpoint: URL) -> UUID {
        namespace("G2C.DEBUG.TRIP.environment|" + endpoint.absoluteString)
    }

    static func read(_ environment: [String: String]) -> Self? {
        guard let endpoint = readEndpoint(environment),
              let token = environment["G2C_DEV_TOKEN"], !token.isEmpty, token.utf8.count <= 16384,
              token.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { return nil }
        // These local dev-token claims partition simulator storage only. The API
        // remains the JWT/auth authority; no Supabase/production session is created.
        let parts = token.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3, parts.allSatisfy({ !$0.isEmpty }) else { return nil }
        var payload = String(parts[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        payload += String(repeating: "=", count: (4 - payload.count % 4) % 4)
        guard let bytes = Data(base64Encoded: payload),
              let claims = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              claims["iss"] as? String == "https://local.g2c.invalid", claims["aud"] as? String == "g2c-local",
              let subject = claims["sub"] as? String, !subject.isEmpty, subject.utf8.count <= 256 else { return nil }
        let proposalID = environment["G2C_DEV_PROPOSAL_ID"]
        if let proposalID, proposalID.range(of: "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$", options: .regularExpression) == nil { return nil }
        return Self(endpoint: endpoint, token: token, proposalID: proposalID,
            environmentID: environmentNamespace(endpoint),
            accountID: namespace("G2C.DEBUG.TRIP.account|https://local.g2c.invalid|" + subject),
            subject: subject, expiresAt: claims["exp"] as? Double)
    }

    private static func namespace(_ value: String) -> UUID {
        let b = Array(SHA256.hash(data: Data(value.utf8)))
        return UUID(uuid: (b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]))
    }
    #else
    static func read(_ environment: [String: String]) -> Self? { nil }
    #endif
}

#if DEBUG
/// Same operator-owned profile schema as local-memory-policy.1. These values
/// describe choices only; the signed API remains the consent/owner authority.
struct DevelopmentMemoryProfile: Decodable {
    struct Slot: Decodable {
        let kind: String
        let collection_allowed: Bool
        let semantic_resolved: Bool
    }
    let subjects: [String]
    let slots: [String: Slot]
    let extents: [String]
    let context_ids: [String]

    static func read(_ environment: [String: String]) throws -> Self? {
        guard let raw = environment["G2C_DEV_MEMORY_PROFILE"] else { return nil }
        guard let data = raw.data(using: .utf8), data.count <= 262144 else {
            throw ConfigurationFailure.invalidMemoryProfile
        }
        let value = try JSONDecoder().decode(Self.self, from: data)
        guard !value.subjects.isEmpty, !value.slots.isEmpty, !value.extents.isEmpty,
              value.subjects.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }),
              value.slots.allSatisfy({ !$0.key.isEmpty && ["fact", "experience", "preference"].contains($0.value.kind) }),
              value.extents.allSatisfy({ ["long_term", "current"].contains($0) }),
              !value.extents.contains("current") || !value.context_ids.isEmpty else {
            throw ConfigurationFailure.invalidMemoryProfile
        }
        return value
    }
    static func managementEndpoint(_ environment: [String: String]) throws -> URL? {
        let key = "G2C_DEV_MEMORY_MANAGEMENT_URL"
        guard environment[key] != nil else { return nil }
        guard let endpoint = DevelopmentSessionConfiguration.readEndpoint(environment, key: key) else { throw ConfigurationFailure.invalidManagementEndpoint }
        return endpoint
    }
    enum ConfigurationFailure: Error { case invalidMemoryProfile, invalidManagementEndpoint }
}
#endif
