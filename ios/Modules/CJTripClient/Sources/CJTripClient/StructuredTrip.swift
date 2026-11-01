import Foundation
import CJAPI

/// Explicit observations, not defaults or claims of current authority.
public enum TripObservation<Value: Sendable>: Sendable {
    case known(Value), missing, unknown, uncertain(String)
}
extension TripObservation: Equatable where Value: Equatable {}

public enum StructuredTripVersion: String, Sendable {
    case first = "structured.1", needsBound = "structured.2"
}

public struct StructuredTripEvent: Sendable {
    public let date: TripObservation<String>
    public let time: TripObservation<String>
    public let timezone: TripObservation<String>
    public let utcOffset: TripObservation<String>

    static func read(_ value: TripJSONValue, version: StructuredTripVersion) throws -> Self {
        let f = try value.fields("date time timezone utc_offset")
        return try .init(date: observation(f.required("date")) { value in
            let text = try boundedTripText(value, maximum: 10)
            guard text.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}") else { throw TripFailure.invalidResponse }
            // UTC here validates the calendar date only; it is never a source zone.
            _ = try factStamp(.object(["iso8601": .string(text + "T00:00:00.000000+00:00"), "fold": .number("0")]))
            return text
        }, time: observation(f.required("time")) { value in
            let text = try boundedTripText(value, maximum: 8)
            let pattern = version == .first ? "[0-9]{2}:[0-9]{2}:[0-9]{2}" : "[0-9]{2}:[0-9]{2}(?::[0-9]{2})?"
            guard text.matches(pattern) else { throw TripFailure.invalidResponse }
            let parts = text.split(separator: ":").map { Int($0)! }
            guard parts[0] < 24, parts[1] < 60, parts.count == 2 || parts[2] < 60 else { throw TripFailure.invalidResponse }
            return text // Preserve minute precision; never append seconds.
        }, timezone: observation(f.required("timezone")) { value in
            let text = try boundedTripText(value, maximum: 128)
            guard text != "localtime", text != "Factory",
                  TimeZone.knownTimeZoneIdentifiers.contains(text) || ["UTC", "Etc/UTC", "GMT", "Etc/GMT"].contains(text),
                  TimeZone(identifier: text) != nil else { throw TripFailure.invalidResponse }
            return text
        }, utcOffset: observation(f.required("utc_offset")) { value in
            let text = try boundedTripText(value, maximum: 6)
            guard text.matches("[+-][0-9]{2}:[0-9]{2}") else { throw TripFailure.invalidResponse }
            let parts = text.dropFirst().split(separator: ":").map { Int($0)! }
            guard parts[0] <= 23, parts[1] <= 59 else { throw TripFailure.invalidResponse }
            return text
        })
    }
}

public struct StructuredTripItem: Identifiable, Sendable {
    public let id: String
    public let text: String
    public let verification: Components.Schemas.TripDocumentItem.verificationPayload
    public let evidence: [String]
    public let start: StructuredTripEvent
    public let end: StructuredTripEvent
    public let fixed: TripObservation<Bool>
    public let sourceCategory: Components.Schemas.SourceDocumentItemV1.source_categoryPayload
    public let sourceReferences: [String]
}

/// Parsed canonical content is data. Only a protected client read may mint an
/// accepted editing source; constructing/decoding this value cannot grant writes.
public struct StructuredTripDocument: Sendable {
    public let version: StructuredTripVersion
    public let title: String
    public let items: [StructuredTripItem]
    public let sources: [Components.Schemas.SourceRecordV1]
    public let originalUTF8: Data
    public var contentSHA256: String { digest(originalUTF8) }

    public static func decode(_ bytes: Data) throws -> Self {
        guard !bytes.isEmpty, bytes.count <= 1_000_000 else { throw TripFailure.invalidResponse }
        var parser = StrictTripJSON(bytes: Array(bytes)); let node = try parser.document()
        try factBounds(node, maxDepth: 32, maxNodes: 32768)
        guard tripCanonicalJSON(node) == bytes else { throw TripFailure.invalidResponse }
        let f = try node.fields("content_version title items sources")
        guard let version = StructuredTripVersion(rawValue: try f.required("content_version").text()) else { throw TripFailure.invalidResponse }
        let title = try boundedTripText(f.required("title"), maximum: 120)
        let sources = try JSONDecoder().decode([Components.Schemas.SourceRecordV1].self, from: tripCanonicalJSON(f.required("sources")))
        let sourceMap = try validatedTripSources(sources)
        let values = try f.required("items").elements()
        guard (1...60).contains(values.count) else { throw TripFailure.invalidResponse }
        var ids = Set<String>(), used = Set<String>()
        let items = try values.map { value -> StructuredTripItem in
            let item = try value.fields("id text verification evidence schedule fixed source_category source_refs")
            let id = try tripWireID(item.required("id")), text = try boundedTripText(item.required("text"), maximum: 500)
            guard ids.insert(id).inserted,
                  let verification = Components.Schemas.TripDocumentItem.verificationPayload(rawValue: try item.required("verification").text()),
                  let category = Components.Schemas.SourceDocumentItemV1.source_categoryPayload(rawValue: try item.required("source_category").text()) else { throw TripFailure.invalidResponse }
            let evidence = try item.required("evidence").elements().map { try boundedTripText($0, maximum: 4096) }
            let refs = try item.required("source_refs").elements().map { try $0.text() }
            guard evidence.count <= 40, refs.count <= 1, verification != .verified || !evidence.isEmpty else { throw TripFailure.invalidResponse }
            if category == .unknown {
                guard refs.isEmpty else { throw TripFailure.invalidResponse }
            } else if !(category == .user_provided && refs.isEmpty) {
                guard refs.count == 1, let source = sourceMap[refs[0]], same(source.text, text),
                      verification == .pending, evidence.isEmpty else { throw TripFailure.invalidResponse }
                let kind: Components.Schemas.SourceRecordV1.kindPayload
                switch category {
                case .user_provided: kind = .message
                case .queried: kind = .place
                case .estimated: kind = .route_estimate
                case .unknown: throw TripFailure.invalidResponse
                }
                guard source.kind == kind else { throw TripFailure.invalidResponse }
                used.insert(refs[0])
            }
            let schedule = try item.required("schedule").fields("start end")
            return try .init(id: id, text: text, verification: verification, evidence: evidence,
                start: .read(schedule.required("start"), version: version), end: .read(schedule.required("end"), version: version),
                fixed: observation(item.required("fixed")) { value in
                    guard case .boolean(let result) = value else { throw TripFailure.invalidResponse }; return result
                }, sourceCategory: category, sourceReferences: refs)
        }
        guard used == Set(sourceMap.keys) else { throw TripFailure.invalidResponse }
        return .init(version: version, title: title, items: items, sources: sources, originalUTF8: bytes)
    }
}

public struct StructuredTripSummary: Sendable {
    public let tripID: String
    public let version: Int
    public let contentVersion: StructuredTripVersion
    public let title: String
    public let contentSHA256: String
}
public struct StructuredTripRecord: Sendable {
    public let tripID: String
    public let version: Int
    public let document: StructuredTripDocument
}
public struct StructuredTripPage: Sendable {
    public let requestID: String
    public let trips: [StructuredTripSummary]
    /// May advance through a page containing no structured records.
    public let nextAfter: String?
}

/// TRIP-structured-read.1 projections. No fallback to old unstructured readers.
public enum StructuredTripReadV1 {
    public static func page(_ bytes: Data, requestID: String) throws -> StructuredTripPage {
        let f = try envelope(bytes, fields: "version request_id trips next_after", requestID: requestID)
        let values = try f.required("trips").elements()
        guard values.count <= 100 else { throw TripFailure.invalidResponse }
        var ids = Set<String>()
        let trips = try values.map { value -> StructuredTripSummary in
            let item = try value.fields("trip_id version content_version title content_sha256")
            let id = try tripWireID(item.required("trip_id")), hash = try item.required("content_sha256").text()
            guard ids.insert(id).inserted, tripHash(hash),
                  let contentVersion = StructuredTripVersion(rawValue: try item.required("content_version").text()) else { throw TripFailure.invalidResponse }
            return try .init(tripID: id, version: tripWireVersion(item.required("version")), contentVersion: contentVersion,
                title: boundedTripText(item.required("title"), maximum: 120), contentSHA256: hash)
        }
        return try .init(requestID: requestID, trips: trips, nextAfter: f.required("next_after").nullable(tripWireID))
    }
    public static func detail(_ bytes: Data, requestID: String) throws -> StructuredTripRecord? {
        let f = try envelope(bytes, fields: "version request_id trip", requestID: requestID)
        return try f.required("trip").nullable { value in
            let item = try value.fields("trip_id version content_sha256 content")
            let document = try StructuredTripDocument.decode(tripCanonicalJSON(item.required("content")))
            guard try same(item.required("content_sha256").text(), document.contentSHA256) else { throw TripFailure.invalidResponse }
            return try .init(tripID: tripWireID(item.required("trip_id")), version: tripWireVersion(item.required("version")), document: document)
        }
    }
    private static func envelope(_ bytes: Data, fields: String, requestID: String) throws -> [String: TripJSONValue] {
        guard !bytes.isEmpty, bytes.count <= 1_000_000, UUID(uuidString: requestID) != nil else { throw TripFailure.invalidResponse }
        var parser = StrictTripJSON(bytes: Array(bytes)); let node = try parser.document()
        try factBounds(node, maxDepth: 32, maxNodes: 32768)
        let f = try node.fields(fields)
        guard try f.required("version").text() == "TRIP-structured-read.1", try same(f.required("request_id").text(), requestID) else { throw TripFailure.invalidResponse }
        return f
    }
}

private func observation<Value: Sendable>(_ node: TripJSONValue, read: (TripJSONValue) throws -> Value) throws -> TripObservation<Value> {
    let f = try node.object()
    switch try f.required("state").text() {
    case "known": _ = try node.fields("state value"); return try .known(read(f.required("value")))
    case "missing": _ = try node.fields("state"); return .missing
    case "unknown": _ = try node.fields("state"); return .unknown
    case "uncertain": _ = try node.fields("state note"); return try .uncertain(boundedTripText(f.required("note"), maximum: 500))
    default: throw TripFailure.invalidResponse
    }
}
func boundedTripText(_ value: TripJSONValue, maximum: Int) throws -> String {
    let text = try value.text()
    guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, text.unicodeScalars.count <= maximum else { throw TripFailure.invalidResponse }
    return text
}
func tripWireID(_ value: TripJSONValue) throws -> String {
    let id = try value.text(); guard tripID(id) else { throw TripFailure.invalidResponse }; return id
}
func tripWireVersion(_ value: TripJSONValue) throws -> Int { Int(try value.integer(1...Int64.max)) }

/// Python packed encoding for these frozen objects: scalar strings are retained
/// verbatim, object keys use Unicode scalar order, and slashes stay unescaped.
/// Parsed number tokens stay lexical; version fields are validated separately.
func tripCanonicalJSON(_ value: TripJSONValue) -> Data {
    func quote(_ text: String) -> String {
        var result = "\""
        for scalar in text.unicodeScalars {
            switch scalar.value {
            case 34: result += "\\\""
            case 92: result += "\\\\"
            case 8: result += "\\b"
            case 9: result += "\\t"
            case 10: result += "\\n"
            case 12: result += "\\f"
            case 13: result += "\\r"
            case 0..<32: result += String(format: "\\u%04x", scalar.value)
            default: result.unicodeScalars.append(scalar)
            }
        }
        return result + "\""
    }
    func encode(_ value: TripJSONValue) -> String {
        switch value {
        case .object(let values):
            return "{" + values.keys.sorted { $0.utf8.lexicographicallyPrecedes($1.utf8) }.map { quote($0) + ":" + encode(values[$0]!) }.joined(separator: ",") + "}"
        case .array(let values): return "[" + values.map(encode).joined(separator: ",") + "]"
        case .string(let text): return quote(text)
        case .number(let token): return token
        case .boolean(let value): return value ? "true" : "false"
        case .null: return "null"
        }
    }
    return Data(encode(value).utf8)
}
