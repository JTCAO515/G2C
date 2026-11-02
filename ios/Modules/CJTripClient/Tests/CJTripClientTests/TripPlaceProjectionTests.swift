import Foundation
import Testing
import CryptoKit
import CJAPI
@testable import CJTripClient

struct TripPlaceProjectionTests {
    private func document(crs: String = "GCJ-02", missing: Bool = false, wrongID: Bool = false, noPlaces: Bool = false) throws -> StructuredTripDocument {
        let url = try #require(Bundle.module.url(forResource: "provenance", withExtension: "json", subdirectory: "Fixtures"))
        let proposal = try JSONDecoder().decode(Components.Schemas.SourceTripProposalSnapshot.self, from: Data(contentsOf: url))
        guard case .SourceDocumentV1(let original) = proposal.document else { throw TripFailure.invalidResponse }
        var source = try #require(original.sources.first { $0.kind == .place })
        let bytes = try #require(Data(base64Encoded: source.snapshot_utf8_base64))
        var snapshot = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        var record = try #require(snapshot["record"] as? [String: Any])
        var place = try #require(record["place"] as? [String: Any])
        if missing { place["coordinate"] = ["state": "unknown", "value": NSNull()] }
        else {
            var observed = try #require(place["coordinate"] as? [String: Any])
            var coordinate = try #require(observed["value"] as? [String: Any])
            coordinate["crs"] = crs; observed["value"] = coordinate; place["coordinate"] = observed
        }
        if wrongID { place["name_zh"] = "another place" }
        record["place"] = place; snapshot["record"] = record
        let data = try canonical(snapshot)
        source.snapshot_utf8_base64 = data.base64EncodedString()
        source.snapshot_sha256 = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        let encoder = JSONEncoder()
        let sourceObject = try JSONSerialization.jsonObject(with: encoder.encode(source))
        let unknown: [String: String] = ["state": "unknown"]
        let event = Dictionary(uniqueKeysWithValues: ["date", "time", "timezone", "utc_offset"].map { ($0, unknown) })
        let item: [String: Any] = ["id": "item-place", "text": noPlaces ? "UNKNOWN" : source.text,
            "verification": "pending", "evidence": [], "schedule": ["start": event, "end": event], "fixed": unknown,
            "source_category": noPlaces ? "unknown" : "queried", "source_refs": noPlaces ? [] : [source.id]]
        return try StructuredTripDocument.decode(canonical(["content_version": "structured.1", "title": "Synthetic", "items": [item], "sources": noPlaces ? [] : [sourceObject]]))
    }
    private func canonical(_ object: Any) throws -> Data {
        let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes])
        var parser = StrictTripJSON(bytes: Array(data))
        return try tripCanonicalJSON(parser.document())
    }
    @Test func textAndMarkerShareOriginalSourceIdentityAndStrings() throws {
        let doc = try document()
        let places = try TripPlaceProjection.read(from: doc)
        let row = try #require(places.first), coordinate = try #require(row.markerCoordinate)
        #expect(places.count == 1 && row.providerID == "SYNTH_A" && row.nameZH == "合成公园")
        #expect(row.addressZH.value == "合成路" && row.officialNameEN.state == .unknown)
        #expect(row.rawCoordinate == "116.1,39.1" && coordinate.raw == row.rawCoordinate)
        #expect(coordinate.longitude.text == row.longitudeText && coordinate.latitude.text == row.latitudeText)
        #expect(row.snapshotSHA256 == doc.sources[0].snapshot_sha256)
    }
    @Test func otherCRSIsRetainedButNeverProducesMarker() throws {
        let rows = try TripPlaceProjection.read(from: document(crs: "WGS84"))
        let row = try #require(rows.first)
        #expect(row.markerCoordinate == nil && row.crs == "WGS84" && row.rawCoordinate == "116.1,39.1")
    }
    @Test func unknownAndAbsentSourcesNeverBecomePoints() throws {
        let rows = try TripPlaceProjection.read(from: document(missing: true))
        #expect(rows.count == 1 && rows[0].coordinateState == .unknown && rows[0].markerCoordinate == nil)
        let empty = try TripPlaceProjection.read(from: document(noPlaces: true))
        #expect(empty.isEmpty)
    }
    @Test func mismatchedSnapshotDisplayIsRejected() throws {
        let doc = try document(wrongID: true)
        #expect(throws: TripFailure.invalidResponse) { try TripPlaceProjection.read(from: doc) }
    }
}
