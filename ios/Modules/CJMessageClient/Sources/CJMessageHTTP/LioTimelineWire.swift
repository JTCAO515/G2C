import Foundation

/// Client-side wire boundary for the additive Lio timeline. This does not
/// grant a network route or a write capability.
public enum LioTimelineWire {
    public enum Locale: String, Sendable { case english = "en", chinese = "zh" }

    public struct Send: Sendable {
        public let messageID: String
        public let conversationID: String?
        public let originalUTF8: Data

        public init(messageID: String, text: String, locale: Locale, conversationID: String? = nil) throws {
            guard LioTimelineWire.validMessageID(messageID),
                  !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  !text.utf8.contains(0), text.utf8.count <= 12_000,
                  conversationID.map(LioTimelineWire.validConversationID) ?? true else {
                throw MessageHTTPFailure.invalidConfiguration
            }
            var value = ["version": "LIO-message.1", "message_id": messageID,
                         "text": text, "locale": locale.rawValue]
            if let conversationID { value["conversation_id"] = conversationID }
            let bytes = try JSONEncoder().encode(value)
            guard bytes.count <= 16_384 else { throw MessageHTTPFailure.invalidConfiguration }
            self.messageID = messageID
            self.conversationID = conversationID
            originalUTF8 = bytes
        }

        /// A transport may reuse originalUTF8 for an explicitly authorized same
        /// send. It must not regenerate these bytes or dispatch a new question
        /// from an ambiguous response.
        public func confirm(_ response: Data) throws -> String {
            guard response.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
            try validateUnambiguousJSON(response)
            let reply = try JSONDecoder().decode(Acceptance.self, from: response)
            guard reply.version == "LIO-message-receipt.1",
                  reply.messageID.utf8.elementsEqual(messageID.utf8),
                  LioTimelineWire.validConversationID(reply.conversationID),
                  conversationID.map({ $0 == reply.conversationID }) ?? true else {
                throw MessageHTTPFailure.invalidResponse
            }
            return reply.conversationID
        }
    }

    public struct Source: Sendable, Equatable {
        public let title: String
        public let link: URL?
        public let observedAt: String?
    }

    public enum Activity: String, Sendable, Decodable {
        case places = "checking_places"
        case weather = "checking_weather"
        case travelInformation = "checking_travel_information"
    }

    public struct SavedTrip: Decodable, Sendable, Equatable {
        public struct Day: Decodable, Sendable, Equatable {
            public struct Item: Decodable, Sendable, Equatable {
                public let id: String
                public let label: String
                public let startTime: String?
                public let endTime: String?
                public let fixed: Bool?

                enum CodingKeys: String, CodingKey {
                    case id = "item_id", label, startTime = "start_time", endTime = "end_time", fixed
                }
            }

            public let date: String?
            public let items: [Item]
        }

        public let id: String
        public let title: String
        public let days: [Day]

        enum CodingKeys: String, CodingKey { case id = "trip_id", title, days }
    }

    public struct Message: Sendable, Equatable {
        public enum State: Equatable, Sendable {
            case waiting, answering, completed, dailyLimit
            /// The current wire does not distinguish definitive failure from
            /// a lost result. This does not authorize a new write.
            case unavailable
        }

        public let id: String
        public let question: String
        public let answer: String
        public let state: State
        public let activity: Activity?
        public let sources: [Source]
        public let trip: SavedTrip?
    }

    public struct Page: Sendable, Equatable {
        public let conversationID: String?
        public let messages: [Message]
        public let nextBefore: String?
    }

    public static func decodePage(_ data: Data, for expectedConversationID: String? = nil) throws -> Page {
        guard data.count <= 4_500_000 else { throw MessageHTTPFailure.invalidResponse }
        try validateUnambiguousJSON(data)
        let page = try JSONDecoder().decode(Snapshot.self, from: data)
        guard page.version == "LIO-timeline.1", page.messages.count <= 20,
              page.conversationID.map(validConversationID) ?? (page.messages.isEmpty && page.nextBefore == nil),
              expectedConversationID.map({ $0 == page.conversationID }) ?? true,
              page.nextBefore.map({ cursor in
                  page.messages.first?.messageID.utf8.elementsEqual(cursor.utf8) == true
              }) ?? true,
              Set(page.messages.map { Data($0.messageID.utf8) }).count == page.messages.count else {
            throw MessageHTTPFailure.invalidResponse
        }
        return try Page(conversationID: page.conversationID, messages: page.messages.map(project),
                        nextBefore: page.nextBefore)
    }

    private static func project(_ wire: Snapshot.Row) throws -> Message {
        guard validMessageID(wire.messageID),
              !wire.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !wire.text.utf8.contains(0), wire.text.utf8.count <= 12_000 else {
            throw MessageHTTPFailure.invalidResponse
        }
        let state: Message.State
        switch (wire.status, wire.failure) {
        case (.sending, nil): state = .waiting
        case (.answering, nil): state = .answering
        case (.completed, nil): state = .completed
        case (.failed, .some(.quota)): state = .dailyLimit
        case (.failed, .some(.unavailable)): state = .unavailable
        default: throw MessageHTTPFailure.invalidResponse
        }
        let sources = wire.sources.compactMap { item -> Source? in
            guard let title = item.title, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
            let link = item.url.flatMap { URL(string: $0) }.flatMap { candidate in
                candidate.scheme?.lowercased() == "https" && candidate.host?.isEmpty == false
                    && candidate.user == nil && candidate.password == nil ? candidate : nil
            }
            return Source(title: title, link: link, observedAt: item.observedAt)
        }
        if let trip = wire.trip {
            let items = trip.days.flatMap(\.items)
            guard state == .completed, validMessageID(trip.id),
                  !trip.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  items.allSatisfy({ validMessageID($0.id) }),
                  Set(items.map(\.id)).count == items.count else {
                throw MessageHTTPFailure.invalidResponse
            }
        }
        return Message(id: wire.messageID, question: wire.text, answer: wire.answer, state: state,
                       activity: wire.activity, sources: sources, trip: wire.trip)
    }

    static func validMessageID(_ id: String) -> Bool {
        !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !id.utf8.contains(0) && id.utf8.count <= 256
    }

    static func validConversationID(_ id: String) -> Bool {
        let prefix = "lio-dialogue-"
        return id.hasPrefix(prefix) && id.utf8.count == prefix.utf8.count + 32
            && id.utf8.dropFirst(prefix.utf8.count).allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }

    private struct Acceptance: Decodable {
        let version: String
        let messageID: String
        let conversationID: String
        enum CodingKeys: String, CodingKey {
            case version, messageID = "message_id", conversationID = "conversation_id"
        }
    }

    private struct Snapshot: Decodable {
        struct Row: Decodable {
            enum Status: String, Decodable { case sending, answering, completed, failed }
            enum Failure: String, Decodable { case quota, unavailable }
            struct Citation: Decodable {
                let title: String?
                let url: String?
                let observedAt: String?
                enum CodingKeys: String, CodingKey { case title, url, observedAt = "observed_at" }
            }
            let messageID: String
            let text: String
            let answer: String
            let status: Status
            let failure: Failure?
            let activity: Activity?
            let sources: [Citation]
            let trip: SavedTrip?
            enum CodingKeys: String, CodingKey { case messageID = "message_id", text, answer, status, failure, activity, sources, trip }
        }
        let version: String
        let conversationID: String?
        let messages: [Row]
        let nextBefore: String?
        enum CodingKeys: String, CodingKey {
            case version, conversationID = "conversation_id", messages, nextBefore = "next_before"
        }
    }
}
