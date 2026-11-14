import Foundation
import CJAPI

public enum CalendarTripContentVersion: String, Sendable { case first = "structured.1", second = "structured.2", calendar = "structured.3" }

public enum CalendarStructuredTripContent: Sendable {
    case legacy(StructuredTripDocument)
    case calendar(CalendarStructuredTripDocument)

    public var title: String {
        switch self { case .legacy(let value): value.title; case .calendar(let value): value.title }
    }
    public var originalUTF8: Data {
        switch self { case .legacy(let value): value.originalUTF8; case .calendar(let value): value.originalUTF8 }
    }
    public var contentSHA256: String { digest(originalUTF8) }
}

public struct CalendarStructuredTripSummary: Sendable {
    public let tripID: String
    public let version: Int
    public let contentVersion: CalendarTripContentVersion
    public let contentSHA256: String
    public let title: String
    public let calendar: CalendarStructuredTripDocument.CalendarState?
    public let dayCount: Int?
}
public struct CalendarStructuredTripRecord: Sendable {
    public let tripID: String
    public let version: Int
    public let content: CalendarStructuredTripContent
}
public struct CalendarStructuredTripPage: Sendable {
    public let requestID: String
    public let trips: [CalendarStructuredTripSummary]
    public let nextAfter: String?
}

/// Frozen TRIP-structured-read.2 data only. No legacy source or editing token is minted.
public enum CalendarStructuredTripReadV2 {
    public static func page(_ bytes: Data, requestID: String) throws -> CalendarStructuredTripPage {
        let root = try envelope(bytes, fields: "version request_id trips next_after", requestID: requestID)
        let values = try root.required("trips").elements()
        guard values.count <= 100 else { throw TripFailure.invalidResponse }
        var ids = Set<String>()
        let rows = try values.map { raw -> CalendarStructuredTripSummary in
            let row = try raw.fields("trip_id version content_version title content_sha256 calendar day_count")
            let id = try tripWireID(row.required("trip_id"))
            let hash = try row.required("content_sha256").text()
            guard ids.insert(id).inserted, tripHash(hash),
                  let version = CalendarTripContentVersion(rawValue: try row.required("content_version").text()) else {
                throw TripFailure.invalidResponse
            }
            let calendar: CalendarStructuredTripDocument.CalendarState?
            let count: Int?
            if version == .calendar {
                calendar = try readCalendar(row.required("calendar"))
                count = Int(try row.required("day_count").integer(1...Int64.max))
            } else {
                guard case .null = try row.required("calendar"), case .null = try row.required("day_count") else {
                    throw TripFailure.invalidResponse
                }
                calendar = nil; count = nil
            }
            return try CalendarStructuredTripSummary(tripID: id, version: tripWireVersion(row.required("version")),
                contentVersion: version, contentSHA256: hash, title: boundedTripText(row.required("title"), maximum: 120),
                calendar: calendar, dayCount: count)
        }
        return try CalendarStructuredTripPage(requestID: requestID, trips: rows,
            nextAfter: root.required("next_after").nullable(tripWireID))
    }

    public static func detail(_ bytes: Data, requestID: String) throws -> CalendarStructuredTripRecord? {
        let root = try envelope(bytes, fields: "version request_id trip", requestID: requestID)
        return try root.required("trip").nullable { raw in
            let row = try raw.fields("trip_id version content_sha256 content")
            let original = try row.required("content")
            let fields = try original.object()
            let content: CalendarStructuredTripContent
            switch try fields.required("content_version").text() {
            case "structured.1", "structured.2":
                content = .legacy(try StructuredTripDocument.decode(tripCanonicalJSON(original)))
            case "structured.3":
                content = .calendar(try CalendarStructuredTripDocument.decode(tripCanonicalJSON(original)))
            default: throw TripFailure.invalidResponse
            }
            guard try same(row.required("content_sha256").text(), content.contentSHA256) else { throw TripFailure.invalidResponse }
            return try CalendarStructuredTripRecord(tripID: tripWireID(row.required("trip_id")),
                                                    version: tripWireVersion(row.required("version")), content: content)
        }
    }

    static func readCalendar(_ raw: TripJSONValue) throws -> CalendarStructuredTripDocument.CalendarState {
        let fields = try raw.object()
        switch try fields.required("state").text() {
        case "undated":
            _ = try raw.fields("state")
            return .undated
        case "dated":
            let fields = try raw.fields("state start_date")
            let date = try fields.required("start_date").text()
            _ = try OrdinalTripDate(date)
            return .dated(startDate: date)
        default: throw TripFailure.invalidResponse
        }
    }

    private static func envelope(_ bytes: Data, fields: String, requestID: String) throws -> [String: TripJSONValue] {
        guard !bytes.isEmpty, bytes.count <= 1_000_000, UUID(uuidString: requestID) != nil else { throw TripFailure.invalidResponse }
        var parser = StrictTripJSON(bytes: Array(bytes))
        let node = try parser.document()
        try factBounds(node, maxDepth: 32, maxNodes: 32768)
        let root = try node.fields(fields)
        guard try root.required("version").text() == "TRIP-structured-read.2",
              try same(root.required("request_id").text(), requestID) else { throw TripFailure.invalidResponse }
        return root
    }
}
