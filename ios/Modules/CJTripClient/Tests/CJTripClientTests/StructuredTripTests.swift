import Foundation
import Testing
@testable import CJTripClient

@Suite @MainActor struct StructuredTripTests {
    struct Fixture: Decodable {
        let name: String
        let canonical_utf8_base64: String
        let sha256: String
        let title: String
        var bytes: Data { Data(base64Encoded: canonical_utf8_base64)! }
    }
    let trace = "B35279D6-8B42-466D-A55D-8A16B64BB270"
    func fixtures() throws -> [Fixture] {
        let url = try #require(Bundle.module.url(forResource: "STRUCTURED-V1", withExtension: "json", subdirectory: "Fixtures"))
        return try JSONDecoder().decode([Fixture].self, from: Data(contentsOf: url))
    }
    func fixture(_ name: String) throws -> Fixture {
        let values = try fixtures(); return try #require(values.first { $0.name == name })
    }
    func object(_ name: String) throws -> [String: Any] {
        let raw = try fixture(name).bytes, value = try JSONSerialization.jsonObject(with: raw)
        return try #require(value as? [String: Any])
    }
    func canonical(_ value: [String: Any]) throws -> Data {
        let raw = try JSONSerialization.data(withJSONObject: value)
        var parser = StrictTripJSON(bytes: Array(raw))
        return try tripCanonicalJSON(parser.document())
    }
    func changedItem(_ name: String = "unknown", _ change: (inout [String: Any]) -> Void) throws -> Data {
        var doc = try object(name), items = doc["items"] as! [[String: Any]]
        change(&items[0]); doc["items"] = items
        return try canonical(doc)
    }

    @Test func officialPythonGoldensPreserveCanonicalBytesAndUnicode() throws {
        for fixture in try fixtures() {
            let doc = try StructuredTripDocument.decode(fixture.bytes)
            #expect(doc.originalUTF8 == fixture.bytes)
            #expect(doc.contentSHA256 == fixture.sha256)
            #expect(Array(doc.title.utf8) == Array(fixture.title.utf8))
        }
    }
    @Test func unknownDoesNotInferDatesFromTextOrUnlockItems() throws {
        let doc = try StructuredTripDocument.decode(fixture("unknown").bytes), item = try #require(doc.items.first)
        #expect(item.text.contains("Tomorrow 09:00"))
        #expect(item.start.date == .unknown && item.start.time == .unknown)
        #expect(item.start.timezone == .unknown && item.start.utcOffset == .unknown)
        #expect(item.fixed == .unknown && item.fixed != .known(false))
        #expect(item.sourceCategory == .user_provided && item.sourceReferences.isEmpty)
    }
    @Test func minutePrecisionIsPreservedOnlyInTheNewVersion() throws {
        let doc = try StructuredTripDocument.decode(fixture("minute").bytes)
        #expect(doc.version == .needsBound && doc.items[0].start.time == .known("23:00"))
        #expect(doc.items[0].end.utcOffset == .known("+08:00"))
        var old = try object("minute"); old["content_version"] = "structured.1"
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(canonical(old)) }
    }
    @Test func allObservationStatesStayDistinct() throws {
        let raw = try changedItem { item in
            var schedule = item["schedule"] as! [String: Any], start = schedule["start"] as! [String: Any]
            start["date"] = ["state": "missing"]
            start["time"] = ["state": "uncertain", "note": "user has not decided / 尚未确定"]
            schedule["start"] = start; item["schedule"] = schedule; item["fixed"] = ["state": "known", "value": false]
        }
        let item = try StructuredTripDocument.decode(raw).items[0]
        #expect(item.start.date == .missing && item.start.time == .uncertain("user has not decided / 尚未确定"))
        #expect(item.fixed == .known(false))
    }
    @Test func invalidObservationPayloadsNeverCoerce() throws {
        let values: [[String: Any]] = [
            ["state": "unknown", "value": false], ["state": "missing", "note": "not allowed"],
            ["state": "uncertain", "note": ""], ["state": "known", "value": 0],
            ["state": "known", "value": "false"], ["state": "new_state"]]
        for value in values {
            let raw = try changedItem { $0["fixed"] = value }
            #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(raw) }
        }
    }
    @Test func impossibleLocalFieldsAndImplicitZonesReject() throws {
        for (field, value) in [("date", "2026-02-30"), ("time", "24:00:00"), ("time", "23:59:60"),
                                ("timezone", "localtime"), ("timezone", "Factory"), ("timezone", "No/Such_Zone"),
                                ("utc_offset", "+99:00")] {
            let raw = try changedItem("explicit") { item in
                var schedule = item["schedule"] as! [String: Any], start = schedule["start"] as! [String: Any]
                start[field] = ["state": "known", "value": value]; schedule["start"] = start; item["schedule"] = schedule
            }
            #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(raw) }
        }
    }
    @Test func versionsIDsAndUnknownFieldsRejectWithoutFallback() throws {
        var unknown = try object("unknown"); unknown["content_version"] = "structured.99"
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(canonical(unknown)) }
        unknown = try object("unknown"); unknown["owner"] = "caller"
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(canonical(unknown)) }
        unknown = try object("unknown"); var items = unknown["items"] as! [[String: Any]]; items.append(items[0]); unknown["items"] = items
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(canonical(unknown)) }
        let invalidID = try changedItem { $0["id"] = "wrong / id" }
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(invalidID) }
        let original = try fixture("unknown").bytes
        let duplicate = Data("{\"content_version\":\"structured.1\",".utf8) + original.dropFirst()
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(duplicate) }
    }
    @Test func originalSourcesRemainBoundAndCannotAcquireVerification() throws {
        let doc = try StructuredTripDocument.decode(fixture("sources").bytes)
        #expect(!doc.sources.isEmpty && doc.items.contains { $0.sourceCategory == .queried })
        let raw = try changedItem("sources") { $0["source_refs"] = ["unknown-source"] }
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(raw) }
        var changed = try object("sources"), sources = changed["sources"] as! [[String: Any]]
        sources[0]["text"] = "not the original source"; changed["sources"] = sources
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripDocument.decode(canonical(changed)) }
    }
    @Test func emptyDiscoveryPagesMayStillAdvanceAcrossLegacyRecords() throws {
        let bytes = Data("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\"\(trace)\",\"trips\":[],\"next_after\":\"legacy.2\"}".utf8)
        let page = try StructuredTripReadV1.page(bytes, requestID: trace)
        #expect(page.trips.isEmpty && page.nextAfter == "legacy.2")
    }
    @Test func discoveryIntegerTokensCannotRoundOrBecomeBooleans() throws {
        func page(_ token: String) -> Data {
            Data("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\"\(trace)\",\"trips\":[{\"trip_id\":\"trip:1\",\"version\":\(token),\"content_version\":\"structured.2\",\"title\":\"SYNTHETIC\",\"content_sha256\":\"\(String(repeating: "a", count: 64))\"}],\"next_after\":null}".utf8)
        }
        #expect(try StructuredTripReadV1.page(page("9007199254740993"), requestID: trace).trips[0].version == 9_007_199_254_740_993)
        for token in ["1.0", "1e0", "true", "\"1\"", "0", "-1", "9223372036854775808"] {
            #expect(throws: TripFailure.invalidResponse) { try StructuredTripReadV1.page(page(token), requestID: trace) }
        }
    }
    @Test func detailChecksContentDigestAndOriginalTrace() throws {
        let f = try fixture("minute"), text = String(decoding: f.bytes, as: UTF8.self)
        func detail(_ hash: String) -> Data {
            Data("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\"\(trace)\",\"trip\":{\"trip_id\":\"trip:1\",\"version\":7,\"content_sha256\":\"\(hash)\",\"content\":\(text)}}".utf8)
        }
        let value = try StructuredTripReadV1.detail(detail(f.sha256), requestID: trace)
        let record = try #require(value)
        #expect(record.version == 7 && record.document.originalUTF8 == f.bytes)
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripReadV1.detail(detail(String(repeating: "0", count: 64)), requestID: trace) }
        #expect(throws: TripFailure.invalidResponse) { try StructuredTripReadV1.detail(detail(f.sha256), requestID: "109890E1-FEC2-482F-9549-BE5E76D425C9") }
        let missing = Data("{\"version\":\"TRIP-structured-read.1\",\"request_id\":\"\(trace)\",\"trip\":null}".utf8)
        #expect(try StructuredTripReadV1.detail(missing, requestID: trace) == nil)
    }
}
