import Foundation
import Testing
import CJMessageHTTP
import CJTripClient
@testable import CJManualPreviewClient

func scopedFixture() throws -> Data {
    try Data(contentsOf: Bundle.module.url(forResource: "SCOPED-DISCOVERY-V1", withExtension: "json", subdirectory: "Fixtures")!)
}
func scopedReference(_ bytes: Data) throws -> MessageEditReference {
    let json = try ScopedWireJSON(bytes, maximumBytes: 4_000_000)
    let value = try #require(json.object["discovery"] as? [String: Any])
    return try MessageEditReference.decodeResponseReference(canonical(["reference": value["reference"]!]), maximumBytes: 65536)
}
func scopedDecode(_ bytes: Data, original: MessageEditReference? = nil) throws -> ScopedDiscovery {
    try .decode(bytes, requestID: "00000000-0000-4000-8000-000000000337", original: original ?? scopedReference(bytes))
}
struct ScopedDiscoveryTests {
    @Test func preservesOriginalAssociationDiffUnknownAndBytes() throws {
        let bytes = try scopedFixture(), value = try scopedDecode(bytes)
        let candidate = try #require(value.candidate)
        #expect(value.state == .published && value.responseUTF8 == bytes && candidate.discoveryUTF8 == bytes)
        #expect(candidate.expectedVersion == 2 && candidate.before.items[0].text == candidate.after.items[0].text)
        #expect(candidate.before.items[1].text != candidate.after.items[1].text)
        #expect(candidate.feasibilityStatus == "UNKNOWN" && candidate.checks[0].missing == ["route evidence"])
    }
    @Test(arguments: ["proposal_id", "trip_id", "expected_version", "candidate_hash", "content", "scope", "diff", "feasibility"])
    func candidateCorruptionWithholdsWholeResponse(field: String) throws {
        let bytes = try scopedFixture(), original = try scopedReference(bytes)
        var root = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        var d = root["discovery"] as! [String: Any], p = d["proposal"] as! [String: Any]
        p[field] = NSNull(); d["proposal"] = p; root["discovery"] = d
        #expect(throws: (any Error).self) { try scopedDecode(canonical(root), original: original) }
    }
    @Test(arguments: ["message_id", "run_id", "input_sha256", "generation", "trip_context", "namespace", "needs_reference", "selection_epoch"])
    func changedOriginalReferenceIsNeverAReplacement(field: String) throws {
        let bytes = try scopedFixture(), original = try scopedReference(bytes)
        var root = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        var d = root["discovery"] as! [String: Any], ref = d["reference"] as! [String: Any]
        ref[field] = NSNull(); d["reference"] = ref; root["discovery"] = d
        #expect(throws: (any Error).self) { try scopedDecode(canonical(root), original: original) }
    }
    @Test func unknownIsNotAbsenceAndFutureStateFailsClosed() throws {
        let bytes = try scopedFixture(), original = try scopedReference(bytes)
        var root = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        var d = root["discovery"] as! [String: Any]
        d["state"] = "unknown"; d["run_status"] = "unknown"; d["draft_outcome"] = "provider_unknown"; d["proposal"] = NSNull(); root["discovery"] = d
        let unknown = try scopedDecode(canonical(root), original: original)
        #expect(unknown.state == .unknown && unknown.candidate == nil)
        d["state"] = "no_candidate"; root["discovery"] = d
        #expect(throws: (any Error).self) { try scopedDecode(canonical(root), original: original) }
        d["state"] = "future"; root["discovery"] = d
        #expect(throws: (any Error).self) { try scopedDecode(canonical(root), original: original) }
    }
    @Test func unselectedChangesAndBooleanVersionRefuse() throws {
        let bytes = try scopedFixture(), original = try scopedReference(bytes)
        let text = String(decoding: bytes, as: UTF8.self)
        #expect(throws: (any Error).self) { try scopedDecode(Data(text.replacingOccurrences(of: "\"expected_version\":2", with: "\"expected_version\":true").utf8), original: original) }
        #expect(throws: (any Error).self) { try scopedDecode(Data("{\"version\":\"duplicate\",".utf8) + bytes.dropFirst(), original: original) }
    }
}

struct ScopedActualResponseTests {
    @Test func actualCProtectedRuntimeResponse() throws {
        let bytes = try Data(contentsOf: Bundle.module.url(forResource: "SCOPED-DISCOVERY-RUNTIME-V1", withExtension: "json", subdirectory: "Fixtures")!)
        let json = try ScopedWireJSON(bytes, maximumBytes: 4_000_000)
        let value = try ScopedDiscovery.decode(bytes, requestID: ScopedWireJSON.text(json.object["request_id"]), original: scopedReference(bytes))
        #expect(value.state == .published && value.candidate?.feasibilityStatus == "UNKNOWN")
    }
}

struct ScopedCCompatibilityTests {
    @Test(arguments: ["SOURCES", "REORDER"])
    func acceptsOriginalCCoreCandidates(kind: String) throws {
        let bytes = try Data(contentsOf: Bundle.module.url(forResource: "SCOPED-" + kind + "-V1", withExtension: "json", subdirectory: "Fixtures")!)
        let value = try scopedDecode(bytes), candidate = try #require(value.candidate)
        if kind == "SOURCES" { #expect(candidate.before.sources.count == 1 && candidate.after.sources.isEmpty) }
        else { #expect(candidate.before.items.map(\.id) != candidate.after.items.map(\.id)) }
    }
}

struct ScopedProtectedContentTests {
    @Test func afterContentAndUnselectedChangesCannotHideInTheDiff() throws {
        let bytes = try scopedFixture(), original = try scopedReference(bytes)
        var root = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        var d = root["discovery"] as! [String: Any], p = d["proposal"] as! [String: Any], diff = p["diff"] as! [String: Any]
        var after = diff["after"] as! [String: Any], items = after["items"] as! [[String: Any]]
        items[0]["text"] = "Changed outside the selected range"
        after["items"] = items; diff["after"] = after; p["diff"] = diff; d["proposal"] = p; root["discovery"] = d
        #expect(throws: (any Error).self) { try scopedDecode(canonical(root), original: original) }
        p["content"] = after; d["proposal"] = p; root["discovery"] = d
        #expect(throws: (any Error).self) { try scopedDecode(canonical(root), original: original) }
    }
}
