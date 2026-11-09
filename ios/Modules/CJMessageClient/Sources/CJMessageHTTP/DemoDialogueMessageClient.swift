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
        guard try unresolvedMessages(lease: lease).isEmpty else { throw RecoveryError.queryOnly }
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
                  envelope["version"] as? String == "DEMO-dialogue-message.1" else { return false }
            _ = try DemoDialogueRoute.validateOriginal(record.originalUTF8)
            return true
        }
    }

    public func originalText(messageID: String, lease: Lease) throws -> String {
        try recovery.validateScope(scope, lease: lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.queryOnly }
        let original = try DemoDialogueRoute.validateOriginal(record.originalUTF8)
        guard Data(original.messageID.utf8) == Data(messageID.utf8) else { throw RecoveryError.receiptMismatch }
        return original.text
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
            var parts = URLComponents()
            parts.path = DemoDialogueRoute.path
            if !submitting {
                parts.queryItems = [URLQueryItem(name: "message_id", value: original.messageID)]
                parts.percentEncodedQuery = parts.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B")
            }
            guard let path = parts.string else { throw MessageHTTPFailure.invalidConfiguration }
            var request = HTTPRequest(method: submitting ? .post : .get, scheme: nil, authority: nil, path: path)
            request.headerFields[.authorization] = "Bearer " + bearer
            request.headerFields[.accept] = "application/json"
            if submitting { request.headerFields[.contentType] = "application/octet-stream" }
            try recovery.validateScope(scope, lease: lease)
            try Task.checkCancellation()
            let (response, body) = try await transport.send(
                request, body: submitting ? HTTPBody(bytes) : nil, baseURL: endpoint.url,
                operationID: submitting ? DemoDialogueRoute.submit : DemoDialogueRoute.original)
            try recovery.validateScope(scope, lease: lease)
            try Task.checkCancellation()
            guard let body else { throw MessageHTTPFailure.invalidResponse }
            let data = try await Data(collecting: body, upTo: min(endpoint.maximumResponseBytes, 65_536))
            try recovery.validateScope(scope, lease: lease)
            try Task.checkCancellation()
            try verifyResponse(data, response: response)
            return try settle(operation, original: original, bytes: bytes, status: response.status.code,
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
