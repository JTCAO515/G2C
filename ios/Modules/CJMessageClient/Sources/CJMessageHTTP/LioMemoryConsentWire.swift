import Foundation

/// `LIO-memory-consent.1` (#1970, `contracts/message/LIO-MEMORY-CONSENT-V1.md`): the account's choice whether Lio may
/// offer to remember preferences. The server's record is the only record the server enforces; the App keeps its own
/// copy on the device (`LioConsent`) and writes each choice here.
public enum LioMemoryConsentWire {
    public static let version = "LIO-memory-consent.1"

    public enum State: String, Codable, Sendable { case granted, withdrawn }

    /// One user action, written once with a fixed `request_id`: a retry sends the same bytes.
    public struct Request: Equatable, Sendable {
        public let state: State
        public let textVersion: String
        public let requestID: String

        /// `consent_text_version` and `request_id`: 1–64 and 1–128 of `A-Za-z0-9._:-`.
        public init?(state: State, textVersion: String, requestID: String) {
            guard Self.valid(textVersion, limit: 64), Self.valid(requestID, limit: 128) else { return nil }
            self.state = state
            self.textVersion = textVersion
            self.requestID = requestID
        }

        var originalUTF8: Data {
            get throws {
                // Sorted keys: the same action is the same bytes every time, so a retry cannot look like a different request.
                let encoder = JSONEncoder()
                encoder.outputFormatting = [.sortedKeys]
                return try encoder.encode(Body(version: LioMemoryConsentWire.version, state: state,
                                              textVersion: textVersion, requestID: requestID))
            }
        }

        private struct Body: Encodable {
            let version: String
            let state: State
            let textVersion: String
            let requestID: String
            enum CodingKeys: String, CodingKey {
                case version, state, textVersion = "consent_text_version", requestID = "request_id"
            }
        }

        static func valid(_ value: String, limit: Int) -> Bool {
            !value.isEmpty && value.utf8.count <= limit && value.utf8.allSatisfy {
                (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0)
                    || $0 == 45 || $0 == 46 || $0 == 58 || $0 == 95
            }
        }
    }

    /// What the server answers to both routes. `recorded` is false for an account that has never chosen.
    public struct Receipt: Equatable, Sendable {
        public let state: State
        public let recorded: Bool
        public init(state: State, recorded: Bool) { self.state = state; self.recorded = recorded }
    }

    static func decodeReceipt(_ data: Data) throws -> Receipt {
        guard data.count <= 65_536 else { throw MessageHTTPFailure.invalidResponse }
        try validateUnambiguousJSON(data)
        let wire = try JSONDecoder().decode(ReceiptWire.self, from: data)
        guard wire.version == version else { throw MessageHTTPFailure.invalidResponse }
        // A PUT answer may leave `recorded` out; a state that was just written is recorded.
        return Receipt(state: wire.state, recorded: wire.recorded ?? true)
    }

    private struct ReceiptWire: Decodable {
        let version: String
        let state: State
        let recorded: Bool?
    }
}

/// Writes and reads the account's memory consent. A refusal that retrying cannot change (400, 401, 403, 409) is told
/// apart from a server that could not answer (anything else, or no answer): the second is retried by the caller.
@MainActor
public final class LioMemoryConsentClient {
    public enum Outcome: Equatable, Sendable {
        case accepted(LioMemoryConsentWire.Receipt)
        case refused(status: Int)
    }

    private let send: @MainActor (LioMemoryConsentWire.Request) async throws -> Outcome
    private let read: @MainActor () async throws -> Outcome

    public convenience init(timeline: LioTimelineHTTP) {
        self.init(send: { try await timeline.submitMemoryConsent($0) }, read: { try await timeline.readMemoryConsent() })
    }

    /// The seam tests (and previews) use to stand in for the network.
    public init(send: @escaping @MainActor (LioMemoryConsentWire.Request) async throws -> Outcome,
                read: @escaping @MainActor () async throws -> Outcome) {
        self.send = send
        self.read = read
    }

    public func put(_ request: LioMemoryConsentWire.Request) async throws -> Outcome { try await send(request) }

    public func current() async throws -> Outcome { try await read() }
}
