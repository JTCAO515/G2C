import Foundation
import CJAPI
import CJStrictJSON

enum RichTripJSONPolicy: StrictJSONPolicy {
    static var failure: TripFailure { .invalidResponse }
    static var requiresObjectRoot: Bool { true }
    static var preservesUnboundedNumberTokens: Bool { true }
}

/// Read-only frozen structured.4 values. This codec grants no protected read or editing source.
public struct RichStructuredTripDocument: Sendable {
    public enum Kind: String, Sendable { case sight, meal, hotel, transport, freeTime = "free_time" }
    public struct Reference: Sendable {
        public let provider: String
        public let kind: String
        public let reference: String
        public let sha256: String
    }
    public struct Place: Sendable {
        public let nameZH: String
        public let nameEN: String
        public let englishNameReference: Reference?
        public let providerID: String?
        public let coordinate: PlaceCoordinateV1?
        public let coordinateRole: PlaceCoordinateRoleV1?
        public let address: String?
        public let reference: Reference?
        public var matched: Bool { providerID != nil }
    }
    public struct Tip: Sendable { public let text: String; public let reference: Reference? }
    public struct Day: Sendable {
        public let index: Int
        public let date: String?
        public let theme: String
        public let area: String
    }
    public struct Item: Sendable {
        public let calendarItem: CalendarStructuredTripDocument.Item
        public let kind: Kind
        public let place: Place
        public let note: String?
        public let tip: Tip?
        public let reasonReferences: [String]
    }
    /// Preserve a finite JSON quantity's exact token, including integers beyond Double's range.
    public struct Quantity: Sendable { public let token: String }
    public struct Leg: Sendable {
        public enum Mode: String, Sendable { case walking, transit, taxi }
        public struct Estimate: Sendable {
            public let mode: Mode
            public let duration: Quantity
            public let distance: Quantity
            public let reference: Reference
        }
        public let dayIndex: Int
        public let fromItemID: String
        public let toItemID: String
        public let estimate: Estimate?
    }
    public struct Hotel: Sendable {
        public let place: Place
        public let note: String?
        public let reasonReferences: [String]
    }
    public struct Lodging: Sendable { public let area: String; public let recommendations: [Hotel] }
    public let title: String
    public let calendar: CalendarStructuredTripDocument.CalendarState
    public let days: [Day]
    public let items: [Item]
    public let sources: [Components.Schemas.SourceRecordV1]
    public let dateChecks: [CalendarStructuredTripDocument.DateCheck]
    public let legs: [Leg]
    public let lodging: Lodging
    public let originalUTF8: Data
    public var contentSHA256: String { digest(originalUTF8) }

    public static func decode(_ bytes: Data) throws -> Self {
        guard !bytes.isEmpty, bytes.count <= 1_000_000 else { throw TripFailure.invalidResponse }
        var parser = StrictJSONReader<RichTripJSONPolicy>(bytes: Array(bytes))
        let node = try parser.document()
        try factBounds(node, maxDepth: 32, maxNodes: 32768)
        guard tripCanonicalJSON(node) == bytes else { throw TripFailure.invalidResponse }
        let root = try node.fields("content_version title calendar days items sources date_checks legs lodging")
        guard try root.required("content_version").text() == "structured.4" else { throw TripFailure.invalidResponse }
        let rawDays = try root.required("days").elements(), rawItems = try root.required("items").elements()
        let richDays = try rawDays.map { raw -> (TripJSONValue, String, String) in
            var fields = try raw.object()
            let theme = try boundedTripText(fields.required("theme"), maximum: 500)
            let area = try boundedTripText(fields.required("area"), maximum: 500)
            fields.removeValue(forKey: "theme"); fields.removeValue(forKey: "area")
            return (.object(fields), theme, area)
        }
        let richItems = try rawItems.map { raw -> (TripJSONValue, [String: TripJSONValue]) in
            var fields = try raw.fields("id text verification evidence schedule fixed source_category source_refs kind place note tip reason_refs")
            var extra: [String: TripJSONValue] = [:]
            for key in ["kind", "place", "note", "tip", "reason_refs"] { extra[key] = fields.removeValue(forKey: key)! }
            return (.object(fields), extra)
        }
        // C's frozen private validation view. Do not expose its retagged bytes or source.
        let validation: TripJSONValue = .object([
            "content_version": .string("structured.3"), "title": try root.required("title"),
            "calendar": try root.required("calendar"), "days": .array(richDays.map(\.0)),
            "items": .array(richItems.map(\.0)), "sources": try root.required("sources"),
            "date_checks": try root.required("date_checks")
        ])
        let common = try CalendarStructuredTripDocument.decode(tripCanonicalJSON(validation))
        let days = zip(common.days, richDays).map { Day(index: $0.0.index, date: $0.0.date, theme: $0.1.1, area: $0.1.2) }
        let items = try zip(common.items, richItems).map { item, rich -> Item in
            let fields = rich.1
            guard let kind = Kind(rawValue: try fields.required("kind").text()) else { throw TripFailure.invalidResponse }
            let tip = try fields.required("tip").nullable { raw -> Tip in
                let f = try raw.fields("text source")
                let source = try f.required("source").nullable(readReference)
                guard source == nil || (source?.provider == "visitor" && source?.kind == "tip") else { throw TripFailure.invalidResponse }
                return try Tip(text: boundedTripText(f.required("text"), maximum: 500), reference: source)
            }
            return try Item(calendarItem: item, kind: kind, place: readPlace(fields.required("place")),
                note: optionalText(fields.required("note")), tip: tip, reasonReferences: readReasons(fields.required("reason_refs")))
        }
        let rawLegs = try root.required("legs").elements()
        guard rawLegs.count <= 60 else { throw TripFailure.invalidResponse }
        let legs = try rawLegs.map { raw -> Leg in
            let f = try raw.fields("day_index from_item_id to_item_id state mode duration_seconds distance_m source time_semantics future_guaranteed")
            guard try f.required("time_semantics").text() == "provider_estimate_at_query_time",
                  case .boolean(false) = try f.required("future_guaranteed") else { throw TripFailure.invalidResponse }
            let estimate: Leg.Estimate?
            switch try f.required("state").text() {
            case "unconfirmed":
                for key in ["mode", "duration_seconds", "distance_m", "source"] {
                    guard case .null = try f.required(key) else { throw TripFailure.invalidResponse }
                }
                estimate = nil
            case "estimated":
                guard let mode = Leg.Mode(rawValue: try f.required("mode").text()) else { throw TripFailure.invalidResponse }
                let source = try readReference(f.required("source"))
                guard source.provider == "amap", source.kind == "route" else { throw TripFailure.invalidResponse }
                estimate = try Leg.Estimate(mode: mode, duration: readQuantity(f.required("duration_seconds")),
                                            distance: readQuantity(f.required("distance_m")), reference: source)
            default: throw TripFailure.invalidResponse
            }
            return try Leg(dayIndex: Int(f.required("day_index").integer(1...Int64(days.count))),
                           fromItemID: tripWireID(f.required("from_item_id")), toItemID: tripWireID(f.required("to_item_id")), estimate: estimate)
        }
        var adjacent: [(Int, String, String)] = []
        for day in days {
            let ids = items.filter { $0.calendarItem.startDayIndex == day.index }.map { $0.calendarItem.value.id }
            adjacent += zip(ids, ids.dropFirst()).map { (day.index, $0.0, $0.1) }
        }
        guard legs.count == adjacent.count else { throw TripFailure.invalidResponse }
        for (leg, pair) in zip(legs, adjacent) {
            guard leg.dayIndex == pair.0, leg.fromItemID == pair.1, leg.toItemID == pair.2 else {
                throw TripFailure.invalidResponse
            }
        }
        let lodging = try root.required("lodging").fields("area recommendations")
        let rawHotels = try lodging.required("recommendations").elements()
        guard (2...3).contains(rawHotels.count) else { throw TripFailure.invalidResponse }
        let hotels = try rawHotels.map { raw -> Hotel in
            let f = try raw.fields("place note reason_refs")
            return try Hotel(place: readPlace(f.required("place")), note: optionalText(f.required("note")),
                             reasonReferences: readReasons(f.required("reason_refs")))
        }
        return try Self(title: common.title, calendar: common.calendar, days: days, items: items,
            sources: common.sources, dateChecks: common.dateChecks, legs: legs,
            lodging: Lodging(area: boundedTripText(lodging.required("area"), maximum: 500), recommendations: hotels), originalUTF8: bytes)
    }

    private static func optionalText(_ value: TripJSONValue) throws -> String? {
        try value.nullable { try boundedTripText($0, maximum: 500) }
    }
    private static func readReference(_ value: TripJSONValue) throws -> Reference {
        let f = try value.fields("provider kind reference sha256")
        let provider = try f.required("provider").text(), kind = try f.required("kind").text()
        let pairs = ["amap": ["place", "route", "name"], "wikidata": ["name"], "visitor": ["tip"], "checks": ["weather", "day_opening"]]
        let hash = try f.required("sha256").text()
        guard pairs[provider]?.contains(kind) == true, tripHash(hash) else { throw TripFailure.invalidResponse }
        return try Reference(provider: provider, kind: kind, reference: boundedTripText(f.required("reference"), maximum: 4096), sha256: hash)
    }
    private static func readPlace(_ value: TripJSONValue) throws -> Place {
        let f = try value.fields("state amap_id name_zh name_en name_en_source coordinate coordinate_role address source")
        let name = try f.required("name_en_source").nullable(readReference)
        guard name == nil || name?.kind == "name" else { throw TripFailure.invalidResponse }
        let id: String?, coordinate: PlaceCoordinateV1?, role: PlaceCoordinateRoleV1?, source: Reference?, address: String?
        switch try f.required("state").text() {
        case "unconfirmed":
            for key in ["amap_id", "coordinate", "coordinate_role", "address", "source"] {
                guard case .null = try f.required(key) else { throw TripFailure.invalidResponse }
            }
            id = nil; coordinate = nil; role = nil; source = nil; address = nil
        case "matched":
            id = try f.required("amap_id").identifier()
            coordinate = try PlaceCoordinateV1.read(f.required("coordinate"))
            guard let decoded = PlaceCoordinateRoleV1(rawValue: try f.required("coordinate_role").text()) else { throw TripFailure.invalidResponse }
            role = decoded
            source = try readReference(f.required("source"))
            guard source?.provider == "amap", source?.kind == "place" else { throw TripFailure.invalidResponse }
            address = try optionalText(f.required("address"))
        default: throw TripFailure.invalidResponse
        }
        return try Place(nameZH: boundedTripText(f.required("name_zh"), maximum: 500),
            nameEN: boundedTripText(f.required("name_en"), maximum: 500), englishNameReference: name,
            providerID: id, coordinate: coordinate, coordinateRole: role, address: address, reference: source)
    }
    private static func readReasons(_ value: TripJSONValue) throws -> [String] {
        let factors = Set(["city", "duration_days", "season", "first_visit", "party_type", "interests", "pace", "lodging_tier", "dietary", "must_see", "avoid", "mobility", "arrival", "departure"])
        let names = try value.elements().map { try $0.text() }
        guard Set(names).count == names.count, Set(names).isSubset(of: factors) else { throw TripFailure.invalidResponse }
        return names
    }
    private static func readQuantity(_ value: TripJSONValue) throws -> Quantity {
        guard case .number(let token) = value else { throw TripFailure.invalidResponse }
        if token.contains(where: { ".eE".contains($0) }) {
            guard let number = Double(token), number.isFinite, number >= 0 else { throw TripFailure.invalidResponse }
        } else if token.first == "-", token.dropFirst() != "0" { throw TripFailure.invalidResponse }
        return Quantity(token: token)
    }
}
