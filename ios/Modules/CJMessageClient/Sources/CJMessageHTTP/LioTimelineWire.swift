import Foundation

/// Client-side wire boundary for the additive Lio timeline. This does not
/// grant a network route or a write capability.
public enum LioTimelineWire {
    public enum Locale: String, Sendable { case english = "en", chinese = "zh" }
    public enum Version: Int, Sendable { case v1 = 1, v2 = 2, v3 = 3, v4 = 4 }
    public enum V2Destination: Sendable {
        case defaultChat, newChat, existing(String)
    }

    public struct Send: Sendable {
        public let messageID: String
        public let conversationID: String?
        public let originalUTF8: Data
        let version: Version
        let startsNewChat: Bool

        public init(messageID: String, text: String, locale: Locale, conversationID: String? = nil) throws {
            try Self.validate(messageID, text, conversationID)
            var value = ["version": "LIO-message.1", "message_id": messageID,
                         "text": text, "locale": locale.rawValue]
            if let conversationID { value["conversation_id"] = conversationID }
            let bytes = try JSONEncoder().encode(value)
            guard bytes.count <= 16_384 else { throw MessageHTTPFailure.invalidConfiguration }
            self.messageID = messageID
            self.conversationID = conversationID
            originalUTF8 = bytes
            version = .v1
            startsNewChat = false
        }

        public init(messageID: String, text: String, locale: Locale, destination: V2Destination,
                    version: Version = .v2) throws {
            guard version == .v2 || version == .v3 || version == .v4 else { throw MessageHTTPFailure.invalidConfiguration }
            let conversationID: String?
            let newConversation: Bool?
            switch destination {
            case .defaultChat: (conversationID, newConversation) = (nil, nil)
            case .newChat: (conversationID, newConversation) = (nil, true)
            case .existing(let id): (conversationID, newConversation) = (id, nil)
            }
            try Self.validate(messageID, text, conversationID)
            let bytes = try JSONEncoder().encode(VersionedQuestion(version: "LIO-message.\(version.rawValue)", messageID: messageID, text: text, locale: locale.rawValue,
                                                            conversationID: conversationID, newConversation: newConversation))
            guard bytes.count <= 16_384 else { throw MessageHTTPFailure.invalidConfiguration }
            self.messageID = messageID
            self.conversationID = conversationID
            originalUTF8 = bytes
            self.version = version
            startsNewChat = newConversation == true
        }

        /// Other actions share the encrypted journal. Only first-chat originals
        /// carry this marker; once recognized, decode and bind the complete bytes.
        public static func recordedFirst(_ bytes: Data, messageID: String) throws -> (original: Send, title: String)? {
            let decoder = JSONDecoder()
            guard let marker = try? decoder.decode(FirstMarker.self, from: bytes),
                  ["LIO-message.2", "LIO-message.3", "LIO-message.4"].contains(marker.version), marker.newConversation == true else { return nil }
            if marker.version == "LIO-message.4" {
                let title = try LioNative4Envelope.firstQuestion(bytes, messageID: messageID)
                try validate(messageID, title, nil)
                return (Send(firstMessageID: messageID, bytes: bytes, version: .v4), title)
            }
            guard bytes.count <= 16_384 else { throw MessageHTTPFailure.invalidConfiguration }
            if marker.version == "LIO-message.3" {
                var reader = StrictJSON(bytes: Array(bytes))
                _ = try CardJSON.fields(reader.document(), "version message_id text locale new_conversation")
            } else { try validateUnambiguousJSON(bytes) }
            let recorded = try decoder.decode(VersionedQuestion.self, from: bytes)
            guard recorded.messageID.utf8.elementsEqual(messageID.utf8),
                  recorded.conversationID == nil, Locale(rawValue: recorded.locale) != nil else {
                throw MessageHTTPFailure.invalidConfiguration
            }
            try validate(messageID, recorded.text, nil)
            let version: Version = marker.version == "LIO-message.3" ? .v3 : .v2
            return (Send(firstMessageID: messageID, bytes: bytes, version: version), recorded.text)
        }

        private init(firstMessageID: String, bytes: Data, version: Version) {
            messageID = firstMessageID
            conversationID = nil
            originalUTF8 = bytes
            self.version = version
            startsNewChat = true
        }

        private static func validate(_ messageID: String, _ text: String, _ conversationID: String?) throws {
            guard LioTimelineWire.validMessageID(messageID),
                  !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  !text.utf8.contains(0), text.utf8.count <= 12_000,
                  conversationID.map(LioTimelineWire.validConversationID) ?? true else {
                throw MessageHTTPFailure.invalidConfiguration
            }
        }

        private struct FirstMarker: Decodable {
            let version: String
            let newConversation: Bool?
            enum CodingKeys: String, CodingKey { case version, newConversation = "new_conversation" }
        }

        private struct VersionedQuestion: Codable {
            let version: String
            let messageID: String
            let text: String
            let locale: String
            let conversationID: String?
            let newConversation: Bool?

            enum CodingKeys: String, CodingKey {
                case version, messageID = "message_id", text, locale
                case conversationID = "conversation_id", newConversation = "new_conversation"
            }
        }

        /// A transport may reuse originalUTF8 for an explicitly authorized same
        /// send. It must not regenerate these bytes or dispatch a new question
        /// from an ambiguous response.
        public func confirm(_ response: Data) throws -> String {
            if version == .v4 { return try LioNative4Envelope.confirm(response, original: self) }
            guard response.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
            if version == .v3 {
                var reader = StrictJSON(bytes: Array(response))
                _ = try CardJSON.fields(reader.document(), "version message_id conversation_id")
            } else { try validateUnambiguousJSON(response) }
            let reply = try JSONDecoder().decode(Acceptance.self, from: response)
            guard reply.version == "LIO-message-receipt.\(version.rawValue)",
                  reply.messageID.utf8.elementsEqual(messageID.utf8),
                  LioTimelineWire.validConversationID(reply.conversationID),
                  conversationID.map({ $0 == reply.conversationID }) ?? true else {
                throw MessageHTTPFailure.invalidResponse
            }
            return reply.conversationID
        }

        func confirmLookup(_ response: Data) throws -> (id: String, receipt: Data)? {
            if version == .v4 { return try LioNative4Envelope.lookup(response, original: self) }
            if version == .v3 {
                guard response.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
                var reader = StrictJSON(bytes: Array(response))
                let fields = try CardJSON.fields(reader.document(), "version receipt")
                guard try CardJSON.text(fields["version"]) == "LIO-message-lookup.3" else {
                    throw MessageHTTPFailure.invalidResponse
                }
                if case .null? = fields["receipt"] { return nil }
                let bytes = response.subdata(in: reader.rootMemberRanges["receipt"]!)
                return (try confirm(bytes), bytes)
            }
            try validateUnambiguousJSON(response)
            guard let lookup = try JSONSerialization.jsonObject(with: response) as? [String: Any],
                  lookup["version"] as? String == "LIO-message-lookup.\(version == .v3 ? 3 : 2)",
                  let value = lookup["receipt"] else { throw MessageHTTPFailure.invalidResponse }
            if value is NSNull { return nil }
            guard let receipt = value as? [String: Any] else { throw MessageHTTPFailure.invalidResponse }
            let bytes = try JSONSerialization.data(withJSONObject: receipt)
            return (try confirm(bytes), bytes)
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
        public let calendarSummary: LioCalendarTripCard?

        enum CodingKeys: String, CodingKey { case id = "trip_id", title, days }

        /// The old decoder intentionally ignores added calendar fields, as before.
        /// Only the explicit v3 reader may attach a validated Card2 summary.
        public init(from decoder: any Decoder) throws {
            let fields = try decoder.container(keyedBy: CodingKeys.self)
            id = try fields.decode(String.self, forKey: .id)
            title = try fields.decode(String.self, forKey: .title)
            days = try fields.decode([Day].self, forKey: .days)
            calendarSummary = nil
        }

        init(_ summary: LioCalendarTripCard) {
            id = summary.id
            title = summary.title
            days = summary.days.map { day in
                Day(date: day.date, items: day.items.map { item in
                    Day.Item(id: item.id, label: item.label, startTime: item.startTime,
                             endTime: item.endTime, fixed: item.fixed)
                })
            }
            calendarSummary = summary
        }

        init(id: String, title: String, days: [Day]) {
            self.id = id
            self.title = title
            self.days = days
            calendarSummary = nil
        }
    }

    public struct Message: Sendable, Equatable {
        public enum State: Equatable, Sendable {
            case waiting, answering, completed
            /// The service reported a limit after accepting the question.
            case serviceLimit
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
        public let memoryTags: [LioMemoryWire.Tag]
        /// LIO-answer-followups.1 (#1727), only on a v2 read that declared it; nil otherwise.
        public let layout: AnswerLayout?
        /// Fixed buttons under a finished answer; empty unless the server sent valid ones for a split answer.
        public let followups: [Followup]

        public init(id: String, question: String, answer: String, state: State, activity: Activity?, sources: [Source],
                    trip: SavedTrip?, memoryTags: [LioMemoryWire.Tag], layout: AnswerLayout? = nil, followups: [Followup] = []) {
            self.id = id; self.question = question; self.answer = answer; self.state = state; self.activity = activity
            self.sources = sources; self.trip = trip; self.memoryTags = memoryTags; self.layout = layout; self.followups = followups
        }
    }

    /// How the server says an answer is shown: `split` means two bubbles cut at the first blank line.
    public enum AnswerLayout: String, Sendable, Equatable { case split, single }

    /// One fixed button the server chose from the App's tool registry: a tool, its string parameters and its label.
    public struct Followup: Sendable, Equatable {
        public let tool: String
        public let parameters: [String: String]
        public let label: String
        public init(tool: String, parameters: [String: String], label: String) {
            self.tool = tool; self.parameters = parameters; self.label = label
        }
    }

    public static let answerFollowupsVersion = "LIO-answer-followups.1"

    public struct Page: Sendable, Equatable {
        public let conversationID: String?
        public let messages: [Message]
        public let nextBefore: String?
    }

    public static func decodePage(_ data: Data, for expectedConversationID: String? = nil,
                                  version: Version = .v1) throws -> Page {
        guard data.count <= 4_500_000 else { throw MessageHTTPFailure.invalidResponse }
        let calendarTrips: [LioCalendarTripCard?]?
        if version == .v3 { calendarTrips = try LioCalendarResponses.timelineTrips(data) }
        else { try validateUnambiguousJSON(data); calendarTrips = nil }
        let page = try JSONDecoder().decode(Snapshot.self, from: data)
        guard ["LIO-timeline.1", "LIO-timeline.2", "LIO-timeline.3"].contains(page.version),
              page.version == "LIO-timeline.\(version.rawValue)", page.messages.count <= 20,
              page.conversationID.map(validConversationID) ?? (page.messages.isEmpty && page.nextBefore == nil),
              expectedConversationID.map({ $0 == page.conversationID }) ?? true,
              page.nextBefore.map({ cursor in
                  page.messages.first?.messageID.utf8.elementsEqual(cursor.utf8) == true
              }) ?? true,
              Set(page.messages.map { Data($0.messageID.utf8) }).count == page.messages.count else {
            throw MessageHTTPFailure.invalidResponse
        }
        return try Page(conversationID: page.conversationID, messages: page.messages.enumerated().map { index, row in
            let trip: SavedTrip?
            if let calendarTrips { trip = calendarTrips[index].map(SavedTrip.init) }
            else { trip = row.trip }
            return try project(row, trip: trip)
        },
                        nextBefore: page.nextBefore)
    }

    private static func project(_ wire: Snapshot.Row, trip: SavedTrip?) throws -> Message {
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
        // A failed row can carry a service limit after the send was accepted.
        // Only the send endpoint can establish the user's daily question cap.
        case (.failed, .some(.quota)): state = .serviceLimit
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
        if let trip {
            guard state == .completed, validSavedTrip(trip) else {
                throw MessageHTTPFailure.invalidResponse
            }
        }
        let tags = state == .completed ? wire.memory?.tags ?? [] : []
        guard tags.allSatisfy(\.isValid), Set(tags.map(\.id)).count == tags.count else {
            throw MessageHTTPFailure.invalidResponse
        }
        let layout = wire.layout.flatMap(AnswerLayout.init(rawValue:))
        // A layout the App does not know is read as no layout: the row is still shown as before.
        let followups = (state == .completed && layout == .split) ? validFollowups(wire.followups) : []
        return Message(id: wire.messageID, question: wire.text, answer: wire.answer, state: state,
                       activity: wire.activity, sources: sources, trip: trip, memoryTags: tags,
                       layout: layout, followups: followups)
    }

    /// Buttons that do not pass the checks are dropped as a set: a damaged list never puts a partial or
    /// unlisted button on screen, and never fails the page.
    private static func validFollowups(_ wire: Snapshot.Row.Followups?) -> [Followup] {
        guard let wire, wire.version == answerFollowupsVersion, (1...2).contains(wire.actions.count) else { return [] }
        var result: [Followup] = []
        for action in wire.actions {
            guard validToken(action.tool, limit: 64), validText(action.label, limit: 60),
                  action.parameters.count <= 8,
                  action.parameters.allSatisfy({ validToken($0.key, limit: 64) && validText($0.value, limit: 200) }),
                  (try? JSONSerialization.data(withJSONObject: action.parameters).count).map({ $0 <= 600 }) == true else { return [] }
            result.append(Followup(tool: action.tool, parameters: action.parameters, label: action.label))
        }
        return result
    }

    private static func validToken(_ value: String, limit: Int) -> Bool {
        !value.isEmpty && value.utf8.count <= limit
            && value.utf8.allSatisfy { (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 95 }
    }

    /// Non-empty after trimming, within the limit, and without control, separator, zero-width or bidirectional
    /// format characters (the contract's rule for values and labels).
    private static func validText(_ value: String, limit: Int) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed == value, !value.isEmpty, value.count <= limit, value.utf8.count <= limit * 4 else { return false }
        return value.unicodeScalars.allSatisfy { scalar in
            switch scalar.properties.generalCategory {
            case .control, .format, .lineSeparator, .paragraphSeparator, .surrogate, .privateUse, .unassigned: return false
            default: return scalar != "\u{2028}" && scalar != "\u{2029}"
            }
        }
    }

    static func validSavedTrip(_ trip: SavedTrip) -> Bool {
        let items = trip.days.flatMap(\.items)
        return validMessageID(trip.id)
            && !trip.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && items.allSatisfy { validMessageID($0.id) }
            && Set(items.map(\.id)).count == items.count
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
            let memory: Memory?
            struct Memory: Decodable { let tags: [LioMemoryWire.Tag] }
            let layout: String?
            let followups: Followups?
            struct Followups: Decodable {
                let version: String
                let actions: [Action]
                struct Action: Decodable {
                    let tool: String
                    let parameters: [String: String]
                    let label: String
                }
            }
            enum CodingKeys: String, CodingKey { case messageID = "message_id", text, answer, status, failure, activity, sources, trip, memory, layout, followups }
            init(from decoder: Decoder) throws {
                let c = try decoder.container(keyedBy: CodingKeys.self)
                messageID = try c.decode(String.self, forKey: .messageID); text = try c.decode(String.self, forKey: .text)
                answer = try c.decode(String.self, forKey: .answer); status = try c.decode(Status.self, forKey: .status)
                failure = try c.decodeIfPresent(Failure.self, forKey: .failure)
                activity = try c.decodeIfPresent(Activity.self, forKey: .activity)
                sources = try c.decode([Citation].self, forKey: .sources)
                trip = try c.decodeIfPresent(SavedTrip.self, forKey: .trip)
                memory = try c.decodeIfPresent(Memory.self, forKey: .memory)
                layout = try c.decodeIfPresent(String.self, forKey: .layout)
                // The buttons are optional garnish: a malformed list reads as none and never fails the page.
                followups = (try? c.decodeIfPresent(Followups.self, forKey: .followups)) ?? nil
            }
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
