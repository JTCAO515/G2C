import Foundation

enum DevelopmentKeychainIdentity {
    enum Failure: Error { case invalidSigningIdentity }
    static func validated(bundleIdentifier: String?, signedIdentifier: String?) throws -> String {
        guard let bundleIdentifier, !bundleIdentifier.isEmpty, !bundleIdentifier.contains("*"), let signedIdentifier,
              signedIdentifier.hasSuffix("." + bundleIdentifier) else { throw Failure.invalidSigningIdentity }
        let prefix = signedIdentifier.dropLast(bundleIdentifier.count + 1)
        guard prefix.utf8.count == 10,
              prefix.utf8.allSatisfy({ (65...90).contains($0) || (48...57).contains($0) }) else {
            throw Failure.invalidSigningIdentity
        }
        return signedIdentifier
    }
    static func read() throws -> String {
        #if os(iOS) && !targetEnvironment(simulator) && (G2C_DEMO_BETA || (DEBUG && G2C_M4_DEVICE_ACCEPTANCE))
        return try validated(bundleIdentifier:Bundle.main.bundleIdentifier,
            signedIdentifier:Bundle.main.object(forInfoDictionaryKey:"G2CDevelopmentApplicationIdentifier") as? String)
        #else
        guard let identifier=Bundle.main.bundleIdentifier else { throw Failure.invalidSigningIdentity }
        return identifier
        #endif
    }
}

enum DevelopmentAccountInput {
    enum Failure: Error { case invalidAccounts }
    #if DEBUG && os(iOS) && !targetEnvironment(simulator) && G2C_M4_DEVICE_ACCEPTANCE
    static func discardStaged() throws {
        let files=FileManager.default
        let root=try files.url(for:.cachesDirectory,in:.userDomainMask,appropriateFor:nil,create:false)
        let file=root.appendingPathComponent("G2CM4DeviceAccounts.json")
        guard files.fileExists(atPath:file.path) else { return }
        let values=try file.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey])
        guard values.isRegularFile==true,values.isSymbolicLink==false else { throw Failure.invalidAccounts }
        try files.removeItem(at:file)
    }
    #endif
    static func decode(_ raw: Data) throws -> [String:String] {
        guard raw.count <= 131072,
              let tokens=try JSONSerialization.jsonObject(with:raw) as? [String:String],tokens.count<=8,
              tokens.keys.allSatisfy({ !$0.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty }) else {
            throw Failure.invalidAccounts
        }
        return tokens
    }
    static func read(_ environment:[String:String]) throws -> [String:String] {
        #if DEBUG && os(iOS) && !targetEnvironment(simulator) && G2C_M4_DEVICE_ACCEPTANCE
        if let name=environment["G2C_M4_ACCOUNTS_FILE"] {
            guard name=="G2CM4DeviceAccounts.json",[nil,"{}"].contains(environment["G2C_DEV_ACCOUNTS"]) else {
                throw Failure.invalidAccounts
            }
            let files=FileManager.default
            let root=try files.url(for:.cachesDirectory,in:.userDomainMask,appropriateFor:nil,create:false)
            let file=root.appendingPathComponent(name)
            let values=try file.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
            guard values.isRegularFile==true,values.isSymbolicLink==false,
                  let size=values.fileSize,size<=131072 else { throw Failure.invalidAccounts }
            try files.setAttributes([.posixPermissions:0o600,.protectionKey:FileProtectionType.complete],ofItemAtPath:file.path)
            let data=try Data(contentsOf:file)
            try files.removeItem(at:file) // One-use operator input, never retained as a journal.
            return try decode(data)
        }
        #endif
        guard let raw=(environment["G2C_DEV_ACCOUNTS"] ?? "{}").data(using:.utf8) else { throw Failure.invalidAccounts }
        return try decode(raw)
    }
}
#if DEBUG || G2C_DEMO_BETA
import CryptoKit
#endif

struct DevelopmentMemorySlot: Decodable {
    let kind: String
    let collection_allowed: Bool
    let semantic_resolved: Bool
}
enum DevelopmentToolAnswerProfile { case plain,place,fact,needs }
struct DevelopmentTripEditingProfile {
    enum Failure: Error { case invalidProfile }
    static func read(_ environment: [String: String]) throws -> Self? {
        #if DEBUG
        guard let value = environment["G2C_DEV_TRIP_MANUAL_PROFILE"] else { return nil }
        guard value == "manual-v1" else { throw Failure.invalidProfile }
        return Self()
        #else
        return nil
        #endif
    }
}
struct DevelopmentMemoryHistoryProfile {
    enum Failure: Error { case invalidProfile }
    static func read(_ environment: [String: String]) throws -> Self? {
        #if DEBUG
        guard let value = environment["G2C_DEV_MEMORY_HISTORY_PROFILE"] else { return nil }
        guard value == "history-v1", environment["G2C_DEV_ACCOUNT_MODE"] == "1" else { throw Failure.invalidProfile }
        return Self()
        #else
        return nil
        #endif
    }
}
struct DevelopmentFeedbackProfile {
    enum Failure: Error { case invalidProfile }
    static func read(_ environment: [String: String]) throws -> Self? {
        #if DEBUG
        guard let value = environment["G2C_DEV_FEEDBACK_PROFILE"] else { return nil }
        guard value == "feedback-v1" else { throw Failure.invalidProfile }
        return Self()
        #else
        return nil
        #endif
    }
}
enum DevelopmentMessageProfile:String {
    case discussion="trip-discussion-v1",edit="trip-edit-v1",editResults="trip-edit-result-v1",planning="needs-planning-v1"
    static func read(_ environment:[String:String]) throws -> Self? {
        #if DEBUG
        guard let value=environment["G2C_DEV_MESSAGE_PROFILE"] else { return nil }
        guard let result=Self(rawValue:value) else { throw DevelopmentDiscussionProfile.Failure.invalidProfile }
        return result
        #else
        return nil
        #endif
    }
    func validate(typed:DevelopmentTypedMode?,needs:DevelopmentNeedsProfile?,answer:DevelopmentToolAnswerProfile,
                  travel:DevelopmentTravelProfile?=nil,legacyProposal:Bool=false) throws {
        switch self {
        case .discussion:
            guard typed == nil else { throw DevelopmentDiscussionProfile.Failure.incompatibleProfiles }
        case .edit,.editResults:
            if self == .editResults { guard !legacyProposal else { throw DevelopmentDiscussionProfile.Failure.incompatibleProfiles } }
            guard let typed,!typed.travel.travel_ids.isEmpty,needs != nil else { throw DevelopmentDiscussionProfile.Failure.incompatibleProfiles }
            guard case .plain=answer else { throw DevelopmentDiscussionProfile.Failure.incompatibleProfiles }
        case .planning:
            guard typed == nil,needs != nil,let travel,!travel.travel_ids.isEmpty,!legacyProposal else {
                throw DevelopmentDiscussionProfile.Failure.incompatibleProfiles
            }
            guard case .plain=answer else { throw DevelopmentDiscussionProfile.Failure.incompatibleProfiles }
        }
    }
}
enum DevelopmentDiscussionProfile {
    enum Failure:Error { case invalidProfile,incompatibleProfiles }
    static func read(_ environment:[String:String]) throws -> Bool {
        try DevelopmentMessageProfile.read(environment) == .discussion
    }
}
/// Explicit local record selection only. Server AUTH still derives its owner.
struct DevelopmentNeedsProfile {
    let needsID: String
    enum Failure: Error { case invalidProfile }
    static func read(_ environment: [String: String]) throws -> Self? {
        #if DEBUG
        let keys = ["G2C_DEV_NEEDS_PROFILE", "G2C_DEV_NEEDS_ID"]
        guard keys.contains(where: { environment[$0] != nil }) else { return nil }
        guard environment["G2C_DEV_NEEDS_PROFILE"] == "manual-v1", let id = environment["G2C_DEV_NEEDS_ID"],
              id.range(of: "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$", options: .regularExpression) == (id.startIndex..<id.endIndex) else {
            throw Failure.invalidProfile
        }
        return Self(needsID: id)
        #else
        return nil
        #endif
    }
}
/// UI choices only. No legacy conversation allow-list is reinterpreted as
/// travel consent; the frozen typed server policy and B lease remain authoritative.
struct DevelopmentTypedMemoryProfile: Decodable {
    let version: String
    let subjects: [String]
    let slots: [String:DevelopmentMemorySlot]
    let extents: [String]
    enum ConfigurationFailure: Error { case invalidProfile,incompleteMode }
    static func read(_ environment: [String:String]) throws -> Self? {
        #if DEBUG
        guard let raw = environment["G2C_DEV_TYPED_MEMORY_PROFILE"] else { return nil }
        guard let data = raw.data(using:.utf8),data.count <= 262144,
              let fields = try JSONSerialization.jsonObject(with:data) as? [String:Any],
              Set(fields.keys) == ["version","subjects","slots","extents"] else { throw ConfigurationFailure.invalidProfile }
        let profile = try JSONDecoder().decode(Self.self,from:data)
        guard profile.version == "app-memory.2",!profile.subjects.isEmpty,!profile.slots.isEmpty,!profile.extents.isEmpty,
              profile.subjects.allSatisfy({ !$0.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty }),
              Set(profile.subjects).count == profile.subjects.count,
              profile.slots.allSatisfy({ !$0.key.isEmpty && ["fact","experience","preference","inference"].contains($0.value.kind) }),
              profile.extents.allSatisfy({ ["long_term","current"].contains($0) }),
              Set(profile.extents).count == profile.extents.count else { throw ConfigurationFailure.invalidProfile }
        return profile
        #else
        return nil
        #endif
    }
}
struct DevelopmentTypedMode {
    let travel: DevelopmentTravelProfile
    let memory: DevelopmentTypedMemoryProfile
    let memoryEndpoint: URL
    static func read(_ environment: [String:String],messageProfile:DevelopmentMessageProfile?=nil) throws -> Self? {
        #if DEBUG
        if messageProfile == .planning {
            guard environment["G2C_DEV_TYPED_MEMORY_PROFILE"] == nil,environment["G2C_DEV_TYPED_MEMORY_URL"] == nil else {
                throw DevelopmentDiscussionProfile.Failure.incompatibleProfiles
            }
            return nil
        }
        let keys = ["G2C_DEV_TRAVEL_PROFILE","G2C_DEV_TYPED_MEMORY_PROFILE","G2C_DEV_TYPED_MEMORY_URL"]
        guard keys.contains(where:{environment[$0] != nil}) else { return nil }
        guard let travel = try DevelopmentTravelProfile.read(environment),let memory = try DevelopmentTypedMemoryProfile.read(environment),
              let endpoint = DevelopmentSessionConfiguration.readEndpoint(environment,key:"G2C_DEV_TYPED_MEMORY_URL") else {
            throw DevelopmentTypedMemoryProfile.ConfigurationFailure.incompleteMode
        }
        return Self(travel:travel,memory:memory,memoryEndpoint:endpoint)
        #else
        return nil
        #endif
    }
}
/// All adjacent journals use the same account/key purpose. A missing key must
/// not be replaced while any old or typed original still exists in that namespace.
enum DevelopmentMemoryStorageNamespace {
    /// Once the newer journal namespace exists, an older consumer cannot prove
    /// its outcomes or reinterpret it. Keep V1 GET recovery, but never revive
    /// its writer by removing the typed configuration. Reenter the compatible
    /// typed consumer instead; no journal is deleted to unlock an old writer.
    static func legacyWritesAllowed(legacyRoot: URL,files: FileManager = .default) throws -> Bool {
        let prefix = legacyRoot.lastPathComponent + ".typed-v2"
        return try !files.contentsOfDirectory(at:legacyRoot.deletingLastPathComponent(),includingPropertiesForKeys:nil)
            .contains { $0.lastPathComponent == prefix || $0.lastPathComponent.hasPrefix(prefix + ".") }
    }
    static func isEmpty(legacyRoot: URL,files: FileManager = .default) throws -> Bool {
        let parent = legacyRoot.deletingLastPathComponent(),name = legacyRoot.lastPathComponent
        let entries = try files.contentsOfDirectory(at:parent,includingPropertiesForKeys:[.isSymbolicLinkKey,.isDirectoryKey])
        for entry in entries where entry.lastPathComponent == name || entry.lastPathComponent.hasPrefix(name + ".") {
            let metadata = try entry.resourceValues(forKeys:[.isSymbolicLinkKey,.isDirectoryKey])
            guard metadata.isSymbolicLink == false,metadata.isDirectory == true else { return false }
            if try !files.contentsOfDirectory(atPath:entry.path).isEmpty { return false }
        }
        return true
    }
}

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

    #if DEBUG || G2C_DEMO_BETA
    static func restoring(endpoint: URL, token: String, proposalID: String?, approvedLocalHost: String?, approvedBetaAPI: Bool = false) -> Self? {
        var environment=["G2C_DEV_API_BASE_URL":endpoint.absoluteString,"G2C_DEV_TOKEN":token]
        if let proposalID { environment["G2C_DEV_PROPOSAL_ID"]=proposalID }
        if let approvedLocalHost { environment["G2C_M4_LOCAL_HOST"]=approvedLocalHost }
        if approvedBetaAPI { environment["G2C_M4_BETA_API"]="1" }
        return read(environment)
    }
    let endpoint: URL
    let token: String
    let proposalID: String?
    let environmentID: UUID
    let accountID: UUID
    let subject: String
    let expiresAt: Double?

    static func readEndpoint(_ environment: [String: String], key: String = "G2C_DEV_API_BASE_URL") -> URL? {
        #if G2C_DEMO_BETA
        return nil
        #else
        guard let rawURL = environment[key],
              var url = URLComponents(string: rawURL),
              url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil, ["", "/"].contains(url.path) else { return nil }
        #if G2C_M4_DEVICE_ACCEPTANCE
        if environment["G2C_M4_BETA_API"] != nil {
            guard environment["G2C_M4_BETA_API"] == "1",
                  environment["G2C_M4_LOCAL_HOST"] == nil,
                  url.scheme == "https", url.host == "api-beta.go2china.space",
                  url.port == nil || url.port == 443 else { return nil }
            url.path = ""; url.port = nil
            return url.url
        }
        #endif
        guard let port = url.port, (1...65535).contains(port) else { return nil }
        let approved: Bool
        #if G2C_M4_DEVICE_ACCEPTANCE
        approved = isM4LocalHost(url.host, environment: environment)
        #else
        approved = false
        #endif
        #if os(iOS) && !targetEnvironment(simulator)
        let loopback = false
        #else
        let loopback = url.scheme == "http" && url.host == "127.0.0.1"
        #endif
        guard loopback || (url.scheme == "https" && approved) else { return nil }
        url.path = ""
        return url.url
        #endif
    }

    // Independent environment-input boundary. The transport separately admits
    // its immutable endpoint and preserves the per-route/session capabilities.
    private static func isM4LocalHost(_ host: String?, environment: [String:String]) -> Bool {
        guard let host, host == environment["G2C_M4_LOCAL_HOST"] else { return false }
        let fields = host.split(separator: ".", omittingEmptySubsequences: false)
        let bytes = fields.compactMap { UInt8($0) }
        guard fields.count == 4, bytes.count == 4,
              zip(fields, bytes).allSatisfy({ String($0.1) == $0.0 }) else { return false }
        return bytes[0] == 10 || (bytes[0] == 172 && (16...31).contains(bytes[1]))
            || (bytes[0] == 192 && bytes[1] == 168) || (bytes[0] == 169 && bytes[1] == 254)
    }

    static func placeToolsEnabled(_ environment: [String:String]) throws -> Bool {
        guard let value = environment["G2C_DEV_PLACE_TOOLS"] else { return false }
        guard value == "synthetic-v1" else { throw DevelopmentToolsFailure.invalidProfile }
        return true
    }
    static func toolAnswerProfile(_ environment: [String:String]) throws -> DevelopmentToolAnswerProfile {
        let place = try placeToolsEnabled(environment)
        let fact: Bool
        if let value = environment["G2C_DEV_FACT_TOOLS"] {
            guard value == "synthetic-fact-v1" else { throw DevelopmentToolsFailure.invalidProfile }
            fact = true
        } else { fact = false }
        let needs: Bool
        if let value = environment["G2C_DEV_NEEDS_PREVIEW"] {
            guard value == "synthetic-needs-v1", try DevelopmentNeedsProfile.read(environment) != nil else {
                throw DevelopmentToolsFailure.invalidProfile
            }
            needs = true
        } else { needs = false }
        guard [place, fact, needs].filter({ $0 }).count <= 1 else { throw DevelopmentToolsFailure.invalidProfile }
        return needs ? .needs : fact ? .fact : place ? .place : .plain
    }
    enum DevelopmentToolsFailure: Error { case invalidProfile }

    static func environmentNamespace(_ endpoint: URL) -> UUID {
        #if G2C_DEMO_BETA
        namespace("G2C.DEMO.TRIP.environment|" + endpoint.absoluteString)
        #else
        namespace("G2C.DEBUG.TRIP.environment|" + endpoint.absoluteString)
        #endif
    }

    static func read(_ environment: [String: String]) -> Self? {
        #if G2C_DEMO_BETA
        return nil
        #else
        guard let endpoint = readEndpoint(environment),
              let token = environment["G2C_DEV_TOKEN"], let claims = DevelopmentBearerClaims.read(token) else { return nil }
        let subject = claims.subject
        let proposalID = environment["G2C_DEV_PROPOSAL_ID"]
        if let proposalID, proposalID.range(of: "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$", options: .regularExpression) == nil { return nil }
        return Self(endpoint: endpoint, token: token, proposalID: proposalID,
            environmentID: environmentNamespace(endpoint),
            accountID: namespace("G2C.DEBUG.TRIP.account|https://local.g2c.invalid|" + subject),
            subject: subject, expiresAt: claims.expiration)
        #endif
    }

    #if G2C_DEMO_BETA
    static func demo(_ invite: DemoInviteSession) -> Self {
        let endpoint = DemoBetaConfiguration.endpoint
        return Self(endpoint: endpoint, token: invite.grant.access_token, proposalID: nil,
            environmentID: environmentNamespace(endpoint),
            accountID: namespace("G2C.DEMO.TRIP.account|https://local.g2c.invalid|" + invite.grant.subject),
            subject: invite.grant.subject, expiresAt: invite.grant.expiry?.timeIntervalSince1970)
    }
    #endif

    private static func namespace(_ value: String) -> UUID {
        let b = Array(SHA256.hash(data: Data(value.utf8)))
        return UUID(uuid: (b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]))
    }
    #else
    static func read(_ environment: [String: String]) -> Self? { nil }
    #endif
}

#if DEBUG || G2C_DEMO_BETA
/// Same operator-owned profile schema as local-memory-policy.1. These values
/// describe choices only; the signed API remains the consent/owner authority.
struct DevelopmentMemoryProfile: Decodable {
    typealias Slot = DevelopmentMemorySlot
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

/// Explicit DEBUG-only local offline integration; clock offsets are native-test inputs,
/// never a server time claim or a Release permission.
struct DevelopmentOfflineProfile {
    let wallOffset: Int64
    let uptimeOffset: Int64
    let trusted: Bool
    enum Failure: Error { case invalidConfiguration }
    static func read(_ environment: [String: String]) throws -> Self? {
        #if DEBUG
        let keys = ["G2C_DEV_OFFLINE_TRIP", "G2C_DEV_OFFLINE_WALL_OFFSET", "G2C_DEV_OFFLINE_UPTIME_OFFSET", "G2C_DEV_OFFLINE_TIME_TRUSTED"]
        guard keys.contains(where: { environment[$0] != nil }) else { return nil }
        guard environment["G2C_DEV_OFFLINE_TRIP"] == "last-sync-v1", environment["G2C_DEV_ACCOUNT_MODE"] == "1" else {
            throw Failure.invalidConfiguration
        }
        func offset(_ name: String) throws -> Int64 {
            guard let raw = environment[name] else { return 0 }
            guard let value = Int64(raw), String(value) == raw, (-315_360_000...315_360_000).contains(value) else {
                throw Failure.invalidConfiguration
            }
            return value
        }
        let trusted: Bool
        switch environment["G2C_DEV_OFFLINE_TIME_TRUSTED"] {
        case nil, "1": trusted = true
        case "0": trusted = false
        default: throw Failure.invalidConfiguration
        }
        return try .init(wallOffset: offset(keys[1]), uptimeOffset: offset(keys[2]), trusted: trusted)
        #else
        return nil
        #endif
    }
}

/// Explicit opt-in for the signed internal beta account root. Individual
/// development profiles retain their own compatibility rules.
struct DevelopmentBetaComposition {
    static let setting = "G2C_M4_BETA_COMPOSITION"
    enum Failure: Error { case invalidConfiguration }

    let endpoint: URL
    let needs: DevelopmentNeedsProfile
    let typedMemory: DevelopmentTypedMode
    let manualEditing: DevelopmentTripEditingProfile
    let feedback: DevelopmentFeedbackProfile
    let offline: DevelopmentOfflineProfile

    static func read(_ environment: [String: String]) throws -> Self? {
        #if DEBUG
        guard environment[setting] != nil else { return nil }
        #if G2C_M4_DEVICE_ACCEPTANCE
        let incompatibleSettings = [
            "G2C_DEV_TOKEN", "G2C_DEV_PROPOSAL_ID", "G2C_DEV_MESSAGE_PROFILE",
            "G2C_DEV_MEMORY_PROFILE", "G2C_DEV_MEMORY_MANAGEMENT_URL", "G2C_DEV_MEMORY_HISTORY_PROFILE",
            "G2C_DEV_MEMORY_CANDIDATE_URL", "G2C_DEV_PLACE_TOOLS", "G2C_DEV_FACT_TOOLS", "G2C_DEV_NEEDS_PREVIEW",
            "G2C_DEV_OFFLINE_WALL_OFFSET", "G2C_DEV_OFFLINE_UPTIME_OFFSET", "G2C_DEV_OFFLINE_TIME_TRUSTED",
        ]
        guard environment[setting] == "internal-v1", environment["G2C_M4_BETA_API"] == "1",
              environment["G2C_DEV_ACCOUNT_MODE"] == "1", environment["G2C_DEV_CLEANUP_PROFILE"] == "device-v4",
              [nil, "{}"].contains(environment["G2C_DEV_ACCOUNTS"]),
              incompatibleSettings.allSatisfy({ environment[$0] == nil }),
              let endpoint = DevelopmentSessionConfiguration.readEndpoint(environment),
              let needs = try DevelopmentNeedsProfile.read(environment),
              let typedMemory = try DevelopmentTypedMode.read(environment),
              typedMemory.memoryEndpoint == endpoint, !typedMemory.travel.travel_ids.isEmpty,
              DevelopmentSessionConfiguration.readEndpoint(environment, key: "G2C_DEV_MEMORY_ERASURE_URL") == endpoint,
              let manualEditing = try DevelopmentTripEditingProfile.read(environment),
              let feedback = try DevelopmentFeedbackProfile.read(environment),
              let offline = try DevelopmentOfflineProfile.read(environment) else { throw Failure.invalidConfiguration }
        return Self(endpoint: endpoint, needs: needs, typedMemory: typedMemory,
                    manualEditing: manualEditing, feedback: feedback, offline: offline)
        #else
        throw Failure.invalidConfiguration
        #endif
        #else
        return nil
        #endif
    }
}

/// Unverified JWT metadata may constrain a local namespace or deny an expired
/// attempt. Only the signed API's verification grants a business session.
struct DevelopmentBearerClaims {
    let subject: String
    let expiration: Double?

    static func read(_ token: String) -> Self? {
        guard !token.isEmpty, token.utf8.count <= 16384,
              token.utf8.allSatisfy({ $0 > 32 && $0 < 127 }) else { return nil }
        let parts = token.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3, parts.allSatisfy({ !$0.isEmpty }) else { return nil }
        var payload = String(parts[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        payload += String(repeating: "=", count: (4 - payload.count % 4) % 4)
        guard let bytes = Data(base64Encoded: payload),
              let claims = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              claims["iss"] as? String == "https://local.g2c.invalid", claims["aud"] as? String == "g2c-local",
              let subject = claims["sub"] as? String, !subject.isEmpty, subject.utf8.count <= 256 else { return nil }
        return Self(subject: subject, expiration: claims["exp"] as? Double)
    }
}
