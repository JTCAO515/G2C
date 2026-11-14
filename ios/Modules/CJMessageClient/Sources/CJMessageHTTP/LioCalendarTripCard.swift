import CJStrictJSON
import Foundation

/// Frozen LIO-trip-card.2 data. Decoding a summary never grants a read, edit or undo capability.
public struct LioCalendarTripCard: Equatable, Sendable {
    public enum ContentVersion: String, Sendable { case first = "structured.1", second = "structured.2", calendar = "structured.3" }
    public enum CalendarState: Equatable, Sendable { case undated, dated(startDate: String) }

    public struct Item: Equatable, Sendable {
        public let id: String
        public let label: String
        public let startTime: String?
        public let endTime: String?
        public let fixed: Bool?
    }
    public struct Day: Equatable, Sendable {
        /// Nil only for legacy content; it is not an inferred ordinal or an undated calendar.
        public let index: Int64?
        public let date: String?
        public let items: [Item]
    }
    public struct DateCheck: Equatable, Sendable {
        public enum Kind: String, Sendable { case weather, dayOpening = "day_opening" }
        public enum State: String, Sendable { case notChecked = "not_checked", unknown, clear, conflict }
        public let kind: Kind
        public let state: State
        public let dayIndices: [Int64]
        public let itemIDs: [String]
        public let reason: String
        public let evidenceReferences: [String]
    }

    public let id: String
    public let tripVersion: Int64
    public let contentVersion: ContentVersion
    public let contentSHA256: String
    public let title: String
    public let calendar: CalendarState?
    public let days: [Day]
    public let dateChecks: [DateCheck]?
    /// Exact decoder input, including its enclosing response when read inside a timeline/history.
    /// These bytes are retained for observation, not interpreted as a write source.
    public let inputUTF8: Data

    public static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.id == rhs.id && lhs.tripVersion == rhs.tripVersion && lhs.contentVersion == rhs.contentVersion
            && lhs.contentSHA256 == rhs.contentSHA256 && lhs.title == rhs.title && lhs.calendar == rhs.calendar
            && lhs.days == rhs.days && lhs.dateChecks == rhs.dateChecks
    }

    public static func decode(_ bytes: Data) throws -> Self {
        guard !bytes.isEmpty, bytes.count <= 4_500_000 else { throw MessageHTTPFailure.invalidResponse }
        var reader = StrictJSON(bytes: Array(bytes))
        let root = try reader.document()
        return try read(root, inputUTF8: bytes)
    }

    static func read(_ root: StrictJSONValue, inputUTF8: Data) throws -> Self {
        let f = try CardJSON.fields(root, "version trip_id trip_version content_version content_sha256 title calendar days date_checks")
        guard try CardJSON.text(f["version"]) == "LIO-trip-card.2",
              let version = ContentVersion(rawValue: try CardJSON.text(f["content_version"])) else {
            throw MessageHTTPFailure.invalidResponse
        }
        let calendar: CalendarState?
        if version == .calendar {
            let value = try CardJSON.object(f["calendar"])
            switch try CardJSON.text(value["state"]) {
            case "undated":
                _ = try CardJSON.fields(f["calendar"], "state")
                calendar = .undated
            case "dated":
                let value = try CardJSON.fields(f["calendar"], "state start_date")
                let start = try CardJSON.text(value["start_date"])
                _ = try CardDate(start)
                calendar = .dated(startDate: start)
            default: throw MessageHTTPFailure.invalidResponse
            }
        } else {
            guard case .null? = f["calendar"], case .null? = f["date_checks"] else { throw MessageHTTPFailure.invalidResponse }
            calendar = nil
        }

        let rawDays = try CardJSON.array(f["days"])
        guard !rawDays.isEmpty else { throw MessageHTTPFailure.invalidResponse }
        var expectedDate: CardDate?
        if case .dated(let start) = calendar { expectedDate = try CardDate(start) }
        var ids = Set<String>()
        let days = try rawDays.enumerated().map { position, raw -> Day in
            let keys: String
            switch calendar {
            case .undated: keys = "day_index items"
            case .dated: keys = "day_index date items"
            case nil: keys = "date items"
            }
            let day = try CardJSON.fields(raw, keys)
            let index: Int64?
            if calendar != nil {
                let value = try CardJSON.integer(day["day_index"])
                guard value == Int64(position + 1) else { throw MessageHTTPFailure.invalidResponse }
                index = value
            } else { index = nil }
            let date: String?
            switch calendar {
            case .undated: date = nil
            case .dated:
                let value = try CardJSON.text(day["date"])
                guard value == expectedDate?.text else { throw MessageHTTPFailure.invalidResponse }
                date = value
                if position + 1 < rawDays.count { try expectedDate?.advance() }
            case nil:
                date = try CardJSON.nullableText(day["date"])
                if let date { _ = try CardDate(date) }
            }
            let values = try CardJSON.array(day["items"])
            guard values.count <= 60 else { throw MessageHTTPFailure.invalidResponse }
            let items = try values.map { raw -> Item in
                let item = try CardJSON.fields(raw, "item_id label start_time end_time fixed")
                let id = try CardJSON.identifier(item["item_id"])
                guard ids.insert(id).inserted else { throw MessageHTTPFailure.invalidResponse }
                return try Item(id: id, label: CardJSON.text(item["label"], maximum: 500),
                                startTime: CardJSON.time(item["start_time"]), endTime: CardJSON.time(item["end_time"]),
                                fixed: CardJSON.nullableBool(item["fixed"]))
            }
            return Day(index: index, date: date, items: items)
        }

        let checks: [DateCheck]?
        if let calendar {
            let values = try CardJSON.array(f["date_checks"])
            guard values.count == 2 else { throw MessageHTTPFailure.invalidResponse }
            let decoded = try values.map { raw -> DateCheck in
                let check = try CardJSON.fields(raw, "kind state day_indices item_ids reason evidence_refs")
                guard let kind = DateCheck.Kind(rawValue: try CardJSON.text(check["kind"])),
                      let state = DateCheck.State(rawValue: try CardJSON.text(check["state"])) else {
                    throw MessageHTTPFailure.invalidResponse
                }
                let indices = try CardJSON.array(check["day_indices"]).map { try CardJSON.integer($0) }
                let itemIDs = try CardJSON.array(check["item_ids"]).map { try CardJSON.identifier($0) }
                let evidence = try CardJSON.array(check["evidence_refs"]).map { try CardJSON.text($0, maximum: 4096) }
                let reason = try CardJSON.text(check["reason"], maximum: 500)
                guard !indices.isEmpty, Set(indices).count == indices.count,
                      indices.allSatisfy({ $0 <= Int64(days.count) }),
                      Set(itemIDs).count == itemIDs.count, Set(itemIDs).isSubset(of: ids), evidence.count <= 40 else {
                    throw MessageHTTPFailure.invalidResponse
                }
                switch calendar {
                case .undated:
                    guard state == .notChecked, reason == "date_not_set", evidence.isEmpty else { throw MessageHTTPFailure.invalidResponse }
                case .dated:
                    guard state != .notChecked, (state != .clear && state != .conflict) || !evidence.isEmpty else {
                        throw MessageHTTPFailure.invalidResponse
                    }
                }
                return DateCheck(kind: kind, state: state, dayIndices: indices, itemIDs: itemIDs,
                                 reason: reason, evidenceReferences: evidence)
            }
            guard Set(decoded.map(\.kind)).count == 2 else { throw MessageHTTPFailure.invalidResponse }
            checks = decoded
        } else { checks = nil }
        return try Self(id: CardJSON.identifier(f["trip_id"]), tripVersion: CardJSON.integer(f["trip_version"]),
                        contentVersion: version, contentSHA256: CardJSON.hash(f["content_sha256"]),
                        title: CardJSON.text(f["title"], maximum: 120), calendar: calendar, days: days,
                        dateChecks: checks, inputUTF8: inputUTF8)
    }
}

enum CardJSON {
    static func object(_ value: StrictJSONValue?) throws -> [String: StrictJSONValue] {
        guard case .object(let result) = value else { throw MessageHTTPFailure.invalidResponse }
        return result
    }
    static func fields(_ value: StrictJSONValue?, _ names: String) throws -> [String: StrictJSONValue] {
        let result = try object(value)
        guard Set(result.keys) == Set(names.split(separator: " ").map(String.init)) else { throw MessageHTTPFailure.invalidResponse }
        return result
    }
    static func array(_ value: StrictJSONValue?) throws -> [StrictJSONValue] {
        guard case .array(let result) = value else { throw MessageHTTPFailure.invalidResponse }
        return result
    }
    static func text(_ value: StrictJSONValue?, maximum: Int = 128) throws -> String {
        guard case .string(let text) = value, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              text.unicodeScalars.count <= maximum else { throw MessageHTTPFailure.invalidResponse }
        return text
    }
    static func nullableText(_ value: StrictJSONValue?) throws -> String? {
        if case .null? = value { return nil }
        return try text(value)
    }
    static func integer(_ value: StrictJSONValue?) throws -> Int64 {
        guard case .number(let token) = value, token.utf8.allSatisfy({ (48...57).contains($0) }),
              let result = Int64(token), result > 0 else { throw MessageHTTPFailure.invalidResponse }
        return result
    }
    static func identifier(_ value: StrictJSONValue?) throws -> String {
        let result = try text(value)
        guard MessageTripSelection.identifier(result) else { throw MessageHTTPFailure.invalidResponse }
        return result
    }
    static func hash(_ value: StrictJSONValue?) throws -> String {
        let result = try text(value)
        guard result.utf8.count == 64, result.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else {
            throw MessageHTTPFailure.invalidResponse
        }
        return result
    }
    static func nullableBool(_ value: StrictJSONValue?) throws -> Bool? {
        if case .null? = value { return nil }
        guard case .boolean(let result) = value else { throw MessageHTTPFailure.invalidResponse }
        return result
    }
    static func time(_ value: StrictJSONValue?) throws -> String? {
        guard let result = try nullableText(value) else { return nil }
        guard let match = result.range(of: #"(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?"#, options: .regularExpression),
              match == result.startIndex..<result.endIndex else { throw MessageHTTPFailure.invalidResponse }
        return result
    }
}

/// Gregorian date arithmetic only; it never observes the clock or invents a trip timezone.
struct CardDate {
    private var year: Int
    private var month: Int
    private var day: Int

    init(_ text: String) throws {
        let bytes = Array(text.utf8)
        guard bytes.count == 10, bytes[4] == 45, bytes[7] == 45,
              bytes.enumerated().allSatisfy({ [4, 7].contains($0.offset) || (48...57).contains($0.element) }),
              let year = Int(text.prefix(4)), year > 0,
              let month = Int(text.dropFirst(5).prefix(2)), (1...12).contains(month),
              let day = Int(text.suffix(2)), (1...Self.monthLength(year, month)).contains(day) else {
            throw MessageHTTPFailure.invalidResponse
        }
        self.year = year; self.month = month; self.day = day
    }
    var text: String { String(format: "%04d-%02d-%02d", year, month, day) }
    mutating func advance() throws {
        day += 1
        if day > Self.monthLength(year, month) { day = 1; month += 1 }
        if month > 12 { month = 1; year += 1 }
        guard year <= 9999 else { throw MessageHTTPFailure.invalidResponse }
    }
    private static func monthLength(_ year: Int, _ month: Int) -> Int {
        let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
        return [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    }
}
