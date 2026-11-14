import Foundation
import CJAPI

/// Read-only structured.3 data. This type cannot become an AcceptedStructuredTripSnapshot.
public struct CalendarStructuredTripDocument: Sendable {
    public enum CalendarState: Equatable, Sendable { case undated, dated(startDate: String) }
    public struct Day: Equatable, Sendable {
        public let index: Int
        public let date: String?
    }
    public struct Item: Sendable {
        public let startDayIndex: Int
        public let endDayIndex: Int
        public let value: StructuredTripItem
    }
    public struct DateCheck: Equatable, Sendable {
        public enum Kind: String, Sendable { case weather, dayOpening = "day_opening" }
        public enum State: String, Sendable { case notChecked = "not_checked", unknown, clear, conflict }
        public let kind: Kind
        public let state: State
        public let dayIndices: [Int]
        public let itemIDs: [String]
        public let reason: String
        public let evidenceReferences: [String]
    }

    public let title: String
    public let calendar: CalendarState
    public let days: [Day]
    public let items: [Item]
    public let sources: [Components.Schemas.SourceRecordV1]
    public let dateChecks: [DateCheck]
    public let originalUTF8: Data
    public var contentSHA256: String { digest(originalUTF8) }

    public static func decode(_ bytes: Data) throws -> Self {
        guard !bytes.isEmpty, bytes.count <= 1_000_000 else { throw TripFailure.invalidResponse }
        var parser = StrictTripJSON(bytes: Array(bytes))
        let node = try parser.document()
        try factBounds(node, maxDepth: 32, maxNodes: 32768)
        guard tripCanonicalJSON(node) == bytes else { throw TripFailure.invalidResponse }
        let root = try node.fields("content_version title calendar days items sources date_checks")
        guard try root.required("content_version").text() == "structured.3" else { throw TripFailure.invalidResponse }
        let rawCalendar = try root.required("calendar").object()
        let calendar: CalendarState
        var nextDate: OrdinalTripDate?
        switch try rawCalendar.required("state").text() {
        case "undated":
            _ = try root.required("calendar").fields("state")
            calendar = .undated
        case "dated":
            let fields = try root.required("calendar").fields("state start_date")
            let start = try fields.required("start_date").text()
            nextDate = try OrdinalTripDate(start)
            calendar = .dated(startDate: start)
        default: throw TripFailure.invalidResponse
        }
        let rawDays = try root.required("days").elements()
        guard !rawDays.isEmpty else { throw TripFailure.invalidResponse }
        let days = try rawDays.enumerated().map { position, raw -> Day in
            let fields = try raw.fields(calendar == .undated ? "day_index" : "day_index date")
            let index = try fields.required("day_index").integer(1...Int64.max)
            guard index == Int64(position + 1) else { throw TripFailure.invalidResponse }
            let date: String?
            if calendar == .undated { date = nil }
            else {
                date = try fields.required("date").text()
                guard date == nextDate?.text else { throw TripFailure.invalidResponse }
                if position + 1 < rawDays.count { try nextDate?.advance() }
            }
            return Day(index: position + 1, date: date)
        }

        let rawItems = try root.required("items").elements()
        guard (1...60).contains(rawItems.count) else { throw TripFailure.invalidResponse }
        var ordinals: [(Int, Int)] = []
        let validationItems = try rawItems.map { raw -> TripJSONValue in
            var fields = try raw.fields("id text verification evidence schedule fixed source_category source_refs")
            let schedule = try fields.required("schedule").fields("start end")
            var indices: [Int] = []
            var validationSchedule: [String: TripJSONValue] = [:]
            for edge in ["start", "end"] {
                var event = try schedule.required(edge).fields("day_index time timezone utc_offset")
                let index = Int(try event.required("day_index").integer(1...Int64(days.count)))
                if calendar == .undated {
                    let offset = try event.required("utc_offset").object()
                    guard try offset.required("state").text() != "known" else { throw TripFailure.invalidResponse }
                }
                event.removeValue(forKey: "day_index")
                if let date = days[index - 1].date {
                    event["date"] = .object(["state": .string("known"), "value": .string(date)])
                } else { event["date"] = .object(["state": .string("unknown")]) }
                validationSchedule[edge] = .object(event)
                indices.append(index)
            }
            ordinals.append((indices[0], indices[1]))
            fields["schedule"] = .object(validationSchedule)
            return .object(fields)
        }

        // Match C's frozen validation-only view: reuse unchanged item/Observation/
        // provenance rules. The copied document is never published, stored, returned
        // as structured.2 or used to mint an accepted editing source.
        let validationNode = TripJSONValue.object([
            "content_version": .string("structured.2"), "title": try root.required("title"),
            "items": .array(validationItems), "sources": try root.required("sources")
        ])
        let validated = try StructuredTripDocument.readFields(validationNode, originalUTF8: tripCanonicalJSON(validationNode))
        let items = zip(validated.items, ordinals).map {
            Item(startDayIndex: $0.1.0, endDayIndex: $0.1.1, value: $0.0)
        }
        let ids = Set(validated.items.map(\.id))
        let rawChecks = try root.required("date_checks").elements()
        guard rawChecks.count == 2 else { throw TripFailure.invalidResponse }
        let checks = try rawChecks.map { raw -> DateCheck in
            let check = try raw.fields("kind state day_indices item_ids reason evidence_refs")
            guard let kind = DateCheck.Kind(rawValue: try check.required("kind").text()),
                  let state = DateCheck.State(rawValue: try check.required("state").text()) else { throw TripFailure.invalidResponse }
            let indices = try check.required("day_indices").elements().map { Int(try $0.integer(1...Int64(days.count))) }
            let itemIDs = try check.required("item_ids").elements().map(tripWireID)
            let reason = try boundedTripText(check.required("reason"), maximum: 500)
            let evidence = try check.required("evidence_refs").elements().map { try boundedTripText($0, maximum: 4096) }
            guard !indices.isEmpty, Set(indices).count == indices.count, Set(itemIDs).count == itemIDs.count,
                  Set(itemIDs).isSubset(of: ids), evidence.count <= 40 else { throw TripFailure.invalidResponse }
            switch calendar {
            case .undated:
                guard state == .notChecked, reason == "date_not_set", evidence.isEmpty else { throw TripFailure.invalidResponse }
            case .dated:
                guard state != .notChecked, (state != .clear && state != .conflict) || !evidence.isEmpty else { throw TripFailure.invalidResponse }
            }
            return DateCheck(kind: kind, state: state, dayIndices: indices, itemIDs: itemIDs,
                             reason: reason, evidenceReferences: evidence)
        }
        guard Set(checks.map(\.kind)).count == 2 else { throw TripFailure.invalidResponse }
        return Self(title: validated.title, calendar: calendar, days: days, items: items,
                    sources: validated.sources, dateChecks: checks, originalUTF8: bytes)
    }
}

/// Clock-free proleptic Gregorian arithmetic; no device timezone participates.
struct OrdinalTripDate {
    private var year: Int
    private var month: Int
    private var day: Int
    init(_ value: String) throws {
        let bytes = Array(value.utf8)
        guard bytes.count == 10, bytes[4] == 45, bytes[7] == 45,
              bytes.enumerated().allSatisfy({ [4, 7].contains($0.offset) || (48...57).contains($0.element) }),
              let year = Int(value.prefix(4)), year > 0,
              let month = Int(value.dropFirst(5).prefix(2)), (1...12).contains(month),
              let day = Int(value.suffix(2)), (1...Self.length(year, month)).contains(day) else { throw TripFailure.invalidResponse }
        self.year = year; self.month = month; self.day = day
    }
    var text: String { String(format: "%04d-%02d-%02d", year, month, day) }
    mutating func advance() throws {
        day += 1
        if day > Self.length(year, month) { day = 1; month += 1 }
        if month > 12 { month = 1; year += 1 }
        guard year <= 9999 else { throw TripFailure.invalidResponse }
    }
    private static func length(_ year: Int, _ month: Int) -> Int {
        let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
        return [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    }
}
