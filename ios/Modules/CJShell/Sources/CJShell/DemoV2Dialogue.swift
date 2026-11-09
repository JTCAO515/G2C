import Foundation
import CryptoKit
import CJAPI

/// Client fixture for #702. Live transport will use the frozen response envelopes
/// and the existing session boundary when the endpoint is deployed.
enum DemoV2Dialogue {
    enum Failure: Error, Equatable {
        case invalidMessage, mismatchedOriginal, invalidResponse, invalidEvent, invalidSource, invalidAction
    }

    enum Destination {
        case initial
        case conversation(String)
        case newConversation
    }

    enum MessageVersion: String {
        case ordinary = "DEMO-dialogue-message.1"
        case planning = "DEMO-dialogue-message.2"
    }

    struct Message: Encodable {
        let version: String
        let message_id: String
        let text: String
        let locale: String
        let conversation_id: String?
        let new_conversation: Bool?

        init(id: UUID, text: String, language: ShellLanguage, destination: Destination,
             version: MessageVersion = .ordinary) throws {
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  !text.utf8.contains(0), text.utf8.count <= 12_000 else { throw Failure.invalidMessage }
            self.version = version.rawValue
            self.message_id = id.uuidString.lowercased()
            self.text = text
            self.locale = language == .chinese ? "zh" : "en"
            switch destination {
            case .initial:
                conversation_id = nil
                new_conversation = nil
            case .conversation(let id):
                guard validConversation(id) else { throw Failure.invalidMessage }
                conversation_id = id
                new_conversation = nil
            case .newConversation:
                conversation_id = nil
                new_conversation = true
            }
        }

        func encoded() throws -> Data {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            let bytes = try encoder.encode(self)
            guard bytes.count <= 16_384 else { throw Failure.invalidMessage }
            return bytes
        }
    }

    enum Route {
        case submitMessage, originalMessage(String), events(String), submitAction, originalAction(String)

        func url(origin: URL) -> URL {
            var components = URLComponents(url: origin, resolvingAgainstBaseURL: false)!
            switch self {
            case .submitMessage:
                components.path = "/v1/demo-dialogue/messages"
            case .originalMessage(let id):
                components.path = "/v1/demo-dialogue/messages"
                components.queryItems = [URLQueryItem(name: "message_id", value: id)]
            case .events(let id):
                components.path = "/v1/demo-dialogue/events"
                components.queryItems = [URLQueryItem(name: "message_id", value: id)]
            case .submitAction:
                components.path = "/v1/demo-dialogue/actions"
            case .originalAction(let id):
                components.path = "/v1/demo-dialogue/actions"
                components.queryItems = [URLQueryItem(name: "action_id", value: id)]
            }
            components.percentEncodedQuery = components.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
            return components.url!
        }
    }

    struct OriginalMessage {
        let command: Message
        let bytes: Data
        let sha256: String

        init(_ command: Message) throws {
            self.command = command
            let bytes = try command.encoded()
            self.bytes = bytes
            self.sha256 = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        }

        func submission(to origin: URL) -> URLRequest {
            var request = URLRequest(url: Route.submitMessage.url(origin: origin))
            request.httpMethod = "POST"
            request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = bytes
            return request
        }

        func reconciliation(at origin: URL) -> URLRequest {
            var request = URLRequest(url: Route.originalMessage(command.message_id).url(origin: origin))
            request.httpMethod = "GET"
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            return request
        }
    }

    struct EventBinding: Sendable {
        let messageID: String
        let conversationID: String
        let runID: String

        fileprivate init(messageID: String, conversationID: String, runID: String) {
            self.messageID = messageID
            self.conversationID = conversationID
            self.runID = runID
        }
    }

    struct Receipt: Decodable {
        let message_id: String
        let conversation_id: String
        let run_id: String
        let input_sha256: String

        var eventBinding: EventBinding {
            .init(messageID: message_id, conversationID: conversation_id, runID: run_id)
        }

        func checkOriginal(_ original: OriginalMessage) throws {
            let message = original.command
            guard message_id == message.message_id,
                  message.conversation_id.map({ $0 == conversation_id }) ?? true,
                  validConversation(conversation_id), !run_id.isEmpty,
                  input_sha256 == original.sha256
            else { throw Failure.mismatchedOriginal }
        }
    }

    enum MessageResult {
        case accepted(Receipt)
        case notObserved
        case dailyLimit
        case accessDenied
        case unknown
        case rejected
    }

    enum MessageOperation { case submit, reconcile }

    /// Pinned to B's #708 DEMO-dialogue-message.1 candidate. A null GET does not
    /// imply failed submission and never gives the caller a new write permit.
    static func response(_ data: Data, status: Int, contentType: String?, original: OriginalMessage,
                         operation: MessageOperation) throws -> MessageResult {
        guard data.count <= 65_536,
              contentType?.split(separator: ";").first?.lowercased() == "application/json" else {
            throw Failure.invalidResponse
        }
        let decoder = JSONDecoder()
        if status == 200 {
            let envelope = try decoder.decode(ReceiptEnvelope.self, from: data)
            guard envelope.version == "DEMO-dialogue-receipt.1", !envelope.request_id.isEmpty else {
                throw Failure.invalidResponse
            }
            if let receipt = envelope.receipt {
                try receipt.checkOriginal(original)
                return .accepted(receipt)
            }
            guard operation == .reconcile else { throw Failure.invalidResponse }
            return .notObserved
        }
        let envelope = try decoder.decode(ErrorEnvelope.self, from: data)
        guard !envelope.request_id.isEmpty else { throw Failure.invalidResponse }
        switch (status, envelope.error.code, envelope.error.outcome, envelope.error.recovery) {
        case (429, "DEMO_DAILY_LIMIT", "failed", "do_not_retry"): return .dailyLimit
        case (401, "ACCESS_DENIED", "failed", "do_not_retry"),
             (403, "ACCESS_DENIED", "failed", "do_not_retry"): return .accessDenied
        case (_, _, "unknown", _), (_, _, _, "reconcile_original"): return .unknown
        case (_, _, "failed", "do_not_retry"): return .rejected
        default: throw Failure.invalidResponse
        }
    }

    private struct ReceiptEnvelope: Decodable {
        let version: String
        let request_id: String
        let receipt: Receipt?

        private enum CodingKeys: String, CodingKey { case version, request_id, receipt }

        init(from decoder: any Decoder) throws {
            let box = try decoder.container(keyedBy: CodingKeys.self)
            version = try box.decode(String.self, forKey: .version)
            request_id = try box.decode(String.self, forKey: .request_id)
            guard box.contains(.receipt) else { throw Failure.invalidResponse }
            receipt = try box.decodeIfPresent(Receipt.self, forKey: .receipt)
        }
    }

    private struct ErrorEnvelope: Decodable {
        struct Detail: Decodable {
            let code: String
            let outcome: String
            let recovery: String
        }
        let request_id: String
        let error: Detail
    }

    private static func validConversation(_ id: String) -> Bool {
        let prefix = "demo-dialogue-"
        let suffix = id.dropFirst(prefix.count)
        return id.hasPrefix(prefix) && suffix.utf8.count == 32 &&
            suffix.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }

    /// The current fixture covers explicit choices whose payload has been
    /// agreed. The separate correct-needs changes body will follow B's schema.
    struct Action: Encodable {
        enum Operation: String, Codable {
            case confirmNeeds = "confirm_needs"
            case correctNeeds = "correct_needs"
            case acceptTrip = "accept_trip"
            case requestTripChanges = "request_trip_changes"
            case acceptEdit = "accept_edit"
            case remember
            case dismissMemory = "dismiss_memory"

            var requiredCard: Event.Kind {
                switch self {
                case .confirmNeeds, .correctNeeds: .needsCard
                case .acceptTrip, .requestTripChanges: .tripCandidate
                case .acceptEdit: .editCandidate
                case .remember, .dismissMemory: .memoryCandidate
                }
            }
        }

        let version = "DEMO-dialogue-action.1"
        let action_id: String
        let conversation_id: String
        let card_id: String
        let expected_version: Int
        let operation: Operation
        let changes: Components.Schemas.NeedsChanges?

        init(id: UUID, operation: Operation, event: Event, receipt: Receipt,
             changes: Components.Schemas.NeedsChanges? = nil) throws {
            try self.init(id: id, operation: operation, event: event, binding: receipt.eventBinding, changes: changes)
        }

        init(id: UUID, operation: Operation, event: Event, binding: EventBinding,
             changes: Components.Schemas.NeedsChanges? = nil) throws {
            try event.checkBinding(binding)
            guard event.kind == operation.requiredCard, let (cardID, revision) = event.cardReference,
                  !cardID.isEmpty, revision > 0, (operation == .correctNeeds) == (changes != nil) else { throw Failure.invalidAction }
            if let changes {
                let bytes = try JSONEncoder().encode(changes)
                guard let values = try JSONSerialization.jsonObject(with: bytes) as? [String: Any], !values.isEmpty
                else { throw Failure.invalidAction }
            }
            self.action_id = id.uuidString.lowercased()
            self.conversation_id = binding.conversationID
            self.card_id = cardID
            self.expected_version = revision
            self.operation = operation
            self.changes = changes
        }
    }

    struct ActionReceipt: Decodable {
        let action_id: String
        let conversation_id: String
        let card_id: String
        let version: Int
        let operation: Action.Operation
        let input_sha256: String
        let message_id: String?
        let run_id: String?
        let card: Event.Card?

        @discardableResult
        func checkOriginal(_ action: Action, bytes: Data) throws -> EventBinding? {
            let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            guard action_id == action.action_id, conversation_id == action.conversation_id,
                  card_id == action.card_id, operation == action.operation, version >= action.expected_version,
                  input_sha256 == digest, (message_id == nil) == (run_id == nil),
                  message_id.map({ !$0.isEmpty }) ?? true, run_id.map({ !$0.isEmpty }) ?? true,
                  card.map({ $0.card_id == card_id && $0.version == version }) ?? true
            else { throw Failure.mismatchedOriginal }
            switch operation {
            case .confirmNeeds:
                guard message_id != nil else { throw Failure.invalidResponse }
            case .correctNeeds:
                guard message_id == nil else { throw Failure.invalidResponse }
            default:
                break
            }
            guard let message_id, let run_id else { return nil }
            return .init(messageID: message_id, conversationID: conversation_id, runID: run_id)
        }
    }

    struct Event: Decodable {
        enum Kind: String, Decodable {
            case status, source
            case answerDelta = "answer_delta"
            case needsCard = "needs_card"
            case tripCandidate = "trip_candidate"
            case editCandidate = "edit_candidate"
            case memoryCandidate = "memory_candidate"
        }

        let eventID: String
        let kind: Kind
        let payload: Payload
        private let conversationID: String
        private let messageID: String
        private let runID: String

        enum Payload {
            case status(Status)
            case answer(Answer)
            case source(Source)
            case card(Card)
            case needs(NeedsCard)
            case trip(TripCandidate)
            case memory(MemoryCandidate)
        }

        struct Status: Decodable {
            enum Stage: String, Decodable {
                case queued, running, tool, completed, failed, cancelled, unknown
                case contextInvalid = "context_invalid"
            }

            let status: String
            let stage: Stage
            let tool_kind: String?
            let error_code: String?
        }

        struct Answer: Decodable { let text: String }

        struct Source: Decodable {
            let source_id: String
            let label: String
            let url: URL?
            let state: String

            var openableURL: URL? {
                guard state == "verified", let url,
                      url.scheme?.lowercased() == "https", url.host != nil,
                      url.user == nil, url.password == nil else { return nil }
                return url
            }
        }

        // Freeze the full per-kind fields with B before rendering live cards.
        struct Card: Decodable {
            let card_id: String
            let version: Int
            let status: String
        }

        struct NeedsCard: Decodable {
            struct Dates: Decodable {
                let start: String?
                let end: String?
            }

            struct FixedItem: Decodable {
                let item_id: String
                let label: String
                let starts_at: String?
                let ends_at: String?
                let time_zone: String?
            }

            let card_id: String
            let version: Int
            let status: String
            let dates: Dates?
            let city: String?
            let party_size: Int?
            let pace: String?
            let fixed_items: [FixedItem]?
        }

        struct TripCandidate: Decodable {
            struct Day: Decodable {
                struct Item: Decodable {
                    let item_id: String
                    let label: String
                    let place: String?
                    let starts_at: String?
                    let ends_at: String?
                    let time_zone: String?
                    let source_ids: [String]
                    let fixed: Bool?
                }

                let date: String?
                let items: [Item]
            }

            let card_id: String
            let version: Int
            let status: String
            let proposal_id: String
            let trip_id: String?
            let expected_trip_version: Int?
            let candidate_hash: String
            let days: [Day]
        }

        struct MemoryCandidate: Decodable {
            let card_id: String
            let version: Int
            let status: String
            let candidate_id: String
            let kind: String
            let text: String
        }

        private enum CodingKeys: String, CodingKey {
            case version, kind, payload
            case eventID = "event_id"
            case conversationID = "conversation_id"
            case messageID = "message_id"
            case runID = "run_id"
        }

        init(from decoder: any Decoder) throws {
            let box = try decoder.container(keyedBy: CodingKeys.self)
            guard try box.decode(String.self, forKey: .version) == "DEMO-dialogue-event.1" else {
                throw Failure.invalidEvent
            }
            eventID = try box.decode(String.self, forKey: .eventID)
            conversationID = try box.decode(String.self, forKey: .conversationID)
            messageID = try box.decode(String.self, forKey: .messageID)
            runID = try box.decode(String.self, forKey: .runID)
            kind = try box.decode(Kind.self, forKey: .kind)
            switch kind {
            case .status: payload = .status(try box.decode(Status.self, forKey: .payload))
            case .answerDelta: payload = .answer(try box.decode(Answer.self, forKey: .payload))
            case .source:
                let source = try box.decode(Source.self, forKey: .payload)
                guard source.state != "unknown" || source.url == nil else { throw Failure.invalidSource }
                payload = .source(source)
            case .tripCandidate:
                payload = .trip(try box.decode(TripCandidate.self, forKey: .payload))
            case .memoryCandidate:
                payload = .memory(try box.decode(MemoryCandidate.self, forKey: .payload))
            case .needsCard:
                payload = .needs(try box.decode(NeedsCard.self, forKey: .payload))
            case .editCandidate:
                payload = .card(try box.decode(Card.self, forKey: .payload))
            }
        }

        var cardReference: (String, Int)? {
            switch payload {
            case .card(let value): (value.card_id, value.version)
            case .needs(let value): (value.card_id, value.version)
            case .trip(let value): (value.card_id, value.version)
            case .memory(let value): (value.card_id, value.version)
            case .status, .answer, .source: nil
            }
        }

        func checkOriginal(_ receipt: Receipt) throws {
            try checkBinding(receipt.eventBinding)
        }

        func checkBinding(_ binding: EventBinding) throws {
            guard !eventID.isEmpty, conversationID == binding.conversationID,
                  messageID == binding.messageID, runID == binding.runID
            else { throw Failure.mismatchedOriginal }
        }
    }
}
