import Foundation
import CryptoKit

/// Client fixture for #702. Live transport will use the frozen response envelopes
/// and the existing session boundary when the endpoint is deployed.
enum DemoV2Dialogue {
    enum Failure: Error, Equatable {
        case invalidMessage, mismatchedOriginal, invalidResponse, invalidEvent, invalidSource
    }

    enum Destination {
        case initial
        case conversation(String)
        case newConversation
    }

    struct Message: Encodable {
        let version = "DEMO-dialogue-message.1"
        let message_id: String
        let text: String
        let locale: String
        let conversation_id: String?
        let new_conversation: Bool?

        init(id: UUID, text: String, language: ShellLanguage, destination: Destination) throws {
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  !text.utf8.contains(0), text.utf8.count <= 12_000 else { throw Failure.invalidMessage }
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

    struct Receipt: Decodable {
        let message_id: String
        let conversation_id: String
        let run_id: String
        let input_sha256: String

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
        }

        struct Status: Decodable {
            enum Stage: String, Decodable {
                case queued, running, tool, completed, failed, cancelled, unknown
                case contextInvalid = "context_invalid"
            }

            let status: String
            let stage: Stage
            let tool_kind: String?
        }

        struct Answer: Decodable { let text: String }

        struct Source: Decodable {
            let source_id: String
            let label: String
            let url: URL?
            let state: String

            var openableURL: URL? {
                guard state != "unknown", let url,
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
            case .needsCard, .tripCandidate, .editCandidate, .memoryCandidate:
                payload = .card(try box.decode(Card.self, forKey: .payload))
            }
        }

        func checkOriginal(_ receipt: Receipt) throws {
            guard !eventID.isEmpty, conversationID == receipt.conversation_id,
                  messageID == receipt.message_id, runID == receipt.run_id
            else { throw Failure.mismatchedOriginal }
        }
    }
}
