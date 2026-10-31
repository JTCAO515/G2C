import Foundation
import Testing
@testable import G2CDevelopmentConfiguration

private func token(subject: String = "fixture", signature: String = "synthetic") throws -> String {
    let body = try JSONSerialization.data(withJSONObject: ["iss": "https://local.g2c.invalid", "aud": "g2c-local", "sub": subject])
    let payload = body.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    return "synthetic.\(payload).\(signature)"
}

struct DevelopmentConfigurationTests {
    @Test func missingEnvironmentNeverAssembles() throws {
        #expect(DevelopmentSessionConfiguration.read([:]) == nil)
        #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_API_BASE_URL": "http://127.0.0.1:8765"]) == nil)
        #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_TOKEN": try token()]) == nil)
    }
    @Test func onlyExplicitLoopbackAndValidLocalInputs() throws {
        for url in ["https://127.0.0.1:8765", "http://localhost:8765", "http://example.com:8765",
                    "http://127.0.0.1", "http://user@127.0.0.1:8765", "http://127.0.0.1:8765/path", "http://127.0.0.1:8765?x=1"] {
            #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_API_BASE_URL": url, "G2C_DEV_TOKEN": try token()]) == nil)
        }
        for invalid in ["", "synthetic", "token with spaces", "one.two.three"] {
            #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_API_BASE_URL": "http://127.0.0.1:8765", "G2C_DEV_TOKEN": invalid]) == nil)
        }
    }
    @Test func debugOptInAndReleaseDenial() throws {
        let environment = ["G2C_DEV_API_BASE_URL": "http://127.0.0.1:8765", "G2C_DEV_TOKEN": try token(), "G2C_DEV_PROPOSAL_ID": "p-fixture"]
        #if DEBUG
        let config = try #require(DevelopmentSessionConfiguration.read(environment))
        #expect(config.proposalID == "p-fixture")
        #expect(!String(reflecting: config).contains(try token()))
        #else
        #expect(DevelopmentSessionConfiguration.read(environment) == nil)
        #endif
    }
    @Test func renewedTokenKeepsStoragePartitionAndOtherUserDoesNot() throws {
        #if DEBUG
        func config(_ subject: String, signature: String) throws -> DevelopmentSessionConfiguration {
            let value = try token(subject: subject, signature: signature)
            return try #require(DevelopmentSessionConfiguration.read(["G2C_DEV_API_BASE_URL": "http://127.0.0.1:8765", "G2C_DEV_TOKEN": value]))
        }
        let a = try config("alice", signature: "first"), renewed = try config("alice", signature: "second"), b = try config("bob", signature: "first")
        #expect(a.accountID == renewed.accountID && a.environmentID == renewed.environmentID)
        #expect(a.accountID != b.accountID)
        #endif
    }
}

#if DEBUG
struct DevelopmentMemoryConfigurationTests {
    @Test func profileMustBeExplicitAndCanonical() throws {
        #expect(try DevelopmentMemoryProfile.read([:]) == nil)
        let raw = """
        {"subjects":["self"],"slots":{"diet":{"kind":"preference","collection_allowed":true,"semantic_resolved":false}},"extents":["long_term"],"context_ids":[]}
        """
        let profile = try #require(try DevelopmentMemoryProfile.read(["G2C_DEV_MEMORY_PROFILE": raw]))
        #expect(profile.subjects == ["self"])
        #expect(profile.slots["diet"]?.semantic_resolved == false)
        for invalid in ["{}", raw.replacingOccurrences(of: "preference", with: "invented-kind"),
                        raw.replacingOccurrences(of: "long_term", with: "current"),
                        raw.replacingOccurrences(of: "[\"self\"]", with: "[]")] {
            #expect(throws: (any Error).self) {
                try DevelopmentMemoryProfile.read(["G2C_DEV_MEMORY_PROFILE": invalid])
            }
        }
    }
}
#endif

extension DevelopmentConfigurationTests {
    @Test func typedActivationRemainsClosedInRelease() throws {
        #if !DEBUG
        let environment = ["G2C_DEV_TRAVEL_PROFILE":"{\"version\":\"app-travel.1\",\"travel_ids\":[]}",
            "G2C_DEV_TYPED_MEMORY_PROFILE":"{\"version\":\"app-memory.2\",\"subjects\":[\"self\"],\"slots\":{\"test\":{\"kind\":\"preference\",\"collection_allowed\":true,\"semantic_resolved\":true}},\"extents\":[\"long_term\"]}",
            "G2C_DEV_TYPED_MEMORY_URL":"http://127.0.0.1:8765"]
        #expect(try DevelopmentTypedMode.read(environment) == nil)
        #expect(try DevelopmentTypedMemoryProfile.read(environment) == nil)
        #expect(try DevelopmentTravelProfile.read(environment) == nil)
        #else
        #expect(try DevelopmentTypedMode.read([:]) == nil)
        #endif
    }
    @Test func typedModeRequiresBothProfilesAndAnExplicitLoopbackMemoryHost() throws {
        let travel = "{\"version\":\"app-travel.1\",\"travel_ids\":[]}"
        let memory = "{\"version\":\"app-memory.2\",\"subjects\":[\"self\"],\"slots\":{\"test\":{\"kind\":\"preference\",\"collection_allowed\":true,\"semantic_resolved\":true}},\"extents\":[\"long_term\",\"current\"]}"
        let profile = ["G2C_DEV_TRAVEL_PROFILE":travel,"G2C_DEV_TYPED_MEMORY_PROFILE":memory,"G2C_DEV_TYPED_MEMORY_URL":"http://127.0.0.1:8765"]
        #if DEBUG
        #expect(try DevelopmentTypedMode.read([:]) == nil)
        #expect(try DevelopmentTypedMode.read(profile)?.memoryEndpoint.absoluteString == "http://127.0.0.1:8765")
        for missing in profile.keys {
            var incomplete = profile;incomplete.removeValue(forKey:missing)
            #expect(throws:(any Error).self) { try DevelopmentTypedMode.read(incomplete) }
        }
        for endpoint in ["https://example.com","http://localhost:8765","http://127.0.0.1:8765/path","http://user@127.0.0.1:8765"] {
            var changed = profile;changed["G2C_DEV_TYPED_MEMORY_URL"] = endpoint
            #expect(throws:(any Error).self) { try DevelopmentTypedMode.read(changed) }
        }
        let legacy = String(memory.replacingOccurrences(of:"\"version\":\"app-memory.2\",",with:"").dropLast()) + ",\"context_ids\":[\"legacy-chat\"]}"
        #expect(throws:(any Error).self) { try DevelopmentTypedMemoryProfile.read(["G2C_DEV_TYPED_MEMORY_PROFILE":String(legacy)]) }
        #expect(throws:(any Error).self) { try DevelopmentTypedMemoryProfile.read(["G2C_DEV_TYPED_MEMORY_PROFILE":memory.replacingOccurrences(of:"app-memory.2",with:"future")]) }
        #else
        #expect(try DevelopmentTypedMode.read(profile) == nil)
        #endif
    }
    @Test func memoryKeyCreationChecksEveryOwnedJournalButNotOtherAccounts() throws {
        let files = FileManager.default,parent = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try files.createDirectory(at:parent,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        defer {try? files.removeItem(at:parent)}
        let root = parent.appendingPathComponent("account-a"),typed = root.appendingPathExtension("typed-v2")
        let rejection = typed.appendingPathExtension("CJMemoryTypedManagementV2.CJMemoryTypedManagementRejectionsV2")
        for directory in [root,typed,rejection,parent.appendingPathComponent("account-b")] {
            try files.createDirectory(at:directory,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        }
        try Data("unrelated".utf8).write(to:parent.appendingPathComponent("account-b/other"))
        #expect(try DevelopmentMemoryStorageNamespace.isEmpty(legacyRoot:root))
        let original = rejection.appendingPathComponent("original"),bytes = Data("retained encrypted original".utf8)
        try bytes.write(to:original)
        #expect(try !DevelopmentMemoryStorageNamespace.isEmpty(legacyRoot:root))
        #expect(try Data(contentsOf:original) == bytes)
    }
    @Test func legacyWriterRemainsAvailableBeforeTypedNamespaceActivation() throws {
        let files = FileManager.default,parent = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try files.createDirectory(at:parent,withIntermediateDirectories:false)
        defer {try? files.removeItem(at:parent)}
        let root = parent.appendingPathComponent("account-a")
        for name in ["account-a","account-a.lifecycle","account-a.CJMemoryRejectionsV1","account-b.typed-v2"] {
            try files.createDirectory(at:parent.appendingPathComponent(name),withIntermediateDirectories:false)
        }
        #expect(try DevelopmentMemoryStorageNamespace.legacyWritesAllowed(legacyRoot:root))
    }
    @Test func evenEmptyTypedNamespaceCannotReactivateAnOlderWriter() throws {
        let files = FileManager.default,parent = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try files.createDirectory(at:parent,withIntermediateDirectories:false)
        defer {try? files.removeItem(at:parent)}
        let root = parent.appendingPathComponent("account-a"),typed = root.appendingPathExtension("typed-v2")
        try files.createDirectory(at:typed,withIntermediateDirectories:false)
        #expect(try !DevelopmentMemoryStorageNamespace.legacyWritesAllowed(legacyRoot:root))
        #expect(try files.contentsOfDirectory(atPath:typed.path).isEmpty)
    }
    @Test func typedLifecycleRejectionsAndUnexpectedEntriesKeepLegacyReadOnly() throws {
        let files = FileManager.default,parent = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try files.createDirectory(at:parent,withIntermediateDirectories:false)
        defer {try? files.removeItem(at:parent)}
        for suffix in ["typed-v2.CJMemoryTypedManagementV2","typed-v2.CJMemoryTypedRejectionsV2","typed-v2"] {
            let root = parent.appendingPathComponent(UUID().uuidString),entry = root.appendingPathExtension(suffix)
            let bytes = Data("retained original namespace".utf8)
            try bytes.write(to:entry)
            #expect(try !DevelopmentMemoryStorageNamespace.legacyWritesAllowed(legacyRoot:root))
            #expect(try Data(contentsOf:entry) == bytes)
        }
    }
    @Test func aSymlinkOrUnexpectedFileCannotBeAnEmptyMemoryNamespace() throws {
        let files = FileManager.default,parent = files.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try files.createDirectory(at:parent,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        defer {try? files.removeItem(at:parent)}
        let root = parent.appendingPathComponent("account"),target = parent.appendingPathComponent("target")
        try files.createDirectory(at:target,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        try files.createSymbolicLink(at:root.appendingPathExtension("typed-v2"),withDestinationURL:target)
        #expect(try !DevelopmentMemoryStorageNamespace.isEmpty(legacyRoot:root))
        let another = parent.appendingPathComponent("another-account")
        try Data().write(to:another.appendingPathExtension("journal"))
        #expect(try !DevelopmentMemoryStorageNamespace.isEmpty(legacyRoot:another))
    }
    #if DEBUG
    @Test func managementEndpointIsExplicitAndLoopbackOnly() throws {
        #expect(try DevelopmentMemoryProfile.managementEndpoint([:]) == nil)
        let key = "G2C_DEV_MEMORY_MANAGEMENT_URL"
        #expect(try DevelopmentMemoryProfile.managementEndpoint([key: "http://127.0.0.1:8766/"])?.absoluteString == "http://127.0.0.1:8766")
        for value in ["", "https://127.0.0.1:8766", "http://localhost:8766", "http://127.0.0.1:8766/path", "http://127.0.0.1:8766?x=1", "http://u@127.0.0.1:8766", "http://127.0.0.1"] {
            #expect(throws: DevelopmentMemoryProfile.ConfigurationFailure.self) {
                try DevelopmentMemoryProfile.managementEndpoint([key: value])
            }
        }
    }
    #endif
}


extension DevelopmentConfigurationTests {
    @Test func typedTravelChoicesAreExplicitVersionedAndNeverEnabledInRelease() throws {
        let key = "G2C_DEV_TRAVEL_PROFILE"
        let id = "0123456789abcdef0123456789abcdef"
        let valid = "{\"version\":\"app-travel.1\",\"travel_ids\":[\"" + id + "\"]}"
        #if DEBUG
        #expect(try DevelopmentTravelProfile.read([:]) == nil)
        #expect(try DevelopmentTravelProfile.read([key:valid])?.travel_ids == [id])
        #expect(try DevelopmentTravelProfile.read([key:"{\"version\":\"app-travel.1\",\"travel_ids\":[]}"])?.travel_ids == [])
        for raw in ["{}", "null", valid.replacingOccurrences(of:"app-travel.1",with:"future"),
                    valid.replacingOccurrences(of:id,with:"legacy-conversation"),
                    valid.replacingOccurrences(of:"[\"" + id + "\"]",with:"[\"" + id + "\",\"" + id + "\"]")] {
            #expect(throws:(any Error).self) { try DevelopmentTravelProfile.read([key:raw]) }
        }
        #else
        #expect(try DevelopmentTravelProfile.read([key:valid]) == nil)
        #endif
    }
    @Test func placeConsumerFormatIsExplicitAndReleaseRemainsClosed() throws {
        #if DEBUG
        #expect(try !DevelopmentSessionConfiguration.placeToolsEnabled([:]))
        #expect(try DevelopmentSessionConfiguration.placeToolsEnabled(["G2C_DEV_PLACE_TOOLS":"synthetic-v1"]))
        for value in ["", "true", "live", "synthetic-v2"] {
            #expect(throws:DevelopmentSessionConfiguration.DevelopmentToolsFailure.invalidProfile) {
                try DevelopmentSessionConfiguration.placeToolsEnabled(["G2C_DEV_PLACE_TOOLS":value])
            }
        }
        #else
        #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_PLACE_TOOLS":"synthetic-v1","G2C_DEV_API_BASE_URL":"http://127.0.0.1:8765","G2C_DEV_TOKEN":try token()]) == nil)
        #endif
    }
}
