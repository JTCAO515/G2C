import Foundation
import Testing
@testable import G2CDevelopmentConfiguration

private func token(subject: String = "fixture", signature: String = "synthetic") throws -> String {
    let body = try JSONSerialization.data(withJSONObject: ["iss": "https://local.g2c.invalid", "aud": "g2c-local", "sub": subject])
    let payload = body.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    return "synthetic.\(payload).\(signature)"
}

struct DevelopmentBetaCompositionTests {
    private static let endpoint = "https://api-beta.go2china.space"
    private static let profile = [
        "G2C_M4_BETA_COMPOSITION": "internal-v1", "G2C_M4_BETA_API": "1",
        "G2C_DEV_API_BASE_URL": endpoint, "G2C_DEV_ACCOUNT_MODE": "1",
        "G2C_DEV_CLEANUP_PROFILE": "device-v4", "G2C_DEV_OFFLINE_TRIP": "last-sync-v1",
        "G2C_DEV_TRIP_MANUAL_PROFILE": "manual-v1", "G2C_DEV_FEEDBACK_PROFILE": "feedback-v1",
        "G2C_DEV_NEEDS_PROFILE": "manual-v1", "G2C_DEV_NEEDS_ID": "needs-fixture",
        "G2C_DEV_TRAVEL_PROFILE": #"{"version":"app-travel.1","travel_ids":["0123456789abcdef0123456789abcdef"]}"#,
        "G2C_DEV_TYPED_MEMORY_PROFILE": #"{"version":"app-memory.2","subjects":["traveler"],"slots":{"food":{"kind":"preference","collection_allowed":true,"semantic_resolved":true}},"extents":["long_term","current"]}"#,
        "G2C_DEV_TYPED_MEMORY_URL": endpoint, "G2C_DEV_MEMORY_ERASURE_URL": endpoint,
    ]

    @Test func compositionRequiresAnExplicitDeviceBuildAndEveryCapability() throws {
        #expect(try DevelopmentBetaComposition.read([:]) == nil)
        #if DEBUG && G2C_M4_DEVICE_ACCEPTANCE
        let composition = try #require(try DevelopmentBetaComposition.read(Self.profile))
        #expect(composition.endpoint.absoluteString == Self.endpoint)
        #expect(composition.typedMemory.memoryEndpoint == composition.endpoint)
        #expect(composition.typedMemory.travel.travel_ids == ["0123456789abcdef0123456789abcdef"])
        #expect(composition.needs.needsID == "needs-fixture")
        #expect(composition.offline.trusted)
        for key in Self.profile.keys where key != DevelopmentBetaComposition.setting {
            var incomplete = Self.profile
            incomplete.removeValue(forKey: key)
            #expect(throws: (any Error).self, "missing \(key)") { try DevelopmentBetaComposition.read(incomplete) }
        }
        #elseif DEBUG
        #expect(throws: DevelopmentBetaComposition.Failure.invalidConfiguration) {
            try DevelopmentBetaComposition.read(Self.profile)
        }
        #else
        #expect(try DevelopmentBetaComposition.read(Self.profile) == nil)
        #endif
    }

    #if DEBUG && G2C_M4_DEVICE_ACCEPTANCE
    @Test func compositionRejectsCompetingWritersAndNonBetaEndpoints() throws {
        let conflicts = [
            "G2C_DEV_MESSAGE_PROFILE": "needs-planning-v1", "G2C_DEV_PROPOSAL_ID": "old-proposal",
            "G2C_DEV_MEMORY_PROFILE": "{}", "G2C_DEV_MEMORY_MANAGEMENT_URL": Self.endpoint,
            "G2C_DEV_MEMORY_CANDIDATE_URL": Self.endpoint, "G2C_DEV_MEMORY_HISTORY_PROFILE": "history-v1",
            "G2C_DEV_NEEDS_PREVIEW": "synthetic-needs-v1", "G2C_DEV_PLACE_TOOLS": "synthetic-v1",
            "G2C_DEV_FACT_TOOLS": "synthetic-fact-v1", "G2C_M4_LOCAL_HOST": "192.168.1.2",
            "G2C_DEV_API_BASE_URL": "https://api-beta.go2china.space.evil.invalid",
            "G2C_DEV_MEMORY_ERASURE_URL": "https://go2china.space",
        ]
        for (key, value) in conflicts {
            var input = Self.profile
            input[key] = value
            #expect(throws: DevelopmentBetaComposition.Failure.invalidConfiguration, "conflict \(key)") {
                try DevelopmentBetaComposition.read(input)
            }
        }
        var typedHost = Self.profile
        typedHost["G2C_DEV_TYPED_MEMORY_URL"] = "https://api-beta.go2china.space:444"
        #expect(throws: DevelopmentTypedMemoryProfile.ConfigurationFailure.incompleteMode) {
            try DevelopmentBetaComposition.read(typedHost)
        }
    }

    @Test func compositionRequiresTheAccountAndRetirementBoundary() throws {
        let bypasses = [
            "G2C_M4_BETA_COMPOSITION": "true", "G2C_DEV_ACCOUNT_MODE": "0", "G2C_DEV_CLEANUP_PROFILE": "device-v3",
            "G2C_DEV_TOKEN": try token(), "G2C_DEV_ACCOUNTS": "{\"injected\":\"token\"}",
            "G2C_DEV_OFFLINE_WALL_OFFSET": "0", "G2C_DEV_OFFLINE_UPTIME_OFFSET": "0", "G2C_DEV_OFFLINE_TIME_TRUSTED": "1",
        ]
        for (key, value) in bypasses {
            var input = Self.profile
            input[key] = value
            #expect(throws: DevelopmentBetaComposition.Failure.invalidConfiguration, "bypass \(key)") {
                try DevelopmentBetaComposition.read(input)
            }
        }
        let composition = try #require(try DevelopmentBetaComposition.read(Self.profile))
        let owner = try #require(DevelopmentSessionConfiguration.restoring(endpoint: composition.endpoint,
            token: token(subject: "owner"), proposalID: nil, approvedLocalHost: nil, approvedBetaAPI: true))
        let other = try #require(DevelopmentSessionConfiguration.restoring(endpoint: composition.endpoint,
            token: token(subject: "other"), proposalID: nil, approvedLocalHost: nil, approvedBetaAPI: true))
        #expect(owner.environmentID == other.environmentID)
        #expect(owner.accountID != other.accountID)
        #expect(owner.proposalID == nil && other.proposalID == nil)
    }
    #endif
}

struct DevelopmentConfigurationTests {
    @Test func betaServiceRequiresTheExplicitDebugChoiceAndKeepsItsRestoreScope() throws {
        #if DEBUG
        let base=["G2C_DEV_API_BASE_URL":"https://api-beta.go2china.space", "G2C_M4_BETA_API":"1"]
        let canonical=URL(string:"https://api-beta.go2china.space")!
        #if G2C_M4_DEVICE_ACCEPTANCE
        #expect(DevelopmentSessionConfiguration.readEndpoint(base)==canonical)
        #expect(DevelopmentSessionConfiguration.readEndpoint(base.merging(["G2C_DEV_API_BASE_URL":"https://api-beta.go2china.space:443/"]){_,new in new})==canonical)
        #expect(DevelopmentSessionConfiguration.restoring(endpoint:canonical,token:try token(),proposalID:nil,approvedLocalHost:nil,approvedBetaAPI:true)?.endpoint==canonical)
        #else
        #expect(DevelopmentSessionConfiguration.readEndpoint(base)==nil)
        #expect(DevelopmentSessionConfiguration.restoring(endpoint:canonical,token:try token(),proposalID:nil,approvedLocalHost:nil,approvedBetaAPI:true)==nil)
        #endif
        #expect(DevelopmentSessionConfiguration.restoring(endpoint:canonical,token:try token(),proposalID:nil,approvedLocalHost:nil)==nil)
        for raw in ["http://api-beta.go2china.space", "https://api-beta.go2china.space:444", "https://api-beta.go2china.space.evil.invalid", "https://go2china.space", "https://47.83.147.176", "https://api-beta.go2china.space/v1", "https://user@api-beta.go2china.space", "https://api-beta.go2china.space?x=1", "https://api-beta.go2china.space#x"] {
            #expect(DevelopmentSessionConfiguration.readEndpoint(base.merging(["G2C_DEV_API_BASE_URL":raw]){_,new in new})==nil)
        }
        for change in [["G2C_M4_BETA_API":"true"], ["G2C_M4_LOCAL_HOST":"192.168.1.2"], ["G2C_M4_LOCAL_HOST":"api-beta.go2china.space"]] {
            #expect(DevelopmentSessionConfiguration.readEndpoint(base.merging(change){_,new in new})==nil)
        }
        #else
        #expect(DevelopmentSessionConfiguration.read(["G2C_M4_BETA_API":"1", "G2C_DEV_API_BASE_URL":"https://api-beta.go2china.space", "G2C_DEV_TOKEN":try token()])==nil)
        #endif
    }
    @Test func restoredMaterialRetainsOnlyTheOriginallyApprovedLocalHost() throws {
        #if DEBUG
        let endpoint=URL(string:"https://192.168.1.2:18443")!,jwt=try token()
        let restored=DevelopmentSessionConfiguration.restoring(endpoint:endpoint,token:jwt,proposalID:nil,approvedLocalHost:"192.168.1.2")
        #if G2C_M4_DEVICE_ACCEPTANCE
        #expect(restored?.endpoint==endpoint)
        #else
        #expect(restored==nil)
        #endif
        #expect(DevelopmentSessionConfiguration.restoring(endpoint:endpoint,token:jwt,proposalID:nil,approvedLocalHost:nil)==nil)
        #expect(DevelopmentSessionConfiguration.restoring(endpoint:endpoint,token:jwt,proposalID:nil,approvedLocalHost:"192.168.1.3")==nil)
        #endif
    }
    @Test func m4LocalDeviceEndpointRequiresExplicitPrivateHost() throws {
        let host = "192.168.1.2"
        let base = ["G2C_DEV_API_BASE_URL":"https://"+host+":18080", "G2C_M4_LOCAL_HOST":host]
        #if DEBUG
        #if G2C_M4_DEVICE_ACCEPTANCE
        #expect(DevelopmentSessionConfiguration.readEndpoint(base)?.host == host)
        #else
        #expect(DevelopmentSessionConfiguration.readEndpoint(base) == nil)
        #endif
        for change in [["G2C_DEV_API_BASE_URL":"http://192.168.1.2:18080"], ["G2C_M4_LOCAL_HOST":"192.168.1.3"], ["G2C_DEV_API_BASE_URL":"https://8.8.8.8:18080","G2C_M4_LOCAL_HOST":"8.8.8.8"],
            ["G2C_DEV_API_BASE_URL":"https://192.168.1.2"], ["G2C_DEV_API_BASE_URL":"https://192.168.1.2:0"],
            ["G2C_DEV_API_BASE_URL":"https://user:password@192.168.1.2:18080"], ["G2C_DEV_API_BASE_URL":"https://192.168.1.2:18080/v1"],
            ["G2C_DEV_API_BASE_URL":"https://192.168.1.2:18080?key=value"], ["G2C_DEV_API_BASE_URL":"https://192.168.1.2:18080#fragment"]] {
            #expect(DevelopmentSessionConfiguration.readEndpoint(base.merging(change){_,new in new}) == nil)
        }
        #else
        #expect(DevelopmentSessionConfiguration.read(base) == nil)
        #endif
    }

    @Test func historyProfileRequiresVerifiedAccountRootAndReleaseStaysClosed() throws {
        let base = ["G2C_DEV_MEMORY_HISTORY_PROFILE": "history-v1", "G2C_DEV_ACCOUNT_MODE": "1"]
        #if DEBUG
        #expect(try DevelopmentMemoryHistoryProfile.read([:]) == nil)
        #expect(try DevelopmentMemoryHistoryProfile.read(base) != nil)
        for invalid in [["G2C_DEV_MEMORY_HISTORY_PROFILE":"true"], ["G2C_DEV_ACCOUNT_MODE":"0"]] {
            #expect(throws:DevelopmentMemoryHistoryProfile.Failure.invalidProfile) {
                try DevelopmentMemoryHistoryProfile.read(base.merging(invalid){_,new in new})
            }
        }
        #expect(throws:DevelopmentMemoryHistoryProfile.Failure.invalidProfile) {
            try DevelopmentMemoryHistoryProfile.read(["G2C_DEV_MEMORY_HISTORY_PROFILE":"history-v1"])
        }
        #else
        #expect(try DevelopmentMemoryHistoryProfile.read(base) == nil)
        #endif
    }
    @Test func feedbackProfileIsExplicitAndReleaseClosed() throws {
        #if DEBUG
        #expect(try DevelopmentFeedbackProfile.read([:]) == nil)
        #expect(try DevelopmentFeedbackProfile.read(["G2C_DEV_FEEDBACK_PROFILE": "feedback-v1"]) != nil)
        for value in ["", "true", "live", "feedback-v2"] {
            #expect(throws: DevelopmentFeedbackProfile.Failure.invalidProfile) {
                try DevelopmentFeedbackProfile.read(["G2C_DEV_FEEDBACK_PROFILE": value])
            }
        }
        #else
        #expect(try DevelopmentFeedbackProfile.read(["G2C_DEV_FEEDBACK_PROFILE": "feedback-v1"]) == nil)
        #endif
    }
    @Test func offlineProfileIsExplicitBoundedAndDoesNotGrantReleaseAccess() throws {
        let base = ["G2C_DEV_OFFLINE_TRIP": "last-sync-v1", "G2C_DEV_ACCOUNT_MODE": "1"]
        #if DEBUG
        #expect(try DevelopmentOfflineProfile.read([:]) == nil)
        let active = try #require(try DevelopmentOfflineProfile.read(base))
        #expect(active.wallOffset == 0 && active.uptimeOffset == 0 && active.trusted)
        for change in [["G2C_DEV_OFFLINE_TRIP": "other"], ["G2C_DEV_ACCOUNT_MODE": "0"],
                       ["G2C_DEV_OFFLINE_WALL_OFFSET": "+1"], ["G2C_DEV_OFFLINE_UPTIME_OFFSET": "nan"],
                       ["G2C_DEV_OFFLINE_WALL_OFFSET": "315360001"], ["G2C_DEV_OFFLINE_TIME_TRUSTED": "yes"]] {
            let invalid = base.merging(change) { _, new in new }
            #expect(throws: DevelopmentOfflineProfile.Failure.invalidConfiguration) { try DevelopmentOfflineProfile.read(invalid) }
        }
        #expect(throws: DevelopmentOfflineProfile.Failure.invalidConfiguration) { try DevelopmentOfflineProfile.read(["G2C_DEV_OFFLINE_WALL_OFFSET": "1"]) }
        #else
        #expect(try DevelopmentOfflineProfile.read(base) == nil)
        #endif
    }
    @Test func needsPlanningProfileIsExplicitWithoutActivatingDiscussionOrRelease() throws {
        let environment=["G2C_DEV_MESSAGE_PROFILE":"needs-planning-v1"]
        #if DEBUG
        #expect(try DevelopmentMessageProfile.read(environment) == .planning)
        #expect(try !DevelopmentDiscussionProfile.read(environment))
        #else
        #expect(try DevelopmentMessageProfile.read(environment) == nil)
        #endif
    }
    @Test func needsPlanningRequiresExplicitTravelAndSavedNeedsWithoutOtherWriters() throws {
        #if DEBUG
        let environment=["G2C_DEV_TRAVEL_PROFILE":"{\"version\":\"app-travel.1\",\"travel_ids\":[\""+String(repeating:"b",count:32)+"\"]}",
            "G2C_DEV_NEEDS_PROFILE":"manual-v1","G2C_DEV_NEEDS_ID":"visit"]
        let needs=try DevelopmentNeedsProfile.read(environment),travel=try DevelopmentTravelProfile.read(environment)
        #expect(try DevelopmentTypedMode.read(environment,messageProfile:.planning) == nil)
        try DevelopmentMessageProfile.planning.validate(typed:nil,needs:needs,answer:.plain,travel:travel)
        // The existing typed-mode entry still refuses a partial old configuration.
        #expect(throws:DevelopmentTypedMemoryProfile.ConfigurationFailure.incompleteMode) { try DevelopmentTypedMode.read(environment) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.planning.validate(typed:nil,needs:nil,answer:.plain,travel:travel) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.planning.validate(typed:nil,needs:needs,answer:.plain) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.planning.validate(typed:nil,needs:needs,answer:.place,travel:travel) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.planning.validate(typed:nil,needs:needs,answer:.plain,travel:travel,legacyProposal:true) }
        var empty=environment;empty["G2C_DEV_TRAVEL_PROFILE"]="{\"version\":\"app-travel.1\",\"travel_ids\":[]}"
        let noChoices=try DevelopmentTravelProfile.read(empty)
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.planning.validate(typed:nil,needs:needs,answer:.plain,travel:noChoices) }
        for key in ["G2C_DEV_TYPED_MEMORY_PROFILE","G2C_DEV_TYPED_MEMORY_URL"] {
            var mixed=environment;mixed[key]="unaccepted"
            #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentTypedMode.read(mixed,messageProfile:.planning) }
        }
        #endif
    }
    @Test func manualTripProfileIsExplicitAndReleaseDoesNotActivateIt() throws {
        #if DEBUG
        #expect(try DevelopmentTripEditingProfile.read([:]) == nil)
        #expect(try DevelopmentTripEditingProfile.read(["G2C_DEV_TRIP_MANUAL_PROFILE":"manual-v1"]) != nil)
        for invalid in ["", "true", "live", "manual-v2"] {
            #expect(throws:DevelopmentTripEditingProfile.Failure.invalidProfile) {
                try DevelopmentTripEditingProfile.read(["G2C_DEV_TRIP_MANUAL_PROFILE":invalid])
            }
        }
        #else
        #expect(try DevelopmentTripEditingProfile.read(["G2C_DEV_TRIP_MANUAL_PROFILE":"manual-v1"]) == nil)
        #endif
    }
    @Test func scopedProfileIsExplicitAndCannotActivateOldDiscussionOrRelease() throws {
        let key="G2C_DEV_MESSAGE_PROFILE"
        #if DEBUG
        #expect(try DevelopmentMessageProfile.read([key:"trip-edit-v1"]) == .edit)
        #expect(try DevelopmentMessageProfile.read([key:"trip-edit-result-v1"]) == .editResults)
        #expect(try !DevelopmentDiscussionProfile.read([key:"trip-edit-v1"]))
        #expect(try DevelopmentMessageProfile.read([:]) == nil)
        #else
        #expect(try DevelopmentMessageProfile.read([key:"trip-edit-v1"]) == nil)
        #expect(try DevelopmentMessageProfile.read([key:"trip-edit-result-v1"]) == nil)
        #endif
    }
    @Test func scopedConfigurationRequiresNamespaceChoicesSavedNeedsAndCompatibleFormat() throws {
        #if DEBUG
        let raw=String(repeating:"b",count:32)
        let environment=["G2C_DEV_TRAVEL_PROFILE":"{\"version\":\"app-travel.1\",\"travel_ids\":[\""+raw+"\"]}",
            "G2C_DEV_TYPED_MEMORY_PROFILE":"{\"version\":\"app-memory.2\",\"subjects\":[\"self\"],\"slots\":{\"pace\":{\"kind\":\"preference\",\"collection_allowed\":true,\"semantic_resolved\":true}},\"extents\":[\"long_term\",\"current\"]}",
            "G2C_DEV_TYPED_MEMORY_URL":"http://127.0.0.1:8765",
            "G2C_DEV_NEEDS_PROFILE":"manual-v1","G2C_DEV_NEEDS_ID":"visit"]
        let typed=try DevelopmentTypedMode.read(environment),needs=try DevelopmentNeedsProfile.read(environment)
        try DevelopmentMessageProfile.edit.validate(typed:typed,needs:needs,answer:.plain)
        try DevelopmentMessageProfile.editResults.validate(typed:typed,needs:needs,answer:.plain)
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.editResults.validate(typed:nil,needs:needs,answer:.plain) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.editResults.validate(typed:typed,needs:nil,answer:.plain) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.editResults.validate(typed:typed,needs:needs,answer:.place) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.editResults.validate(typed:typed,needs:needs,answer:.plain,legacyProposal:true) }
        try DevelopmentMessageProfile.edit.validate(typed:typed,needs:needs,answer:.plain,legacyProposal:true)
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.edit.validate(typed:nil,needs:needs,answer:.plain) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.edit.validate(typed:typed,needs:nil,answer:.plain) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.edit.validate(typed:typed,needs:needs,answer:.place) }
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.discussion.validate(typed:typed,needs:needs,answer:.plain) }
        var empty=environment;empty["G2C_DEV_TRAVEL_PROFILE"]="{\"version\":\"app-travel.1\",\"travel_ids\":[]}"
        let missing=try DevelopmentTypedMode.read(empty)
        #expect(throws:DevelopmentDiscussionProfile.Failure.incompatibleProfiles) { try DevelopmentMessageProfile.edit.validate(typed:missing,needs:needs,answer:.plain) }
        #endif
    }
    @Test func discussionProfileIsExplicitAndReleaseStaysClosed() throws {
        #if DEBUG
        #expect(try !DevelopmentDiscussionProfile.read([:]))
        #expect(try DevelopmentDiscussionProfile.read(["G2C_DEV_MESSAGE_PROFILE":"trip-discussion-v1"]))
        for value in ["", "true", "message-trip.2", "trip-discussion-v2", "live"] {
            #expect(throws:DevelopmentDiscussionProfile.Failure.invalidProfile) { try DevelopmentDiscussionProfile.read(["G2C_DEV_MESSAGE_PROFILE":value]) }
        }
        #else
        #expect(try !DevelopmentDiscussionProfile.read(["G2C_DEV_MESSAGE_PROFILE":"trip-discussion-v1"]))
        #endif
    }
    @Test func factAndPlaceProfilesAreExplicitExclusiveAndNeverEnableRelease() throws {
        #if DEBUG
        #expect(try DevelopmentSessionConfiguration.toolAnswerProfile([:]) == .plain)
        #expect(try DevelopmentSessionConfiguration.toolAnswerProfile(["G2C_DEV_FACT_TOOLS":"synthetic-fact-v1"]) == .fact)
        #expect(try DevelopmentSessionConfiguration.toolAnswerProfile(["G2C_DEV_PLACE_TOOLS":"synthetic-v1"]) == .place)
        for value in ["", "live", "true", "synthetic-v1"] {
            #expect(throws:DevelopmentSessionConfiguration.DevelopmentToolsFailure.invalidProfile) {
                try DevelopmentSessionConfiguration.toolAnswerProfile(["G2C_DEV_FACT_TOOLS":value])
            }
        }
        #expect(throws:DevelopmentSessionConfiguration.DevelopmentToolsFailure.invalidProfile) {
            try DevelopmentSessionConfiguration.toolAnswerProfile(["G2C_DEV_FACT_TOOLS":"synthetic-fact-v1","G2C_DEV_PLACE_TOOLS":"synthetic-v1"])
        }
        #else
        #expect(DevelopmentSessionConfiguration.read(["G2C_DEV_FACT_TOOLS":"synthetic-fact-v1","G2C_DEV_API_BASE_URL":"http://127.0.0.1:8765","G2C_DEV_TOKEN":try token()]) == nil)
        #endif
    }
    @Test func needsSelectionAndPreviewAreExplicitAndExclusive() throws {
        let profile = ["G2C_DEV_NEEDS_PROFILE": "manual-v1", "G2C_DEV_NEEDS_ID": "needs:fixture", "G2C_DEV_NEEDS_PREVIEW": "synthetic-needs-v1"]
        #if DEBUG
        #expect(try DevelopmentNeedsProfile.read([:]) == nil)
        #expect(try DevelopmentNeedsProfile.read(profile)?.needsID == "needs:fixture")
        #expect(try DevelopmentSessionConfiguration.toolAnswerProfile(profile) == .needs)
        for id in ["", "../other", "has space", "trailing\n", String(repeating: "a", count: 97)] {
            var invalid = profile; invalid["G2C_DEV_NEEDS_ID"] = id
            #expect(throws: DevelopmentNeedsProfile.Failure.invalidProfile) { try DevelopmentNeedsProfile.read(invalid) }
        }
        for key in ["G2C_DEV_NEEDS_PROFILE", "G2C_DEV_NEEDS_ID"] {
            var missing = profile; missing.removeValue(forKey: key)
            #expect(throws: (any Error).self) { try DevelopmentNeedsProfile.read(missing) }
        }
        for (key, value) in [("G2C_DEV_FACT_TOOLS", "synthetic-fact-v1"), ("G2C_DEV_PLACE_TOOLS", "synthetic-v1")] {
            var mixed = profile; mixed[key] = value
            #expect(throws: DevelopmentSessionConfiguration.DevelopmentToolsFailure.invalidProfile) { try DevelopmentSessionConfiguration.toolAnswerProfile(mixed) }
        }
        #expect(throws: (any Error).self) { try DevelopmentSessionConfiguration.toolAnswerProfile(["G2C_DEV_NEEDS_PREVIEW": "synthetic-needs-v1"]) }
        #else
        #expect(try DevelopmentNeedsProfile.read(profile) == nil)
        var complete = profile
        complete["G2C_DEV_API_BASE_URL"] = "http://127.0.0.1:8765"
        complete["G2C_DEV_TOKEN"] = try token()
        #expect(DevelopmentSessionConfiguration.read(complete) == nil)
        #endif
    }
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
