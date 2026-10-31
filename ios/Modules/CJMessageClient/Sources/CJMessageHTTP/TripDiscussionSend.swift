import Foundation
import CJAPI
import CJMessageClient
import OpenAPIRuntime
import HTTPTypes

/// Validated original association data, never a server execution permit.
public struct TripDiscussionMessage: Sendable {
    public let receipt: Components.Schemas.MessageReceipt
    public let reference: MessageTripReference
}

extension MessageHTTPClient {
    private func checkDiscussionLease(_ lease: Lease) throws {
        try checkSendLease(lease)
        if tripDiscussionPermitState.lease != lease { tripDiscussionPermitState = SendPermitState(lease: lease);tripDiscussionSources=[:] }
    }
    private func requireDiscussionCapability() throws {
        if let liveMessageTransport { try liveMessageTransport.validateTripDiscussionSending(to: endpoint) }
        else if !submissionEnabledForTest { throw MessageHTTPFailure.productionActivationUnavailable }
    }
    func discussionExchange(path: String, operation: String, raw: Data?, lease: Lease) async throws -> (Int, Data, String) {
        let transport = try await checkedTransport(lease)
        var headers = HTTPFields()
        headers[.accept] = "application/json"
        if raw != nil { headers[.contentType] = "application/octet-stream" }
        let request = HTTPRequest(method: raw == nil ? .get : .post, scheme: nil, authority: nil, path: path, headerFields: headers)
        let response: HTTPResponse, body: HTTPBody?
        do { (response, body) = try await transport.send(request, body: raw.map(HTTPBody.init), baseURL: endpoint.url, operationID: operation) }
        catch { try checkDiscussionLease(lease); throw MessageHTTPFailure.exchangeUnknown }
        try checkDiscussionLease(lease)
        let media = response.headerFields.filter { $0.name == .contentType }
        let controls = response.headerFields.filter { $0.name == .cacheControl }
        guard media.count == 1, let mime = media.first?.value.lowercased(),
              mime == "application/json" || mime == "application/json; charset=utf-8",
              controls.count == 1, controls[0].value.lowercased() == "no-store",
              let body, let trace = response.headerFields[.init("x-request-id")!] else { throw MessageHTTPFailure.invalidResponse }
        let bytes = try await Data(collecting: body, upTo: endpoint.maximumResponseBytes)
        try checkDiscussionLease(lease)
        return (response.status.code, bytes, trace)
    }
    private func discussionStatusPath(conversation: String, message: String?) throws -> String {
        guard !conversation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              conversation.utf8.count <= 256, !conversation.utf8.contains(0) else { throw RecoveryError.invalidInput }
        var parts = URLComponents(); parts.path = "/v3/message-send-status"
        parts.queryItems = [.init(name: "conversation_id", value: conversation)]
        if let message { parts.queryItems!.append(.init(name: "message_id", value: message)) }
        guard let value = parts.string else { throw RecoveryError.invalidInput }
        return value
    }
    /// A fresh head from this client's current signed status read, never a caller
    /// DTO or a restored head. Reading it does not upgrade a MEMORY scope.
    public func readTripDiscussionHead(conversationID: String, lease: Lease) async throws -> Components.Schemas.MessageHead? {
        try checkDiscussionLease(lease)
        let key = Data(conversationID.utf8), request = UUID()
        tripDiscussionPermitState.reads[key] = request
        tripDiscussionPermitState.heads.removeValue(forKey: key)
        let (status, bytes, trace) = try await discussionExchange(path: discussionStatusPath(conversation: conversationID, message: nil), operation: "readTripDiscussionStatusV3", raw: nil, lease: lease)
        guard tripDiscussionPermitState.reads[key] == request else { throw RecoveryError.staleOperation }
        guard status == 200 else {
            throw MessageReadFailure.rejected(status: status, error: try JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: bytes))
        }
        let result = try TripDiscussionStatus(raw: bytes, maximumBytes: endpoint.maximumResponseBytes, requestID: trace, conversationID: conversationID, original: nil)
        if let head = result.head { tripDiscussionPermitState.heads[key] = head }
        return result.head
    }
    private func readyDiscussionHead(conversationID: String, lease: Lease) throws -> Components.Schemas.MessageHead? {
        try checkDiscussionLease(lease)
        let conversation = Data(conversationID.utf8)
        guard let head = tripDiscussionPermitState.heads[conversation], head.last_sequence < Int64.max else { return nil }
        let projection = try recovery.localProjection(scope: scope, lease: lease)
        for reference in projection.actions where reference.phase != .accepted {
            guard let record = try recovery.action(messageID: reference.messageID, lease: lease) else { throw RecoveryError.staleOperation }
            let json = try DiscussionJSON(record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes)
            let id = try DiscussionJSON.text(json.object["conversation_id"])
            guard Data(id.utf8) == conversation else { continue }
            guard reference.phase == .notAccepted else { return nil }
            let expected: Components.Schemas.MessageHead
            switch json.object["version"] as? String {
            case "MESSAGE-send.3": expected = try OriginalTripDiscussion(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes).head
            case "MESSAGE-send.2": expected = try OriginalTravelMessageSend(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes).head
            case "MESSAGE-send.1": expected = try OriginalMessageSend(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes).head
            default: throw RecoveryError.invalidSnapshot
            }
            if DiscussionJSON.same(expected.generation, head.generation), head.last_sequence > expected.last_sequence,
               !tripDiscussionPermitState.refreshedDecisions.contains(Data(record.messageID.utf8)) {
                guard let history = sendPermitState.historyHeads[conversation], DiscussionJSON.same(history.generation, head.generation), history.last_sequence >= head.last_sequence else { return nil }
                tripDiscussionPermitState.refreshedDecisions.insert(Data(record.messageID.utf8))
            }
        }
        try checkDiscussionLease(lease)
        return head
    }
    public func canStartTripDiscussion(conversationID: String, lease: Lease) throws -> Bool {
        try requireDiscussionCapability()
        return try readyDiscussionHead(conversationID: conversationID, lease: lease) != nil
    }
    /// Selection is data only. The App must capture its accepted Trip read and
    /// choice before invoking this seam; B checks owner/version/day/item again.
    @discardableResult public func stageTripDiscussion(messageID: String, conversationID: String, text: String,
        trip: MessageTripSelection?, content:MessageTripContent?=nil,lease: Lease) throws -> ActionRecord {
        try requireDiscussionCapability(); try checkDiscussionLease(lease)
        guard (trip == nil)==(content == nil) else { throw RecoveryError.invalidInput }
        guard let head = try readyDiscussionHead(conversationID: conversationID, lease: lease),
              try recovery.action(messageID: messageID, lease: lease) == nil else { throw RecoveryError.queryOnly }
        let raw = try JSONSerialization.data(withJSONObject: ["version": "MESSAGE-send.3", "message_id": messageID, "conversation_id": conversationID, "text": text, "trip_id": NSNull(), "creation_intent": "none", "expected_generation": head.generation, "expected_sequence": head.last_sequence, "travel_context": NSNull(), "needs_reference": NSNull(), "trip_context": trip.map { $0.object as Any } ?? NSNull()], options: [.sortedKeys])
        _ = try OriginalTripDiscussion(raw: raw, maximumBytes: endpoint.maximumRequestBytes, expectedMessageID: messageID)
        tripDiscussionPermitState.heads.removeValue(forKey: Data(conversationID.utf8))
        try recovery.stage(messageID: messageID, originalUTF8: raw, lease: lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.staleOperation }
        tripDiscussionPermitState.prepared[Data(messageID.utf8)] = PreparedMessageSend(digest: record.inputSHA256, head: head)
        if let content { tripDiscussionSources[Data(messageID.utf8)]=content }
        return record
    }
    public func submitPreparedTripDiscussion(messageID: String, lease: Lease, confirmRestored: Bool = false) async throws -> MessageHTTPOutcome {
        try requireDiscussionCapability(); try checkDiscussionLease(lease)
        let key = Data(messageID.utf8)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.queryOnly }
        let original = try OriginalTripDiscussion(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes, expectedMessageID: messageID)
        if tripDiscussionPermitState.decisions[key] == .resubmitOriginal {
            guard tripDiscussionPermitState.intents.contains(key) || confirmRestored else { throw RecoveryError.queryOnly }
            tripDiscussionPermitState.decisions.removeValue(forKey: key)
            try recovery.authorizeOriginalResubmission(messageID: messageID, lease: lease)
            tripDiscussionPermitState.prepared[key] = PreparedMessageSend(digest: record.inputSHA256, head: original.head)
        }
        guard let permit = tripDiscussionPermitState.prepared[key], permit.digest == record.inputSHA256 else { throw RecoveryError.queryOnly }
        tripDiscussionPermitState.prepared.removeValue(forKey: key); tripDiscussionPermitState.intents.insert(key)
        let submission = try recovery.beginSubmission(messageID: messageID, lease: lease)
        do {
            let (status, bytes, trace) = try await discussionExchange(path: "/v3/messages", operation: "receiveTripDiscussionV3", raw: submission.originalUTF8, lease: lease)
            if status == 200 {
                let result = try TripDiscussionAcceptance(raw: bytes, maximumBytes: endpoint.maximumResponseBytes, requestID: trace, original: original)
                try tripDiscussionSources[key]?.validate(result.reference)
                try recovery.observeReceipt(submission.operation, messageID: result.receipt.message_id, inputSHA256: result.receipt.input_sha256, receipt: bytes)
                tripDiscussionPermitState.heads[Data(original.head.conversation_id.utf8)] = .init(conversation_id: result.receipt.conversation_id, generation: result.receipt.generation, last_sequence: Int64(result.receipt.sequence))
                return .accepted
            }
            let error = try JSONDecoder().decode(Components.Schemas.ErrorResponse.self, from: bytes)
            if status == 409, error.error.code == "INPUT_CONFLICT", error.error.category == "conflict", error.error.outcome == .failed, error.error.recovery == .do_not_retry {
                try recovery.observeSubmissionInputConflict(submission.operation); tripDiscussionPermitState.decisions[key] = .integrityError
            } else { try recovery.observeUnknown(submission.operation) }
            tripDiscussionPermitState.heads.removeValue(forKey: Data(original.head.conversation_id.utf8))
            return .rejected(status: status, error: error)
        } catch {
            try recovery.observeUnknown(submission.operation)
            throw MessageHTTPFailure.exchangeUnknown
        }
    }
    public func tripDiscussionDecision(messageID: String, lease: Lease) throws -> MessageSendDecision? {
        try checkDiscussionLease(lease); return tripDiscussionPermitState.decisions[Data(messageID.utf8)]
    }
    public func requiresTripDiscussionResubmissionConfirmation(messageID: String, lease: Lease) throws -> Bool {
        try checkDiscussionLease(lease); return !tripDiscussionPermitState.intents.contains(Data(messageID.utf8))
    }
    public func reconcileTripDiscussion(messageID: String, lease: Lease) async throws -> MessageSendDecision {
        try checkDiscussionLease(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.invalidInput }
        let original = try OriginalTripDiscussion(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes, expectedMessageID: messageID)
        let key = Data(messageID.utf8), conversation = Data(original.head.conversation_id.utf8)
        tripDiscussionPermitState.decisions.removeValue(forKey: key); tripDiscussionPermitState.prepared.removeValue(forKey: key); tripDiscussionPermitState.heads.removeValue(forKey: conversation)
        let operation = try recovery.beginQuery(messageID: messageID, lease: lease)
        do {
            let (status, bytes, trace) = try await discussionExchange(path: discussionStatusPath(conversation: original.head.conversation_id, message: messageID), operation: "readTripDiscussionStatusV3", raw: nil, lease: lease)
            guard status == 200 else { throw MessageHTTPFailure.exchangeUnknown }
            let result = try TripDiscussionStatus(raw: bytes, maximumBytes: endpoint.maximumResponseBytes, requestID: trace, conversationID: original.head.conversation_id, original: original)
            let decision: MessageSendDecision
            if let accepted = result.acceptance, let receiptBytes = result.acceptedUTF8 {
                try tripDiscussionSources[key]?.validate(accepted.reference)
                try recovery.observeReceipt(operation, messageID: accepted.receipt.message_id, inputSHA256: accepted.receipt.input_sha256, receipt: receiptBytes)
                decision = .accepted
            } else {
                if let head = result.head {
                    if !DiscussionJSON.same(head.generation, original.head.generation) || head.last_sequence > original.head.last_sequence { decision = .notAccepted }
                    else if head.last_sequence == original.head.last_sequence { decision = .resubmitOriginal }
                    else { decision = .resyncRequired }
                } else { decision = .notAccepted }
                switch decision {
                case .notAccepted: try recovery.observeNotAccepted(operation)
                case .resyncRequired: try recovery.observeResyncRequired(operation)
                default: try recovery.observeNotObserved(operation)
                }
            }
            tripDiscussionPermitState.decisions[key] = decision
            if decision == .notAccepted {
                tripDiscussionPermitState.refreshedDecisions.remove(key)
                sendPermitState.historyEpochs[conversation] = UUID(); sendPermitState.historyHeads.removeValue(forKey: conversation)
            }
            if decision == .accepted || decision == .notAccepted, let head = result.head { tripDiscussionPermitState.heads[conversation] = head }
            return decision
        } catch {
            try recovery.observeUnknown(operation); throw MessageHTTPFailure.exchangeUnknown
        }
    }
    public func acceptedTripDiscussionReference(messageID: String, lease: Lease) throws -> MessageTripReference {
        try acceptedTripDiscussion(messageID: messageID, lease: lease).reference
    }
    public func acceptedTripDiscussion(messageID: String, lease: Lease) throws -> TripDiscussionMessage {
        try checkDiscussionLease(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease), record.phase == .accepted, let receipt = record.receipt else { throw RecoveryError.queryOnly }
        let original = try OriginalTripDiscussion(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes, expectedMessageID: messageID)
        let json = try DiscussionJSON(receipt, maximumBytes: endpoint.maximumResponseBytes)
        let trace = try DiscussionJSON.text(json.object["request_id"])
        let accepted = try TripDiscussionAcceptance(raw: receipt, maximumBytes: endpoint.maximumResponseBytes, requestID: trace, original: original)
        try tripDiscussionSources[Data(messageID.utf8)]?.validate(accepted.reference)
        try checkDiscussionLease(lease)
        return TripDiscussionMessage(receipt: accepted.receipt, reference: accepted.reference)
    }
}
