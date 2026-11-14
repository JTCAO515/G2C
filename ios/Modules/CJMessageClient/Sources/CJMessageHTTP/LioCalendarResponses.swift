import Foundation
import CJStrictJSON

/// Additional closed shapes for the explicit calendar wire. Common message
/// statuses, identities and consent tags still pass through their existing reader.
enum LioCalendarResponses {
    static func timelineTrips(_ bytes: Data) throws -> [LioCalendarTripCard?] {
        var reader = StrictJSON(bytes: Array(bytes))
        let root = try CardJSON.fields(reader.document(), "version conversation_id messages next_before")
        return try CardJSON.array(root["messages"]).map { raw in
            let row = try CardJSON.fields(raw, "message_id text answer status failure activity sources trip memory")
            for source in try CardJSON.array(row["sources"]) {
                let source = try CardJSON.fields(source, "title url observed_at")
                _ = try CardJSON.text(source["title"], maximum: Int.max)
                if let url = try nullableText(source["url"]) {
                    guard URL(string: url)?.scheme?.isEmpty == false else { throw MessageHTTPFailure.invalidResponse }
                }
                if let timestamp = try nullableText(source["observed_at"]) {
                    let parser = ISO8601DateFormatter()
                    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                    if parser.date(from: timestamp) == nil {
                        parser.formatOptions = [.withInternetDateTime]
                        guard parser.date(from: timestamp) != nil else { throw MessageHTTPFailure.invalidResponse }
                    }
                }
            }
            if case .null? = row["memory"] {} else {
                let memory = try CardJSON.fields(row["memory"], "tags")
                let tags = try CardJSON.array(memory["tags"])
                guard (1...50).contains(tags.count) else { throw MessageHTTPFailure.invalidResponse }
                for tag in tags { _ = try CardJSON.fields(tag, "id kind text target") }
            }
            if case .null? = row["trip"] { return nil }
            return try LioCalendarTripCard.read(row["trip"]!, inputUTF8: bytes)
        }
    }

    static func historyCards(_ bytes: Data) throws -> (current: LioCalendarTripCard?, history: [LioCalendarTripCard]) {
        var reader = StrictJSON(bytes: Array(bytes))
        let root = try CardJSON.fields(reader.document(), "version conversation_id current history undo_target next_before")
        let current: LioCalendarTripCard?
        if case .null? = root["current"] { current = nil }
        else { current = try LioCalendarTripCard.read(root["current"]!, inputUTF8: bytes) }
        let history = try CardJSON.array(root["history"]).map { try LioCalendarTripCard.read($0, inputUTF8: bytes) }
        return (current, history)
    }

    private static func nullableText(_ value: StrictJSONValue?) throws -> String? {
        if case .null? = value { return nil }
        return try CardJSON.text(value, maximum: Int.max)
    }
}
