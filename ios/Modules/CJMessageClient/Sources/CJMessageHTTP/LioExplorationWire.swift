import Foundation
import CJStrictJSON

/// Frozen LIO-timeline.4 data only. No send, transport, original-action or source capability.
public enum LioExplorationWire {
    public struct Segment: Equatable, Sendable {
        public enum Purpose: String, Sendable { case response, direction, question, notice, summary }
        public let purpose: Purpose
        public let text: String
    }
    public struct Option: Equatable, Sendable {
        public let id: String
        public let displayText: String
        public let sendText: String
    }
    public struct QuestionGroup: Equatable, Sendable {
        public let factor: String
        public let question: String
        public let multiple: Bool
        public let options: [Option]
    }
    public struct Profile: Equatable, Sendable {
        public enum State: String, Sendable { case known, notNeeded = "not_needed", inferred, defaultValue = "default", memory }
        public let factor: String
        public let displayText: String
        public let state: State
    }
    public struct Citation: Equatable, Sendable {
        public let title: String
        public let rawURL: String?
        public let observedAt: String?
        public var link: URL? {
            guard let rawURL, let url = URL(string: rawURL), url.scheme?.lowercased() == "https",
                  url.host?.isEmpty == false, url.user == nil, url.password == nil else { return nil }
            return url
        }
    }
    public struct Notice: Equatable, Sendable {
        public enum Kind: String, Sendable { case weather, dayOpening = "day_opening", reservation, holiday, longTransfer = "long_transfer", season }
        public enum Severity: String, Sendable { case info, warning }
        public let id: String
        public let kind: Kind
        public let severity: Severity
        public let itemIDs: [String]
        public let text: String
        public let source: Citation
    }
    public struct Exit: Equatable, Sendable {
        public let id: String
        public let displayText: String
        public let sendText: String
    }
    public enum Progress: Equatable, Sendable {
        case waiting(String)
        case planningStarted(text: String, days: Int)
    }
    public struct RichCard: Equatable, Sendable {
        public let id: String
        public let tripVersion: Int64
        public let contentSHA256: String
        public let title: String
        public let calendar: LioCalendarTripCard.CalendarState
        public let days: [LioCalendarTripCard.Day]
        public let dateChecks: [LioCalendarTripCard.DateCheck]
    }
    public enum Trip: Equatable, Sendable { case calendar(LioCalendarTripCard), rich(RichCard) }
    public struct Message: Equatable, Sendable {
        public let id: String
        public let question: String
        public let answer: String
        public let state: LioTimelineWire.Message.State
        public let activity: LioTimelineWire.Activity?
        public let sources: [Citation]
        public let trip: Trip?
        public let memoryTags: [LioMemoryWire.Tag]
        public let segments: [Segment]
        public let questions: [QuestionGroup]
        public let profile: [Profile]
        public let notices: [Notice]
        public let exits: [Exit]
        public let progress: Progress?
    }
    public struct Page: Sendable {
        public let conversationID: String?
        public let messages: [Message]
        public let nextBefore: String?
        public let inputUTF8: Data
    }

    public static func decodePage(_ bytes: Data, for expectedConversationID: String? = nil) throws -> Page {
        guard !bytes.isEmpty, bytes.count <= 4_500_000 else { throw MessageHTTPFailure.invalidResponse }
        var parser = StrictJSON(bytes: Array(bytes))
        let root = try CardJSON.fields(parser.document(), "version conversation_id messages next_before")
        guard try text(root["version"]) == "LIO-timeline.4" else { throw MessageHTTPFailure.invalidResponse }
        let id = try optionalText(root["conversation_id"]), next = try optionalText(root["next_before"])
        let rows = try CardJSON.array(root["messages"])
        guard id.map(LioTimelineWire.validConversationID) ?? (rows.isEmpty && next == nil),
              expectedConversationID.map({ id == $0 && LioTimelineWire.validConversationID($0) }) ?? true else {
            throw MessageHTTPFailure.invalidResponse
        }
        let messages = try rows.map { try readMessage($0, input: bytes) }
        guard Set(messages.map { Data($0.id.utf8) }).count == messages.count,
              next.map({ messages.first?.id.utf8.elementsEqual($0.utf8) == true }) ?? true else {
            throw MessageHTTPFailure.invalidResponse
        }
        return Page(conversationID: id, messages: messages, nextBefore: next, inputUTF8: bytes)
    }

    private static func readMessage(_ raw: StrictJSONValue, input: Data) throws -> Message {
        let row = try CardJSON.fields(raw, "message_id text answer status failure activity sources trip memory segments question_groups profile notices exits progress")
        let id = try text(row["message_id"]), question = try text(row["text"])
        guard LioTimelineWire.validMessageID(id), !question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !question.utf8.contains(0), question.utf8.count <= 12_000 else { throw MessageHTTPFailure.invalidResponse }
        let status = try text(row["status"]), failure = try optionalText(row["failure"])
        let state: LioTimelineWire.Message.State
        switch (status, failure) {
        case ("sending", nil): state = .waiting
        case ("answering", nil): state = .answering
        case ("completed", nil): state = .completed
        case ("failed", "quota"): state = .serviceLimit
        case ("failed", "unavailable"): state = .unavailable
        default: throw MessageHTTPFailure.invalidResponse
        }
        let activity: LioTimelineWire.Activity?
        if let value = try optionalText(row["activity"]) {
            guard let parsed = LioTimelineWire.Activity(rawValue: value) else { throw MessageHTTPFailure.invalidResponse }
            activity = parsed
        } else { activity = nil }
        let segments = try array(row["segments"], maximum: 32).map { raw -> Segment in
            let f = try CardJSON.fields(raw, "purpose text")
            guard let purpose = Segment.Purpose(rawValue: try text(f["purpose"])) else { throw MessageHTTPFailure.invalidResponse }
            return try Segment(purpose: purpose, text: boundedText(f["text"], maximum: 12_000))
        }
        let questions = try array(row["question_groups"], maximum: 4).map { raw -> QuestionGroup in
            let f = try CardJSON.fields(raw, "factor_key question multiple options")
            let key = try factor(f["factor_key"])
            guard case .boolean(let multiple)? = f["multiple"] else { throw MessageHTTPFailure.invalidResponse }
            let rawOptions = try array(f["options"], maximum: 4)
            guard rawOptions.count >= 3 else { throw MessageHTTPFailure.invalidResponse }
            let options = try rawOptions.map { raw -> Option in
                let option = try CardJSON.fields(raw, "id display_text send_text"), id = try presentationID(option["id"])
                guard id.hasPrefix(key + ".") else { throw MessageHTTPFailure.invalidResponse }
                return try Option(id: id, displayText: boundedText(option["display_text"], maximum: 500), sendText: sendText(option["send_text"]))
            }
            try unique(options.map(\.id))
            return try QuestionGroup(factor: key, question: boundedText(f["question"], maximum: 500), multiple: multiple, options: options)
        }
        let profile = try array(row["profile"], maximum: 14).map { raw -> Profile in
            let f = try CardJSON.fields(raw, "factor_key display_text state")
            guard let state = Profile.State(rawValue: try text(f["state"])) else { throw MessageHTTPFailure.invalidResponse }
            return try Profile(factor: factor(f["factor_key"]), displayText: boundedText(f["display_text"], maximum: 500), state: state)
        }
        let notices = try array(row["notices"], maximum: 2).map { raw -> Notice in
            let f = try CardJSON.fields(raw, "id type severity item_ids text source")
            guard let kind = Notice.Kind(rawValue: try text(f["type"])),
                  let severity = Notice.Severity(rawValue: try text(f["severity"])) else { throw MessageHTTPFailure.invalidResponse }
            let items = try array(f["item_ids"], maximum: 128).map(presentationID)
            try unique(items)
            return try Notice(id: presentationID(f["id"]), kind: kind, severity: severity, itemIDs: items,
                              text: boundedText(f["text"], maximum: 12_000), source: citation(f["source"]))
        }
        let exits = try array(row["exits"], maximum: 4).map { raw -> Exit in
            let f = try CardJSON.fields(raw, "id display_text send_text")
            return try Exit(id: presentationID(f["id"]), displayText: boundedText(f["display_text"], maximum: 500), sendText: sendText(f["send_text"]))
        }
        try unique(questions.map(\.factor)); try unique(profile.map(\.factor)); try unique(notices.map(\.id)); try unique(exits.map(\.id))
        let progress = try progress(row["progress"])
        guard !["completed", "failed"].contains(status) || progress == nil else { throw MessageHTTPFailure.invalidResponse }
        let answer = try text(row["answer"])
        if !segments.isEmpty || !questions.isEmpty || !notices.isEmpty || !exits.isEmpty {
            var parts = segments.map(\.text)
            parts += questions.map { $0.question + "\n" + $0.options.map(\.displayText).joined(separator: " / ") }
            parts += notices.map(\.text)
            if !exits.isEmpty { parts.append(exits.map(\.displayText).joined(separator: " / ")) }
            guard answer == parts.joined(separator: "\n\n") else { throw MessageHTTPFailure.invalidResponse }
        }
        let trip: Trip?
        if case .null? = row["trip"] { trip = nil }
        else {
            guard state == .completed else { throw MessageHTTPFailure.invalidResponse }
            let value = try CardJSON.object(row["trip"])
            switch try text(value["version"]) {
            case "LIO-trip-card.2": trip = .calendar(try LioCalendarTripCard.read(row["trip"]!, inputUTF8: input))
            case "LIO-trip-card.3": trip = .rich(try richCard(row["trip"]!))
            default: throw MessageHTTPFailure.invalidResponse
            }
        }
        let tags = try memory(row["memory"])
        return try Message(id: id, question: question, answer: answer, state: state, activity: activity,
            sources: CardJSON.array(row["sources"]).map(citation), trip: trip, memoryTags: state == .completed ? tags : [],
            segments: segments, questions: questions, profile: profile, notices: notices, exits: exits, progress: progress)
    }

    private static func richCard(_ raw: StrictJSONValue) throws -> RichCard {
        var fields = try CardJSON.fields(raw, "version trip_id trip_version content_version content_sha256 title calendar days date_checks")
        guard try text(fields["version"]) == "LIO-trip-card.3", try text(fields["content_version"]) == "structured.4",
              try CardJSON.array(fields["days"]).count <= 366 else { throw MessageHTTPFailure.invalidResponse }
        _ = try presentationID(fields["trip_id"])
        fields["version"] = .string("LIO-trip-card.2"); fields["content_version"] = .string("structured.3")
        // Private field-validation copy only. It never escapes as a Card2 or a source.
        let common = try LioCalendarTripCard.read(.object(fields), inputUTF8: Data())
        guard let calendar = common.calendar, let checks = common.dateChecks else { throw MessageHTTPFailure.invalidResponse }
        for day in common.days { for item in day.items { _ = try presentationID(.string(item.id)) } }
        return RichCard(id: common.id, tripVersion: common.tripVersion, contentSHA256: common.contentSHA256,
                        title: common.title, calendar: calendar, days: common.days, dateChecks: checks)
    }
    private static func progress(_ raw: StrictJSONValue?) throws -> Progress? {
        if case .null? = raw { return nil }
        let f = try CardJSON.object(raw)
        switch try text(f["kind"]) {
        case "waiting":
            _ = try CardJSON.fields(raw, "kind text")
            return try .waiting(boundedText(f["text"], maximum: 500))
        case "planning_started":
            _ = try CardJSON.fields(raw, "kind text duration_days")
            let days = try CardJSON.integer(f["duration_days"])
            guard days <= 366 else { throw MessageHTTPFailure.invalidResponse }
            return try .planningStarted(text: boundedText(f["text"], maximum: 500), days: Int(days))
        default: throw MessageHTTPFailure.invalidResponse
        }
    }
    private static func citation(_ raw: StrictJSONValue?) throws -> Citation {
        let f = try CardJSON.fields(raw, "title url observed_at")
        let title = try boundedText(f["title"], maximum: Int.max), url = try optionalText(f["url"])
        if let url { guard URL(string: url)?.scheme?.isEmpty == false else { throw MessageHTTPFailure.invalidResponse } }
        let observed = try optionalText(f["observed_at"])
        if let observed {
            let parser = ISO8601DateFormatter()
            parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if parser.date(from: observed) == nil {
                parser.formatOptions = [.withInternetDateTime]
                guard parser.date(from: observed) != nil else { throw MessageHTTPFailure.invalidResponse }
            }
        }
        return Citation(title: title, rawURL: url, observedAt: observed)
    }
    private static func memory(_ raw: StrictJSONValue?) throws -> [LioMemoryWire.Tag] {
        if case .null? = raw { return [] }
        let f = try CardJSON.fields(raw, "tags"), nodes = try array(f["tags"], maximum: 50)
        guard !nodes.isEmpty else { throw MessageHTTPFailure.invalidResponse }
        let values = try nodes.map { node -> LioMemoryWire.Tag in
            let tag = try CardJSON.fields(node, "id kind text target")
            var dictionary: [String: String] = [:]
            for key in ["id", "kind", "text", "target"] { dictionary[key] = try text(tag[key]) }
            return try JSONDecoder().decode(LioMemoryWire.Tag.self, from: JSONSerialization.data(withJSONObject: dictionary))
        }
        guard values.allSatisfy(\.isValid) else { throw MessageHTTPFailure.invalidResponse }
        try unique(values.map(\.id)); return values
    }
    private static func text(_ raw: StrictJSONValue?) throws -> String {
        guard case .string(let text) = raw else { throw MessageHTTPFailure.invalidResponse }
        return text
    }
    private static func boundedText(_ raw: StrictJSONValue?, maximum: Int) throws -> String {
        let value = try text(raw)
        guard !value.isEmpty, value.unicodeScalars.count <= maximum else { throw MessageHTTPFailure.invalidResponse }
        return value
    }
    private static func optionalText(_ raw: StrictJSONValue?) throws -> String? {
        if case .null? = raw { return nil }
        return try text(raw)
    }
    private static func array(_ raw: StrictJSONValue?, maximum: Int) throws -> [StrictJSONValue] {
        let values = try CardJSON.array(raw)
        guard values.count <= maximum else { throw MessageHTTPFailure.invalidResponse }
        return values
    }
    private static func unique(_ values: [String]) throws {
        guard Set(values).count == values.count else { throw MessageHTTPFailure.invalidResponse }
    }
    private static func presentationID(_ raw: StrictJSONValue?) throws -> String {
        try CardJSON.identifier(raw)
    }
    private static func factor(_ raw: StrictJSONValue?) throws -> String {
        let value = try text(raw)
        let factors: Set<String> = ["city", "duration_days", "season", "first_visit", "party_type", "interests", "pace", "lodging_tier", "dietary", "must_see", "avoid", "mobility", "arrival", "departure"]
        guard factors.contains(value) else { throw MessageHTTPFailure.invalidResponse }
        return value
    }
    private static func sendText(_ raw: StrictJSONValue?) throws -> String {
        let value = try boundedText(raw, maximum: 500)
        guard value.rangeOfCharacter(from: .whitespacesAndNewlines.inverted) != nil, !hasSendControl(value) else { throw MessageHTTPFailure.invalidResponse }
        return value
    }
    private static func hasSendControl(_ value: String) -> Bool {
        value.unicodeScalars.contains { $0.value < 32 || (127...159).contains($0.value) || [0x2028, 0x2029].contains($0.value) }
    }
}
