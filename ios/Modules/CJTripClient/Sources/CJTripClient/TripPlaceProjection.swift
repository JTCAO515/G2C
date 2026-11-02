import Foundation

/// Read-only projection of the persisted provenance snapshot in a structured Trip.
/// This is neither a PLACE result nor permission to query a provider.
public struct TripPlaceProjection: Sendable, Identifiable {
    public let id: String
    public let provider: String
    public let providerID: String
    public let nameZH: String
    public let addressZH: PlaceObservedV1<String>
    public let officialNameEN: PlaceObservedV1<String>
    public let officialAddressEN: PlaceObservedV1<String>
    public let evidenceLevel: String
    public let snapshotSHA256: String
    public let coordinateState: PlaceFieldStateV1
    public let rawCoordinate: String?
    public let longitudeText: String?
    public let latitudeText: String?
    public let crs: String?
    /// Only a validated GCJ-02 declaration is eligible for a marker. No conversion.
    public let markerCoordinate: PlaceCoordinateV1?

    public static func read(from document: StructuredTripDocument) throws -> [Self] {
        try document.sources.filter { $0.kind == .place }.map { source in
            // StructuredTripDocument already verified the original snapshot bytes/hash.
            let bytes = Data(base64Encoded: source.snapshot_utf8_base64)!
            var parser = StrictTripJSON(bytes: Array(bytes))
            let snapshot = try parser.document().fields("display_text record")
            let record = try snapshot.required("record").fields("source query place")
            let provenance = try record.required("source").object()
            let place = try record.required("place").fields("provider provider_id name_zh address_zh coordinate entrance_coordinate exit_coordinate parent_id navigation_id typecode official_name_en official_address_en")
            let provider = try place.required("provider").safeText(128)
            let providerID = try place.required("provider_id").identifier()
            let name = try place.required("name_zh").safeText()
            guard provider == "gaode", try provenance.required("provider").text() == provider,
                  try same(provenance.required("request_ref").text(), source.reference),
                  try provenance.required("evidence").text() == source.evidence_level.rawValue,
                  same(name, source.text), try same(snapshot.required("display_text").text(), source.text) else { throw TripFailure.invalidResponse }
            let coordinate = try place.required("coordinate").fields("state value")
            guard let state = PlaceFieldStateV1(rawValue: try coordinate.required("state").text()) else { throw TripFailure.invalidResponse }
            let raw: String?, longitude: String?, latitude: String?, crs: String?, marker: PlaceCoordinateV1?
            if state == .present {
                let value = try coordinate.required("value").fields("raw longitude latitude crs")
                raw = try value.required("raw").safeText(128)
                longitude = try value.required("longitude").safeText(64)
                latitude = try value.required("latitude").safeText(64)
                crs = try value.required("crs").safeText(64)
                marker = crs == "GCJ-02" ? try PlaceCoordinateV1.read(coordinate.required("value")) : nil
            } else {
                guard case .null = try coordinate.required("value") else { throw TripFailure.invalidResponse }
                raw = nil; longitude = nil; latitude = nil; crs = nil; marker = nil
            }
            return try .init(id: source.id, provider: provider, providerID: providerID, nameZH: name,
                addressZH: .read(place.required("address_zh")) { try $0.safeText() },
                officialNameEN: .read(place.required("official_name_en")) { try $0.safeText() },
                officialAddressEN: .read(place.required("official_address_en")) { try $0.safeText() },
                evidenceLevel: source.evidence_level.rawValue, snapshotSHA256: source.snapshot_sha256,
                coordinateState: state, rawCoordinate: raw, longitudeText: longitude, latitudeText: latitude,
                crs: crs, markerCoordinate: marker)
        }
    }
}
