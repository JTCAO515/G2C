import Foundation
import CJStrictJSON

public enum RichTripContentVersion: String, Sendable {
    case first = "structured.1", second = "structured.2", calendar = "structured.3", rich = "structured.4"
}
public enum RichStructuredTripContent: Sendable {
    case legacy(StructuredTripDocument)
    case calendar(CalendarStructuredTripDocument)
    case rich(RichStructuredTripDocument)

    public var title: String {
        switch self { case .legacy(let value): value.title; case .calendar(let value): value.title; case .rich(let value): value.title }
    }
    public var originalUTF8: Data {
        switch self { case .legacy(let value): value.originalUTF8; case .calendar(let value): value.originalUTF8; case .rich(let value): value.originalUTF8 }
    }
    public var contentSHA256: String { digest(originalUTF8) }
}
public struct RichStructuredTripSummary: Sendable {
    public let tripID: String
    public let version: Int
    public let contentVersion: RichTripContentVersion
    public let contentSHA256: String
    public let title: String
    public let calendar: CalendarStructuredTripDocument.CalendarState?
    public let dayCount: Int?
}
public struct RichStructuredTripRecord: Sendable {
    public let tripID: String
    public let version: Int
    public let content: RichStructuredTripContent
}
public struct RichStructuredTripPage: Sendable {
    public let requestID: String
    public let trips: [RichStructuredTripSummary]
    public let nextAfter: String?
}

/// Frozen read.3 data only. It does not install an endpoint, activate a reader,
/// establish source eligibility or mint any accepted editing/protected source.
public enum RichStructuredTripReadV3 {
    public static func page(_ bytes: Data, requestID: String) throws -> RichStructuredTripPage {
        let root = try envelope(bytes, fields: "version request_id trips next_after", requestID: requestID)
        let rows = try root.required("trips").elements()
        guard rows.count <= 100 else { throw TripFailure.invalidResponse }
        var ids = Set<String>()
        let summaries = try rows.map { raw -> RichStructuredTripSummary in
            let row = try raw.fields("trip_id version content_version title content_sha256 calendar day_count")
            let id = try tripWireID(row.required("trip_id"))
            let hash = try row.required("content_sha256").text()
            guard ids.insert(id).inserted, tripHash(hash),
                  let contentVersion = RichTripContentVersion(rawValue: try row.required("content_version").text()) else {
                throw TripFailure.invalidResponse
            }
            let calendar: CalendarStructuredTripDocument.CalendarState?
            let dayCount: Int?
            switch contentVersion {
            case .first, .second:
                guard case .null = try row.required("calendar"), case .null = try row.required("day_count") else {
                    throw TripFailure.invalidResponse
                }
                calendar = nil; dayCount = nil
            case .calendar, .rich:
                calendar = try CalendarStructuredTripReadV2.readCalendar(row.required("calendar"))
                dayCount = Int(try row.required("day_count").integer(1...Int64.max))
            }
            return try RichStructuredTripSummary(tripID: id, version: tripWireVersion(row.required("version")),
                contentVersion: contentVersion, contentSHA256: hash, title: boundedTripText(row.required("title"), maximum: 120),
                calendar: calendar, dayCount: dayCount)
        }
        return try RichStructuredTripPage(requestID: requestID, trips: summaries,
                                         nextAfter: root.required("next_after").nullable(tripWireID))
    }

    public static func detail(_ bytes: Data, requestID: String) throws -> RichStructuredTripRecord? {
        let root = try envelope(bytes, fields: "version request_id trip", requestID: requestID)
        return try root.required("trip").nullable { raw in
            let row = try raw.fields("trip_id version content_sha256 content")
            let node = try row.required("content")
            let fields = try node.object(), input = tripCanonicalJSON(node)
            let content: RichStructuredTripContent
            switch try fields.required("content_version").text() {
            case "structured.1", "structured.2": content = .legacy(try StructuredTripDocument.decode(input))
            case "structured.3": content = .calendar(try CalendarStructuredTripDocument.decode(input))
            case "structured.4": content = .rich(try RichStructuredTripDocument.decode(input))
            default: throw TripFailure.invalidResponse
            }
            let hash = try row.required("content_sha256").text()
            guard tripHash(hash), hash == content.contentSHA256 else { throw TripFailure.invalidResponse }
            return try RichStructuredTripRecord(tripID: tripWireID(row.required("trip_id")),
                version: tripWireVersion(row.required("version")), content: content)
        }
    }

    private static func envelope(_ bytes: Data, fields: String, requestID: String) throws -> [String: TripJSONValue] {
        // Content retains its own 1 MB / 32-depth limit. Allow the outer envelope
        // overhead without shrinking that frozen content limit.
        guard !bytes.isEmpty, bytes.count <= 4_500_000, UUID(uuidString: requestID) != nil else {
            throw TripFailure.invalidResponse
        }
        var reader = StrictJSONReader<RichTripJSONPolicy>(bytes: Array(bytes))
        let value = try reader.document()
        try factBounds(value, maxDepth: 64, maxNodes: 65536)
        let root = try value.fields(fields)
        guard try root.required("version").text() == "TRIP-structured-read.3",
              try root.required("request_id").text() == requestID else { throw TripFailure.invalidResponse }
        return root
    }
}
