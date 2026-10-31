import Foundation
import CJAPI
import CJMessageClient
import OpenAPIRuntime
import HTTPTypes

/// Validated original association data, never a server execution permit.
public struct TripEditMessage: Sendable {
    public let receipt: Components.Schemas.MessageReceipt
    public let reference: MessageEditReference
}

extension MessageHTTPClient {
    private func checkEditLease(_ lease: Lease) throws {
        try checkSendLease(lease)
        if tripEditPermitState.lease != lease { tripEditPermitState = SendPermitState(lease: lease);tripEditSources=[:] }
    }
    private func requireEditCapability() throws {
        if let liveMessageTransport { try liveMessageTransport.validateTripEditSending(to: endpoint) }
        else if !submissionEnabledForTest { throw MessageHTTPFailure.productionActivationUnavailable }
    }
    private func editStatusPath(conversation: String, message: String?) throws -> String {
        guard !conversation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              conversation.utf8.count <= 256, !conversation.utf8.contains(0) else { throw RecoveryError.invalidInput }
        var parts = URLComponents(); parts.path = "/v4/message-send-status"
        parts.queryItems = [.init(name: "conversation_id", value: conversation)]
        if let message { parts.queryItems!.append(.init(name: "message_id", value: message)) }
        guard let value = parts.string else { throw RecoveryError.invalidInput }
        return value
    }
    /// A fresh head from this client's current signed status read, never a caller
    /// DTO or a restored head. Reading it does not upgrade a MEMORY scope.
    public func readTripEditHead(conversationID: String, lease: Lease) async throws -> Components.Schemas.MessageHead? {
        try checkEditLease(lease)
        let key = Data(conversationID.utf8), request = UUID()
        tripEditPermitState.reads[key] = request
        tripEditPermitState.heads.removeValue(forKey: key)
        let (status, bytes, trace) = try await versionedMessageExchange(path: editStatusPath(conversation: conversationID, message: nil), operation: "readTripEditStatusV4", raw: nil, lease: lease)
        guard tripEditPermitState.reads[key] == request else { throw RecoveryError.staleOperation }
        guard status == 200 else {
            throw MessageReadFailure.rejected(status: status, error: try editError(bytes, maximumBytes: endpoint.maximumResponseBytes, requestID: trace))
        }
        let result = try TripEditStatus(raw: bytes, maximumBytes: endpoint.maximumResponseBytes, requestID: trace, conversationID: conversationID, original: nil)
        if let head = result.head { tripEditPermitState.heads[key] = head }
        return result.head
    }
    private func readyEditHead(conversationID: String, lease: Lease) throws -> Components.Schemas.MessageHead? {
        try checkEditLease(lease)
        let conversation = Data(conversationID.utf8)
        guard let head = tripEditPermitState.heads[conversation], head.last_sequence < Int64.max else { return nil }
        guard try !recovery.conversationOpenings(lease:lease).contains(where:{ Data($0.conversationID.utf8)==conversation && $0.phase == .queryRequired }) else { return nil }
        let projection = try recovery.localProjection(scope: scope, lease: lease)
        for reference in projection.actions where reference.phase != .accepted {
            guard let record = try recovery.action(messageID: reference.messageID, lease: lease) else { throw RecoveryError.staleOperation }
            let json = try DiscussionJSON(record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes)
            let id = try DiscussionJSON.text(json.object["conversation_id"])
            guard Data(id.utf8) == conversation else { continue }
            guard reference.phase == .notAccepted else { return nil }
            let expected: Components.Schemas.MessageHead
            switch json.object["version"] as? String {
            case "MESSAGE-send.4": expected = try OriginalTripEdit(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes).head
            case "MESSAGE-send.3": expected = try OriginalTripDiscussion(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes).head
            case "MESSAGE-send.2": expected = try OriginalTravelMessageSend(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes).head
            case "MESSAGE-send.1": expected = try OriginalMessageSend(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes).head
            default: throw RecoveryError.invalidSnapshot
            }
            if DiscussionJSON.same(expected.generation, head.generation), head.last_sequence > expected.last_sequence,
               !tripEditPermitState.refreshedDecisions.contains(Data(record.messageID.utf8)) {
                guard let history = sendPermitState.historyHeads[conversation], DiscussionJSON.same(history.generation, head.generation), history.last_sequence >= head.last_sequence else { return nil }
                tripEditPermitState.refreshedDecisions.insert(Data(record.messageID.utf8))
            }
        }
        try checkEditLease(lease)
        return head
    }
    public func canStartTripEdit(conversationID: String, lease: Lease) throws -> Bool {
        try requireEditCapability()
        return try readyEditHead(conversationID: conversationID, lease: lease) != nil
    }
    /// Called with the current accepted Trip, independently selected namespace
    /// and current NEEDS. These values never replace B/C currentness checks.
    @discardableResult public func stageTripEdit(messageID: String, conversationID: String, text: String,
        intent: MessageModificationIntent, trip: MessageEditTripSelection, namespace: MessageEditNamespace,
        needs: MessageNeedsSelection?, content: MessageTripContent, lease: Lease) throws -> ActionRecord {
        try requireEditCapability(); try checkEditLease(lease)
        guard content.sha256 == trip.contentSHA256 else { throw RecoveryError.invalidInput }
        guard let head = try readyEditHead(conversationID: conversationID, lease: lease),
              try recovery.action(messageID: messageID, lease: lease) == nil else { throw RecoveryError.queryOnly }
        let raw = try JSONSerialization.data(withJSONObject: ["version": "MESSAGE-send.4", "message_id": messageID,
            "conversation_id": conversationID, "text": text, "trip_id": NSNull(), "creation_intent": "none",
            "expected_generation": head.generation, "expected_sequence": head.last_sequence,
            "modification_intent": intent.rawValue, "trip_context": trip.object, "travel_context": namespace.object,
            "needs_reference": needs.map { ["id": $0.id, "expected_version": $0.expectedVersion] as Any } ?? NSNull()], options: [.sortedKeys])
        _ = try OriginalTripEdit(raw: raw, maximumBytes: endpoint.maximumRequestBytes, expectedMessageID: messageID)
        tripEditPermitState.heads.removeValue(forKey: Data(conversationID.utf8))
        try recovery.stage(messageID: messageID, originalUTF8: raw, lease: lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.staleOperation }
        tripEditPermitState.prepared[Data(messageID.utf8)] = PreparedMessageSend(digest: record.inputSHA256, head: head)
        tripEditSources[Data(messageID.utf8)] = content
        return record
    }
    public func submitPreparedTripEdit(messageID: String, lease: Lease, confirmRestored: Bool = false) async throws -> MessageHTTPOutcome {
        try requireEditCapability(); try checkEditLease(lease)
        let key = Data(messageID.utf8)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.queryOnly }
        let original = try OriginalTripEdit(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes, expectedMessageID: messageID)
        if tripEditPermitState.decisions[key] == .resubmitOriginal {
            guard tripEditPermitState.intents.contains(key) || confirmRestored else { throw RecoveryError.queryOnly }
            tripEditPermitState.decisions.removeValue(forKey: key)
            try recovery.authorizeOriginalResubmission(messageID: messageID, lease: lease)
            tripEditPermitState.prepared[key] = PreparedMessageSend(digest: record.inputSHA256, head: original.head)
        }
        guard let permit = tripEditPermitState.prepared[key], permit.digest == record.inputSHA256 else { throw RecoveryError.queryOnly }
        tripEditPermitState.prepared.removeValue(forKey: key); tripEditPermitState.intents.insert(key)
        let submission = try recovery.beginSubmission(messageID: messageID, lease: lease)
        do {
            let (status, bytes, trace) = try await versionedMessageExchange(path: "/v4/messages", operation: "receiveTripEditV4", raw: submission.originalUTF8, lease: lease)
            if status == 200 {
                let result = try TripEditAcceptance(raw: bytes, maximumBytes: endpoint.maximumResponseBytes, requestID: trace, original: original)
                try tripEditSources[key]?.validate(result.reference)
                try recovery.observeReceipt(submission.operation, messageID: result.receipt.message_id, inputSHA256: result.receipt.input_sha256, receipt: bytes)
                tripEditPermitState.heads[Data(original.head.conversation_id.utf8)] = .init(conversation_id: result.receipt.conversation_id, generation: result.receipt.generation, last_sequence: Int64(result.receipt.sequence))
                return .accepted
            }
            let error = try editError(bytes, maximumBytes: endpoint.maximumResponseBytes, requestID: trace)
            if status == 409, error.error.code == "INPUT_CONFLICT", error.error.category == "conflict", error.error.outcome == .failed, error.error.recovery == .do_not_retry {
                try recovery.observeSubmissionInputConflict(submission.operation); tripEditPermitState.decisions[key] = .integrityError
            } else if error.error.outcome == .failed && error.error.recovery == .do_not_retry {
                try recovery.observeSubmissionRejection(submission.operation, httpStatus: status, responseUTF8: bytes)
                tripEditPermitState.decisions[key] = .notAccepted
            } else { try recovery.observeUnknown(submission.operation) }
            tripEditPermitState.heads.removeValue(forKey: Data(original.head.conversation_id.utf8))
            return .rejected(status: status, error: error)
        } catch {
            try recovery.observeUnknown(submission.operation)
            throw MessageHTTPFailure.exchangeUnknown
        }
    }
    public func tripEditDecision(messageID: String, lease: Lease) throws -> MessageSendDecision? {
        try checkEditLease(lease); return tripEditPermitState.decisions[Data(messageID.utf8)]
    }
    public func requiresTripEditResubmissionConfirmation(messageID: String, lease: Lease) throws -> Bool {
        try checkEditLease(lease); return !tripEditPermitState.intents.contains(Data(messageID.utf8))
    }
    public func reconcileTripEdit(messageID: String, lease: Lease) async throws -> MessageSendDecision {
        try checkEditLease(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.invalidInput }
        let original = try OriginalTripEdit(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes, expectedMessageID: messageID)
        let key = Data(messageID.utf8), conversation = Data(original.head.conversation_id.utf8)
        tripEditPermitState.decisions.removeValue(forKey: key); tripEditPermitState.prepared.removeValue(forKey: key); tripEditPermitState.heads.removeValue(forKey: conversation)
        let operation = try recovery.beginQuery(messageID: messageID, lease: lease)
        do {
            let (status, bytes, trace) = try await versionedMessageExchange(path: editStatusPath(conversation: original.head.conversation_id, message: messageID), operation: "readTripEditStatusV4", raw: nil, lease: lease)
            guard status == 200 else { throw MessageHTTPFailure.exchangeUnknown }
            let result = try TripEditStatus(raw: bytes, maximumBytes: endpoint.maximumResponseBytes, requestID: trace, conversationID: original.head.conversation_id, original: original)
            let decision: MessageSendDecision
            if let accepted = result.acceptance, let receiptBytes = result.acceptedUTF8 {
                try tripEditSources[key]?.validate(accepted.reference)
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
            tripEditPermitState.decisions[key] = decision
            if decision == .notAccepted {
                tripEditPermitState.refreshedDecisions.remove(key)
                sendPermitState.historyEpochs[conversation] = UUID(); sendPermitState.historyHeads.removeValue(forKey: conversation)
            }
            if decision == .accepted || decision == .notAccepted, let head = result.head { tripEditPermitState.heads[conversation] = head }
            return decision
        } catch {
            try recovery.observeUnknown(operation); throw MessageHTTPFailure.exchangeUnknown
        }
    }
    public func acceptedTripEditReference(messageID: String, lease: Lease) throws -> MessageEditReference {
        try acceptedTripEdit(messageID: messageID, lease: lease).reference
    }
    public func acceptedTripEdit(messageID: String, lease: Lease) throws -> TripEditMessage {
        try checkEditLease(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease), record.phase == .accepted, let receipt = record.receipt else { throw RecoveryError.queryOnly }
        let original = try OriginalTripEdit(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes, expectedMessageID: messageID)
        let json = try DiscussionJSON(receipt, maximumBytes: endpoint.maximumResponseBytes)
        let trace = try DiscussionJSON.text(json.object["request_id"])
        let accepted = try TripEditAcceptance(raw: receipt, maximumBytes: endpoint.maximumResponseBytes, requestID: trace, original: original)
        try tripEditSources[Data(messageID.utf8)]?.validate(accepted.reference)
        try checkEditLease(lease)
        return TripEditMessage(receipt: accepted.receipt, reference: accepted.reference)
    }
}
