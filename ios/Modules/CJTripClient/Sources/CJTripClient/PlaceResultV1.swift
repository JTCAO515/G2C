import Foundation

/// Fixed PLACE@1.0 data, never authorization, freshness or dispatch permission.
public struct PlaceResultV1: Sendable {
    public static let contractVersion = "PLACE@1.0"
    public static let wireVersion = "PLACE-result.1"
    public let originalUTF8: Data
    public let query: PlaceQueryV1
    public let outcome: PlaceOutcomeV1
    public let reason: String
    public let source: PlaceSourceV1?
    public let places: [PlaceV1]
    public let routes: [PlaceRouteV1]
    public let providerCode: String?
    public let providerCount: Int64?

    public static func decode(_ bytes: Data) throws -> Self {
        guard !bytes.isEmpty, bytes.count <= 1_048_576 else { throw TripFailure.invalidResponse }
        do {
            var parser = StrictTripJSON(bytes: Array(bytes))
            let root = try parser.document().fields("version query outcome reason source places routes provider_code provider_count")
            guard try root.required("version").text() == "PLACE-result.1",
                  let outcome = PlaceOutcomeV1(rawValue: try root.required("outcome").text()) else { throw TripFailure.invalidResponse }
            let query = try PlaceQueryV1.read(root.required("query"))
            let reason = try root.required("reason").text()
            guard reason.matches("[a-z0-9_]{1,96}") else { throw TripFailure.invalidResponse }
            let code = try root.required("provider_code").nullable { try $0.text() }
            if let code { guard code.matches("[0-9]{1,16}") else { throw TripFailure.invalidResponse } }
            let count = try root.required("provider_count").nullable { try $0.integer(0...9_999_999_999) }
            let places = try root.required("places").elements().map(PlaceV1.read)
            let routes = try root.required("routes").elements().map { try PlaceRouteV1.read($0, query: query) }
            if case .route = query { guard places.isEmpty else { throw TripFailure.invalidResponse } }
            else { guard routes.isEmpty else { throw TripFailure.invalidResponse } }
            guard outcome == .ok ? (!places.isEmpty || !routes.isEmpty) : (places.isEmpty && routes.isEmpty),
                  Set(places.map(\.providerID)).count == places.count else { throw TripFailure.invalidResponse }
            switch query {
            case .detail(let id): guard places.count <= 1, places.allSatisfy({ $0.providerID == id }) else { throw TripFailure.invalidResponse }
            case .search(_, _, _, let size): guard places.count <= size else { throw TripFailure.invalidResponse }
            case .route: break
            }
            if let count { guard count >= places.count, routes.isEmpty || count == routes.count else { throw TripFailure.invalidResponse } }
            let source = try root.required("source").nullable { try PlaceSourceV1.read($0, query: query, outcome: outcome) }
            guard source != nil || (places.isEmpty && routes.isEmpty && outcome != .noResults) else { throw TripFailure.invalidResponse }
            return .init(originalUTF8: bytes, query: query, outcome: outcome, reason: reason, source: source,
                         places: places, routes: routes, providerCode: code, providerCount: count)
        } catch { throw TripFailure.invalidResponse }
    }
}

public enum PlaceOutcomeV1: String, Sendable {
    case ok, noResults = "no_results", rateLimited = "rate_limited", providerError = "provider_error"
    case unknown, invalidResponse = "invalid_response", bindingMismatch = "binding_mismatch", stale, unsupported, unavailable
}
public enum PlaceFieldStateV1: String, Sendable {
    case present, missing, emptyArray = "empty_array", emptyString = "empty_string", null, invalid, unknown
}
public struct PlaceObservedV1<Value: Sendable>: Sendable {
    public let state: PlaceFieldStateV1
    public let value: Value?
    static func read(_ input: TripJSONValue, _ decode: (TripJSONValue) throws -> Value) throws -> Self {
        let fields = try input.fields("state value")
        guard let state = PlaceFieldStateV1(rawValue: try fields.required("state").text()) else { throw TripFailure.invalidResponse }
        let value = try fields.required("value")
        if state == .present { return .init(state: state, value: try decode(value)) }
        guard case .null = value else { throw TripFailure.invalidResponse }
        return .init(state: state, value: nil)
    }
}
public struct PlaceDecimalV1: Sendable, Equatable {
    /// Exact canonical Decimal string from the contract, including trailing/negative zero.
    public let text: String
    public let value: Decimal
}
public struct PlaceCoordinateV1: Sendable, Equatable {
    public let raw: String
    public let longitude: PlaceDecimalV1
    public let latitude: PlaceDecimalV1
    public let crs: String
    static func read(_ input: TripJSONValue) throws -> Self {
        let f = try input.fields("raw longitude latitude crs"), raw = try f.required("raw").text()
        guard raw.matches("-?[0-9]{1,3}(?:\\.[0-9]{1,12})?,-?[0-9]{1,2}(?:\\.[0-9]{1,12})?"),
              try f.required("crs").text() == "GCJ-02" else { throw TripFailure.invalidResponse }
        let parts = raw.split(separator: ",").map(String.init)
        let longitude = try decimal(parts[0], wire: f.required("longitude"))
        let latitude = try decimal(parts[1], wire: f.required("latitude"))
        guard (-180...180).contains(longitude.value), (-90...90).contains(latitude.value) else { throw TripFailure.invalidResponse }
        return .init(raw: raw, longitude: longitude, latitude: latitude, crs: "GCJ-02")
    }
}
public enum PlaceCoordinateRoleV1: String, Sendable { case poiCenter = "poi_center", entrance, exit }
public struct PlaceEndpointV1: Sendable, Equatable {
    public let providerID: String
    public let coordinate: PlaceCoordinateV1
    public let role: PlaceCoordinateRoleV1
    static func read(_ input: TripJSONValue) throws -> Self {
        let f = try input.fields("provider_id coordinate coordinate_role")
        let coordinate = try PlaceCoordinateV1.read(f.required("coordinate"))
        guard let role = PlaceCoordinateRoleV1(rawValue: try f.required("coordinate_role").text()),
              coordinate.raw.split(separator: ",").allSatisfy({ ($0.split(separator: ".", omittingEmptySubsequences: false).dropFirst().first?.count ?? 0) <= 6 }) else { throw TripFailure.invalidResponse }
        return .init(providerID: try f.required("provider_id").identifier(), coordinate: coordinate, role: role)
    }
}
public struct PlaceTimestampV1: Sendable, Equatable {
    public let iso8601: String
    public let fold: Int
    /// Exact instant for ordering; integer microseconds since proleptic Gregorian 0001-01-01 UTC.
    public let utcMicroseconds: Int64
    static func read(_ input: TripJSONValue) throws -> Self {
        let f = try input.fields("iso8601 fold"), text = try f.required("iso8601").text()
        let pattern = #"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.([0-9]{6})([+-])([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]{6}))?)?$"#
        let regex = try NSRegularExpression(pattern: pattern)
        guard let m = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              m.range == NSRange(text.startIndex..., in: text) else { throw TripFailure.invalidResponse }
        func capture(_ n: Int) -> String? { Range(m.range(at: n), in: text).map { String(text[$0]) } }
        let values = try (1...7).map { n -> Int64 in
            guard let part = capture(n), let number = Int64(part) else { throw TripFailure.invalidResponse }; return number
        }
        let y=values[0], month=values[1], day=values[2], hour=values[3], minute=values[4], second=values[5], micro=values[6]
        let leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)
        let days: [Int64] = [31, leap ? 29 : 28,31,30,31,30,31,31,30,31,30,31]
        guard (1...9999).contains(y), (1...12).contains(month), (1...days[Int(month-1)]).contains(day),
              hour < 24, minute < 60, second < 60,
              let offsetHour = capture(9).flatMap(Int64.init), let offsetMinute = capture(10).flatMap(Int64.init),
              offsetHour < 24, offsetMinute < 60 else { throw TripFailure.invalidResponse }
        let offsetSecond = capture(11).flatMap(Int64.init), offsetMicro = capture(12).flatMap(Int64.init)
        if let offsetSecond { guard offsetSecond < 60, offsetSecond != 0 || offsetMicro != nil else { throw TripFailure.invalidResponse } }
        if let offsetMicro { guard offsetMicro != 0 else { throw TripFailure.invalidResponse } }
        let offset = ((offsetHour*60+offsetMinute)*60+(offsetSecond ?? 0))*1_000_000+(offsetMicro ?? 0)
        let negative = capture(8) == "-"
        guard offset != 0 || !negative else { throw TripFailure.invalidResponse }
        let previous = y-1
        let ordinal = previous*365+previous/4-previous/100+previous/400+days.prefix(Int(month-1)).reduce(0,+)+day-1
        let local = ((ordinal*24+hour)*60+minute)*60+second
        return .init(iso8601: text, fold: Int(try f.required("fold").integer(0...1)),
                     utcMicroseconds: local*1_000_000+micro-(negative ? -offset : offset))
    }
}
public enum PlaceDepartureV1: Sendable, Equatable {
    case atQueryTime
    case specifiedTime(PlaceTimestampV1)
    static func read(_ input: TripJSONValue) throws -> Self {
        let f = try input.fields("condition at")
        switch try f.required("condition").text() {
        case "at_query_time": guard case .null = try f.required("at") else { throw TripFailure.invalidResponse }; return .atQueryTime
        case "specified_time": return .specifiedTime(try PlaceTimestampV1.read(f.required("at")))
        default: throw TripFailure.invalidResponse
        }
    }
}
public enum PlaceQueryV1: Sendable, Equatable {
    case search(keyword: String, city: String, page: Int, pageSize: Int)
    case detail(providerID: String)
    case route(origin: PlaceEndpointV1, destination: PlaceEndpointV1, mode: String, departure: PlaceDepartureV1)
    static func read(_ input: TripJSONValue) throws -> Self {
        let kind = try input.object().required("kind").text()
        switch kind {
        case "Search":
            let f = try input.fields("kind keyword city page page_size")
            let keyword = try f.required("keyword").safeText(256), city = try f.required("city").safeText(128)
            let page = try f.required("page").integer(1...200), size = try f.required("page_size").integer(1...25)
            guard !keyword.contains("|"), page*size <= 200 else { throw TripFailure.invalidResponse }
            return .search(keyword: keyword, city: city, page: Int(page), pageSize: Int(size))
        case "Detail": return .detail(providerID: try input.fields("kind provider_id").required("provider_id").identifier())
        case "RouteQuery":
            let f = try input.fields("kind origin destination mode departure"), mode = try f.required("mode").text()
            guard ["walking","driving"].contains(mode) else { throw TripFailure.invalidResponse }
            return .route(origin: try PlaceEndpointV1.read(f.required("origin")), destination: try PlaceEndpointV1.read(f.required("destination")),
                          mode: mode, departure: try PlaceDepartureV1.read(f.required("departure")))
        default: throw TripFailure.invalidResponse
        }
    }
}
public struct PlaceV1: Sendable {
    public var provider: String { "gaode" }
    public let providerID: String
    public let nameZH: String
    public let addressZH: PlaceObservedV1<String>
    public let coordinate: PlaceObservedV1<PlaceCoordinateV1>
    public let entrance: PlaceObservedV1<PlaceCoordinateV1>
    public let exit: PlaceObservedV1<PlaceCoordinateV1>
    public let parentID: PlaceObservedV1<String>
    public let navigationID: PlaceObservedV1<String>
    public let typecode: PlaceObservedV1<String>
    public let officialNameEN: PlaceObservedV1<String>
    public let officialAddressEN: PlaceObservedV1<String>
    public func coordinate(for role: PlaceCoordinateRoleV1) -> PlaceObservedV1<PlaceCoordinateV1> {
        switch role { case .poiCenter: coordinate; case .entrance: entrance; case .exit: exit }
    }
    static func read(_ input: TripJSONValue) throws -> Self {
        let f = try input.fields("provider provider_id name_zh address_zh coordinate entrance_coordinate exit_coordinate parent_id navigation_id typecode official_name_en official_address_en")
        guard try f.required("provider").text() == "gaode" else { throw TripFailure.invalidResponse }
        return .init(providerID: try f.required("provider_id").identifier(), nameZH: try f.required("name_zh").safeText(),
            addressZH: try .read(f.required("address_zh")) { try $0.safeText() }, coordinate: try .read(f.required("coordinate"), PlaceCoordinateV1.read),
            entrance: try .read(f.required("entrance_coordinate"), PlaceCoordinateV1.read), exit: try .read(f.required("exit_coordinate"), PlaceCoordinateV1.read),
            parentID: try .read(f.required("parent_id")) { try $0.identifier() }, navigationID: try .read(f.required("navigation_id")) { try $0.identifier() },
            typecode: try .read(f.required("typecode")) { try $0.safeText() }, officialNameEN: try .read(f.required("official_name_en")) { try $0.safeText() },
            officialAddressEN: try .read(f.required("official_address_en")) { try $0.safeText() })
    }
}
public struct PlaceQuantityV1: Sendable {
    public let raw: String
    public let amount: PlaceDecimalV1
    public let unit: String
    static func read(_ input: TripJSONValue, unit: String) throws -> Self {
        let f = try input.fields("raw value unit"), raw = try f.required("raw").text()
        guard raw.matches("[0-9]{1,12}(?:\\.[0-9]{1,6})?"), try f.required("unit").text() == unit else { throw TripFailure.invalidResponse }
        return .init(raw: raw, amount: try decimal(raw, wire: f.required("value")), unit: unit)
    }
}
public struct PlaceRouteV1: Sendable {
    public var timeSemantics: String { "provider_estimate_at_query_time" }
    public var futureGuaranteed: Bool { false }
    public let query: PlaceQueryV1
    public let distance: PlaceObservedV1<PlaceQuantityV1>
    public let duration: PlaceObservedV1<PlaceQuantityV1>
    static func read(_ input: TripJSONValue, query: PlaceQueryV1) throws -> Self {
        let f = try input.fields("query distance duration time_semantics future_guaranteed")
        guard case .route = query, try PlaceQueryV1.read(f.required("query")) == query,
              try f.required("time_semantics").text() == "provider_estimate_at_query_time",
              case .boolean(false) = try f.required("future_guaranteed") else { throw TripFailure.invalidResponse }
        return .init(query: query, distance: try .read(f.required("distance")) { try PlaceQuantityV1.read($0, unit: "m") },
                     duration: try .read(f.required("duration")) { try PlaceQuantityV1.read($0, unit: "s") })
    }
}
public struct PlaceSourceV1: Sendable {
    public var provider: String { "gaode" }
    public var apiVersion: String { "v3" }
    public var adapterProfile: String { "CJ-PLACE-GAODE@0.1.0-rc.1" }
    public var providerUpdatedAt: PlaceTimestampV1? { nil }
    public let endpoint: String
    public let requestReference: String
    public let bindingDigest: String
    public let started: PlaceTimestampV1
    public let received: PlaceTimestampV1
    public let evidenceKind: String
    public let recordingReference: String?
    static func read(_ input: TripJSONValue, query: PlaceQueryV1, outcome: PlaceOutcomeV1) throws -> Self {
        let f = try input.fields("endpoint provider api_version adapter_profile request_ref binding_digest query_started_at received_at provider_updated_at evidence_kind recording_ref")
        let path: String
        switch query { case .search: path = "/v3/place/text"; case .detail: path = "/v3/place/detail"; case .route(_,_,let mode,_): path = "/v3/direction/"+mode }
        let endpoint = try f.required("endpoint").text(), digest = try f.required("binding_digest").text()
        guard endpoint == "https://restapi.amap.com"+path, try f.required("provider").text() == "gaode",
              try f.required("api_version").text() == "v3", try f.required("adapter_profile").text() == "CJ-PLACE-GAODE@0.1.0-rc.1",
              case .null = try f.required("provider_updated_at"), digest.matches("[0-9a-f]{64}") else { throw TripFailure.invalidResponse }
        let start = try PlaceTimestampV1.read(f.required("query_started_at")), received = try PlaceTimestampV1.read(f.required("received_at"))
        if outcome == .ok {
            guard received.utcMicroseconds >= start.utcMicroseconds else { throw TripFailure.invalidResponse }
            if case .route(_,_,_,let departure) = query { guard departure == .atQueryTime else { throw TripFailure.invalidResponse } }
        }
        let evidence = try f.required("evidence_kind").text(), recording = try f.required("recording_ref").nullable { try $0.safeText() }
        guard ["synthetic","recorded_replay","live_provider","unverified_bytes"].contains(evidence),
              (evidence == "recorded_replay") == (recording != nil) else { throw TripFailure.invalidResponse }
        return .init(endpoint: endpoint, requestReference: try f.required("request_ref").identifier(), bindingDigest: digest,
                     started: start, received: received, evidenceKind: evidence, recordingReference: recording)
    }
}

private func decimal(_ raw: String, wire: TripJSONValue) throws -> PlaceDecimalV1 {
    let negative = raw.hasPrefix("-"), unsigned = negative ? String(raw.dropFirst()) : raw
    let parts = unsigned.split(separator: ".", omittingEmptySubsequences: false)
    let integer = parts[0].drop(while: { $0 == "0" })
    let canonical = (negative ? "-" : "") + (integer.isEmpty ? "0" : String(integer)) + (parts.count == 2 ? "."+parts[1] : "")
    guard try wire.text() == canonical, let value = Decimal(string: canonical, locale: Locale(identifier: "en_US_POSIX")) else { throw TripFailure.invalidResponse }
    return .init(text: canonical, value: value)
}
extension String {
    func matches(_ expression: String) -> Bool { range(of: "^(?:"+expression+")$", options: .regularExpression) == startIndex..<endIndex }
}
extension TripJSONValue {
    func object() throws -> [String: Self] { guard case .object(let value) = self else { throw TripFailure.invalidResponse }; return value }
    func fields(_ expected: String) throws -> [String: Self] {
        let value = try object(); guard Set(value.keys) == Set(expected.split(separator: " ").map(String.init)) else { throw TripFailure.invalidResponse }; return value
    }
    func elements() throws -> [Self] { guard case .array(let value) = self else { throw TripFailure.invalidResponse }; return value }
    func text() throws -> String { guard case .string(let value) = self else { throw TripFailure.invalidResponse }; return value }
    func safeText(_ limit: Int = 1024) throws -> String {
        let value = try text()
        guard !value.isEmpty, value.utf8.count <= limit, !value.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else { throw TripFailure.invalidResponse }
        return value
    }
    func identifier() throws -> String { let value = try safeText(200); guard value.matches("[A-Za-z0-9_-]+") else { throw TripFailure.invalidResponse }; return value }
    func integer(_ bounds: ClosedRange<Int64>) throws -> Int64 {
        guard case .number(let token) = self, token.matches("-?(?:0|[1-9][0-9]*)"), let value = Int64(token), bounds.contains(value) else { throw TripFailure.invalidResponse }; return value
    }
    func nullable<T>(_ decode: (Self) throws -> T) throws -> T? { if case .null = self { return nil }; return try decode(self) }
}
extension Dictionary where Key == String, Value == TripJSONValue {
    func required(_ key: String) throws -> Value { guard let value = self[key] else { throw TripFailure.invalidResponse }; return value }
}
