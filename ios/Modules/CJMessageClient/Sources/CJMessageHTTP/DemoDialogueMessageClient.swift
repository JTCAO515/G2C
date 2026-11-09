import CryptoKit
import Foundation
import CJMessageClient
import HTTPTypes
import OpenAPIRuntime

public struct DemoDialogueMessageReceipt: Decodable, Sendable {
    public let messageID: String
    public let conversationID: String
    public let runID: String
    public let inputSHA256: String

    private enum CodingKeys: String, CodingKey {
        case messageID = "message_id"
        case conversationID = "conversation_id"
        case runID = "run_id"
        case inputSHA256 = "input_sha256"
    }
}

public enum DemoDialogueMessageOutcome: Sendable {
    case accepted(DemoDialogueMessageReceipt)
    case notObserved
    case unknown
    case rejected(status: Int, code: String)
}

public struct DemoDialogueNeedsActionReceipt: Decodable, Sendable {
    public let actionID: String
    public let conversationID: String
    public let cardID: String
    public let version: Int64
    public let operation: String
    public let inputSHA256: String
    public let messageID: String?
    public let runID: String?

    private enum CodingKeys: String, CodingKey {
        case actionID = "action_id"
        case conversationID = "conversation_id"
        case cardID = "card_id"
        case version, operation
        case inputSHA256 = "input_sha256"
        case messageID = "message_id"
        case runID = "run_id"
    }
}

public enum DemoDialogueNeedsActionOutcome: Sendable {
    case accepted(DemoDialogueNeedsActionReceipt, originalResponse: Data)
    case notObserved
    case unknown
    case rejected(status: Int, code: String)
}

/// Uses the existing encrypted recovery journal and credential lease. The
/// transport still requires the distinct signed Beta capability for a write.
@MainActor public final class DemoDialogueMessageClient {
    private let recovery: MessageRecovery
    private let scope: StorageScope
    private let endpoint: MessageEndpoint
    private let credentials: any MessageCredentialsProvider
    private let transport: NoRedirectTransport

    public convenience init(recovery: MessageRecovery, scope: StorageScope, endpoint: MessageEndpoint,
                            credentials: any MessageCredentialsProvider,
                            validateSession: @escaping @MainActor @Sendable () throws -> Void) throws {
        let transport = try NoRedirectTransport.demoDialogueMessages(
            endpoint: endpoint, requestTimeout: 10, resourceTimeout: 30, validate: validateSession)
        self.init(recovery: recovery, scope: scope, endpoint: endpoint, credentials: credentials, transport: transport)
    }

    /// Test-only composition; the supplied transport uses a local interceptor.
    init(recovery: MessageRecovery, scope: StorageScope, endpoint: MessageEndpoint,
         credentials: any MessageCredentialsProvider, transport: NoRedirectTransport) {
        self.recovery = recovery
        self.scope = scope
        self.endpoint = endpoint
        self.credentials = credentials
        self.transport = transport
    }

    /// Send only after the user initiates a fresh action. No replay API is exposed.
    public func submit(originalUTF8: Data, lease: Lease) async throws -> DemoDialogueMessageOutcome {
        let original = try DemoDialogueRoute.validateOriginal(originalUTF8)
        let token = try await bearer(lease)
        guard try unresolvedMessages(lease: lease).isEmpty, try unresolvedNeedsActions(lease: lease).isEmpty
        else { throw RecoveryError.queryOnly }
        try recovery.stage(messageID: original.messageID, originalUTF8: originalUTF8, lease: lease)
        let submission = try recovery.beginSubmission(messageID: original.messageID, lease: lease)
        return try await perform(submission.operation, original: original, bytes: submission.originalUTF8,
                                 lease: lease, bearer: token, submitting: true)
    }

    public func reconcile(messageID: String, lease: Lease) async throws -> DemoDialogueMessageOutcome {
        let token = try await bearer(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.queryOnly }
        let original = try DemoDialogueRoute.validateOriginal(record.originalUTF8)
        guard Data(original.messageID.utf8) == Data(record.messageID.utf8) else { throw RecoveryError.receiptMismatch }
        let operation = try recovery.beginQuery(messageID: messageID, lease: lease)
        return try await perform(operation, original: original, bytes: record.originalUTF8,
                                 lease: lease, bearer: token, submitting: false)
    }

    public func unresolvedMessages(lease: Lease) throws -> [LocalActionReference] {
        let projection = try recovery.localProjection(scope: scope, lease: lease)
        return try projection.actions.filter { action in
            guard [.staged, .queryRequired, .notObserved].contains(action.phase),
                  let record = try recovery.action(messageID: action.messageID, lease: lease),
                  let envelope = try? JSONSerialization.jsonObject(with: record.originalUTF8) as? [String: Any],
                  let version = envelope["version"] as? String,
                  ["DEMO-dialogue-message.1", "DEMO-dialogue-message.2"].contains(version) else { return false }
            _ = try DemoDialogueRoute.validateOriginal(record.originalUTF8)
            return true
        }
    }

    private func bearer(_ lease: Lease) async throws -> String {
        try recovery.validateScope(scope, lease: lease)
        let bearer = try await credentials.bearer(for: scope, lease: lease)
        try recovery.validateScope(scope, lease: lease)
        try Task.checkCancellation()
        guard let bearer else { throw MessageHTTPFailure.credentialsUnavailable }
        return bearer
    }

    private func perform(_ operation: CJMessageClient.Operation, original: DemoDialogueRoute.Original, bytes: Data,
                         lease: Lease, bearer: String, submitting: Bool) async throws -> DemoDialogueMessageOutcome {
        do {
            let (status, data) = try await exchange(
                path: DemoDialogueRoute.path, query: submitting ? nil : URLQueryItem(name: "message_id", value: original.messageID),
                operationID: submitting ? DemoDialogueRoute.submit : DemoDialogueRoute.original,
                payload: submitting ? bytes : nil, lease: lease, bearer: bearer)
            return try settle(operation, original: original, bytes: bytes, status: status,
                              response: data, submitting: submitting)
        } catch {
            // Only this still-current operation may update the encrypted journal.
            // The initial beginSubmission already persisted uncertainty.
            try recovery.validateScope(scope, lease: lease)
            if case .staleOperation? = error as? RecoveryError { throw error }
            try? recovery.observeUnknown(operation)
            if error is CancellationError { throw error }
            return .unknown
        }
    }

    private func exchange(path: String, query: URLQueryItem?, operationID: String,
                          payload: Data?, lease: Lease, bearer: String) async throws -> (Int, Data) {
        var parts = URLComponents()
        parts.path = path
        if let query {
            parts.queryItems = [query]
            parts.percentEncodedQuery = parts.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
        }
        guard let path = parts.string else { throw MessageHTTPFailure.invalidConfiguration }
        var request = HTTPRequest(method: payload == nil ? .get : .post, scheme: nil, authority: nil, path: path)
        request.headerFields[.authorization] = "Bearer " + bearer
        request.headerFields[.accept] = "application/json"
        if payload != nil { request.headerFields[.contentType] = "application/octet-stream" }
        try recovery.validateScope(scope, lease: lease)
        try Task.checkCancellation()
        let (response, body) = try await transport.send(
            request, body: payload.map { HTTPBody($0) }, baseURL: endpoint.url, operationID: operationID)
        try recovery.validateScope(scope, lease: lease)
        try Task.checkCancellation()
        guard let body else { throw MessageHTTPFailure.invalidResponse }
        let data = try await Data(collecting: body, upTo: min(endpoint.maximumResponseBytes, 65_536))
        try recovery.validateScope(scope, lease: lease)
        try Task.checkCancellation()
        try verifyResponse(data, response: response)
        return (response.status.code, data)
    }

    private func verifyResponse(_ data: Data, response: HTTPResponse) throws {
        let trace = response.headerFields.filter { $0.name.canonicalName == "x-request-id" }
        let media = response.headerFields.filter { $0.name == .contentType }
        guard trace.count == 1, let requestID = trace.first?.value, UUID(uuidString: requestID) != nil,
              media.count == 1, media.first?.value.split(separator: ";").first?.lowercased() == "application/json" else {
            throw MessageHTTPFailure.invalidResponse
        }
        try validateUnambiguousJSON(data)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              root["request_id"] as? String == requestID else { throw MessageHTTPFailure.invalidResponse }
    }

    private func settle(_ operation: CJMessageClient.Operation, original: DemoDialogueRoute.Original, bytes: Data,
                        status: Int, response: Data, submitting: Bool) throws -> DemoDialogueMessageOutcome {
        if status == 200 {
            let envelope = try JSONDecoder().decode(ReceiptEnvelope.self, from: response)
            guard envelope.version == "DEMO-dialogue-receipt.1" else { throw MessageHTTPFailure.invalidResponse }
            guard let receipt = envelope.receipt else {
                guard !submitting else { throw MessageHTTPFailure.invalidResponse }
                try recovery.observeNotObserved(operation)
                return .notObserved
            }
            let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            guard Data(receipt.messageID.utf8) == Data(original.messageID.utf8),
                  original.conversationID.map({ Data($0.utf8) == Data(receipt.conversationID.utf8) }) ?? true,
                  DemoDialogueRoute.validConversationID(receipt.conversationID), !receipt.runID.isEmpty,
                  receipt.inputSHA256 == digest else { throw RecoveryError.receiptMismatch }
            try recovery.observeReceipt(operation, messageID: receipt.messageID, inputSHA256: digest, receipt: response)
            return .accepted(receipt)
        }
        let error = try JSONDecoder().decode(ErrorEnvelope.self, from: response).error
        if submitting, (400...599).contains(status), error.outcome == "failed", error.recovery == "do_not_retry" {
            if error.code == "INPUT_CONFLICT" {
                try recovery.observeSubmissionInputConflict(operation)
            } else {
                try recovery.observeSubmissionRejection(operation, httpStatus: status, responseUTF8: response)
            }
            return .rejected(status: status, code: error.code)
        }
        try recovery.observeUnknown(operation)
        return .unknown
    }

    private struct ReceiptEnvelope: Decodable {
        let version: String
        let receipt: DemoDialogueMessageReceipt?

        private enum CodingKeys: String, CodingKey { case version, receipt }

        init(from decoder: any Decoder) throws {
            let box = try decoder.container(keyedBy: CodingKeys.self)
            version = try box.decode(String.self, forKey: .version)
            guard box.contains(.receipt) else { throw MessageHTTPFailure.invalidResponse }
            receipt = try box.decodeIfPresent(DemoDialogueMessageReceipt.self, forKey: .receipt)
        }
    }

    private struct ErrorEnvelope: Decodable {
        struct Detail: Decodable {
            let code: String
            let outcome: String
            let recovery: String
        }
        let error: Detail
    }
}


extension DemoDialogueMessageClient {
    private static let actionPrefix = "demo-needs-action."

    public func submitNeedsAction(originalUTF8: Data, lease: Lease) async throws -> DemoDialogueNeedsActionOutcome {
        let original = try DemoDialogueRoute.validateNeedsAction(originalUTF8)
        let token = try await bearer(lease)
        guard try unresolvedMessages(lease: lease).isEmpty, try unresolvedNeedsActions(lease: lease).isEmpty
        else { throw RecoveryError.queryOnly }
        let journalID = Self.actionPrefix + original.actionID
        try recovery.stage(messageID: journalID, originalUTF8: originalUTF8, lease: lease)
        let submission = try recovery.beginSubmission(messageID: journalID, lease: lease)
        return try await performNeedsAction(submission.operation, original: original, bytes: submission.originalUTF8,
                                            lease: lease, bearer: token, submitting: true)
    }

    public func reconcileNeedsAction(actionID: String, lease: Lease) async throws -> DemoDialogueNeedsActionOutcome {
        let token = try await bearer(lease)
        let journalID = Self.actionPrefix + actionID
        guard let record = try recovery.action(messageID: journalID, lease: lease) else { throw RecoveryError.queryOnly }
        let original = try DemoDialogueRoute.validateNeedsAction(record.originalUTF8)
        guard Data(original.actionID.utf8) == Data(actionID.utf8) else { throw RecoveryError.receiptMismatch }
        let operation = try recovery.beginQuery(messageID: journalID, lease: lease)
        return try await performNeedsAction(operation, original: original, bytes: record.originalUTF8,
                                            lease: lease, bearer: token, submitting: false)
    }

    public func unresolvedNeedsActions(lease: Lease) throws -> [String] {
        let projection = try recovery.localProjection(scope: scope, lease: lease)
        return try projection.actions.compactMap { action in
            guard action.messageID.hasPrefix(Self.actionPrefix),
                  [.staged, .queryRequired, .notObserved].contains(action.phase),
                  let record = try recovery.action(messageID: action.messageID, lease: lease) else { return nil }
            let original = try DemoDialogueRoute.validateNeedsAction(record.originalUTF8)
            guard Data(action.messageID.utf8) == Data((Self.actionPrefix + original.actionID).utf8)
            else { throw RecoveryError.receiptMismatch }
            return original.actionID
        }
    }

    private func performNeedsAction(_ operation: CJMessageClient.Operation, original: DemoDialogueRoute.NeedsActionOriginal,
                                    bytes: Data, lease: Lease, bearer: String, submitting: Bool) async throws -> DemoDialogueNeedsActionOutcome {
        do {
            let (status, data) = try await exchange(
                path: DemoDialogueRoute.actionsPath, query: submitting ? nil : URLQueryItem(name: "action_id", value: original.actionID),
                operationID: submitting ? DemoDialogueRoute.submitAction : DemoDialogueRoute.originalAction,
                payload: submitting ? bytes : nil, lease: lease, bearer: bearer)
            return try settleNeedsAction(operation, original: original, bytes: bytes, status: status,
                                         response: data, submitting: submitting)
        } catch {
            try recovery.validateScope(scope, lease: lease)
            if case .staleOperation? = error as? RecoveryError { throw error }
            try? recovery.observeUnknown(operation)
            if error is CancellationError { throw error }
            return .unknown
        }
    }

    private func settleNeedsAction(_ operation: CJMessageClient.Operation, original: DemoDialogueRoute.NeedsActionOriginal,
                                   bytes: Data, status: Int, response: Data, submitting: Bool) throws -> DemoDialogueNeedsActionOutcome {
        if status == 200 {
            let envelope = try JSONDecoder().decode(NeedsActionEnvelope.self, from: response)
            guard envelope.version == "DEMO-dialogue-action-receipt.1" else { throw MessageHTTPFailure.invalidResponse }
            guard let receipt = envelope.receipt else {
                guard !submitting else { throw MessageHTTPFailure.invalidResponse }
                try recovery.observeNotObserved(operation)
                return .notObserved
            }
            let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
            guard Data(receipt.actionID.utf8) == Data(original.actionID.utf8),
                  Data(receipt.conversationID.utf8) == Data(original.conversationID.utf8),
                  Data(receipt.cardID.utf8) == Data(original.cardID.utf8),
                  receipt.version >= original.expectedVersion, receipt.operation == original.operation,
                  receipt.inputSHA256 == digest else { throw RecoveryError.receiptMismatch }
            if original.operation == "confirm_needs" {
                guard let message = receipt.messageID, !message.isEmpty,
                      let run = receipt.runID, !run.isEmpty else { throw MessageHTTPFailure.invalidResponse }
            } else {
                guard receipt.messageID == nil, receipt.runID == nil else { throw MessageHTTPFailure.invalidResponse }
            }
            try recovery.observeReceipt(operation, messageID: Self.actionPrefix + receipt.actionID,
                                         inputSHA256: digest, receipt: response)
            return .accepted(receipt, originalResponse: response)
        }
        let error = try JSONDecoder().decode(ErrorEnvelope.self, from: response).error
        if submitting, (400...599).contains(status), error.outcome == "failed", error.recovery == "do_not_retry" {
            if error.code == "INPUT_CONFLICT" { try recovery.observeSubmissionInputConflict(operation) }
            else { try recovery.observeSubmissionRejection(operation, httpStatus: status, responseUTF8: response) }
            return .rejected(status: status, code: error.code)
        }
        try recovery.observeUnknown(operation)
        return .unknown
    }

    private struct NeedsActionEnvelope: Decodable {
        let version: String
        let receipt: DemoDialogueNeedsActionReceipt?

        private enum CodingKeys: String, CodingKey { case version, receipt }

        init(from decoder: any Decoder) throws {
            let box = try decoder.container(keyedBy: CodingKeys.self)
            version = try box.decode(String.self, forKey: .version)
            guard box.contains(.receipt) else { throw MessageHTTPFailure.invalidResponse }
            receipt = try box.decodeIfPresent(DemoDialogueNeedsActionReceipt.self, forKey: .receipt)
        }
    }
}
