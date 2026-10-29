import Foundation
import CJAPI
import CJMessageClient
import OpenAPIRuntime

public enum MessageCreationIntent: String, Sendable { case none, considerTrip = "consider_trip" }
public enum MessageSendDecision: Sendable, Equatable {
    case accepted, notAccepted, resubmitOriginal, integrityError, resyncRequired
}

struct OriginalMessageSend {
    let head: Components.Schemas.MessageHead
    init(_ record: ActionRecord, maximumBytes: Int) throws {
        try self.init(raw: record.originalUTF8, maximumBytes: maximumBytes, expectedMessageID: record.messageID)
    }
    init(raw: Data, maximumBytes: Int, expectedMessageID: String? = nil) throws {
        guard raw.count <= maximumBytes else { throw RecoveryError.invalidInput }
        var parser = StrictJSON(bytes: Array(raw)); try parser.check()
        guard let value = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
              Set(value.keys) == ["version", "conversation_id", "message_id", "text", "trip_id", "creation_intent", "expected_generation", "expected_sequence"],
              value["version"] as? String == "MESSAGE-send.1", value["trip_id"] is NSNull,
              let message = value["message_id"] as? String, !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              expectedMessageID.map({ Data(message.utf8) == Data($0.utf8) }) ?? true,
              let cid = value["conversation_id"] as? String, !cid.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              cid.utf8.count <= 256, !cid.utf8.contains(0),
              let text = value["text"] as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let intent = value["creation_intent"] as? String, MessageCreationIntent(rawValue: intent) != nil,
              let generation = value["expected_generation"] as? String, !generation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let sequence = parser.topLevelUnsignedIntegers["expected_sequence"] else { throw RecoveryError.invalidInput }
        head = .init(conversation_id: cid, generation: generation, last_sequence: sequence)
    }
}

struct PreparedMessageSend {
    let digest: String
    let head: Components.Schemas.MessageHead
}
struct SendPermitState {
    var lease: Lease?
    var heads: [Data: Components.Schemas.MessageHead] = [:]
    var reads: [Data: UUID] = [:]
    var refreshedDecisions: Set<Data> = []
    var historyEpochs: [Data: UUID] = [:]
    var historyHeads: [Data: Components.Schemas.MessageHead] = [:]
    var prepared: [Data: PreparedMessageSend] = [:]
    var decisions: [Data: MessageSendDecision] = [:]
    var intents: Set<Data> = []
}

extension MessageHTTPClient {
    func checkSendLease(_ lease: Lease) throws {
        try recovery.validateScope(scope, lease: lease)
        if sendPermitState.lease != lease { sendPermitState = SendPermitState(lease: lease) }
    }

    /// Only a current-process server read populates this client's head cache.
    public func readSendHead(conversationID: String, lease: Lease) async throws -> Components.Schemas.MessageHead? {
        try checkSendLease(lease)
        guard !conversationID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              conversationID.utf8.count <= 256, !conversationID.utf8.contains(0) else { throw RecoveryError.invalidInput }
        let key = Data(conversationID.utf8), request = UUID()
        sendPermitState.reads[key] = request
        sendPermitState.heads.removeValue(forKey: key)
        let api = try await client(lease)
        let output: Operations.getMessageSendStatus.Output
        do { output = try await api.getMessageSendStatus(.init(query: .init(conversation_id: conversationID))) }
        catch { throw MessageHTTPFailure.exchangeUnknown }
        try checkSendLease(lease)
        guard sendPermitState.reads[key] == request else { throw RecoveryError.staleOperation }
        switch output {
        case .ok(let response):
            let body = try response.body.json
            guard case .case2(let receipt) = body.receipt, receipt.value == nil else { throw MessageHTTPFailure.invalidResponse }
            switch body.head {
            case .MessageHead(let head):
                guard Data(head.conversation_id.utf8) == key, !head.generation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      head.last_sequence >= 0 else { throw MessageHTTPFailure.invalidResponse }
                sendPermitState.heads[key] = head
                return head
            case .case2(let head):
                guard head.value == nil else { throw MessageHTTPFailure.invalidResponse }
                return nil
            }
        case .default: throw MessageHTTPFailure.exchangeUnknown
        }
    }

    /// User input is bound to a head obtained under this exact client/scope/lease.
    public func canStartSend(conversationID: String, lease: Lease) throws -> Bool {
        try readyHead(conversationID: conversationID, lease: lease) != nil
    }

    private func readyHead(conversationID: String, lease: Lease) throws -> Components.Schemas.MessageHead? {
        try checkSendLease(lease)
        let conversation = Data(conversationID.utf8)
        guard let head = sendPermitState.heads[conversation], head.last_sequence < Int64.max else { return nil }
        let local = try recovery.localProjection(scope: scope, lease: lease)
        for reference in local.actions where reference.phase != .accepted {
            guard let record = try recovery.action(messageID: reference.messageID, lease: lease) else { throw RecoveryError.staleOperation }
            var parser = StrictJSON(bytes: Array(record.originalUTF8)); try parser.check()
            guard let object = try JSONSerialization.jsonObject(with: record.originalUTF8) as? [String: Any],
                  let cid = object["conversation_id"] as? String else { throw RecoveryError.invalidSnapshot }
            if Data(cid.utf8) == conversation {
                if reference.phase == .notAccepted {
                    let original = try OriginalMessageSend(raw: record.originalUTF8, maximumBytes: endpoint.maximumRequestBytes)
                    if Data(original.head.generation.utf8) == Data(head.generation.utf8), head.last_sequence > original.head.last_sequence,
                       !sendPermitState.refreshedDecisions.contains(Data(record.messageID.utf8)) {
                        guard let history = sendPermitState.historyHeads[conversation],
                              Data(history.generation.utf8) == Data(head.generation.utf8),
                              history.last_sequence >= head.last_sequence else { return nil }
                        sendPermitState.refreshedDecisions.insert(Data(record.messageID.utf8))
                    }
                } else { return nil }
            }
        }
        return head
    }

    @discardableResult public func stageSend(messageID: String, conversationID: String, text: String,
        creationIntent: MessageCreationIntent = .none, lease: Lease) throws -> ActionRecord {
        try checkSendLease(lease)
        let conversation = Data(conversationID.utf8), key = Data(messageID.utf8)
        guard !messageID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let head = try readyHead(conversationID: conversationID, lease: lease),
              try recovery.action(messageID: messageID, lease: lease) == nil else { throw RecoveryError.queryOnly }
        let raw = try JSONSerialization.data(withJSONObject: ["version": "MESSAGE-send.1", "conversation_id": conversationID,
            "message_id": messageID, "text": text, "trip_id": NSNull(), "creation_intent": creationIntent.rawValue,
            "expected_generation": head.generation, "expected_sequence": head.last_sequence], options: [.sortedKeys])
        guard raw.count <= endpoint.maximumRequestBytes else { throw RecoveryError.invalidInput }
        sendPermitState.heads.removeValue(forKey: conversation) // reserve before a storage callback can reenter
        try recovery.stage(messageID: messageID, originalUTF8: raw, lease: lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.staleOperation }
        sendPermitState.prepared[key] = PreparedMessageSend(digest: record.inputSHA256, head: head)
        return record
    }

    public func submitPrepared(messageID: String, lease: Lease, confirmRestored: Bool = false) async throws -> MessageHTTPOutcome {
        if let liveMessageTransport { try liveMessageTransport.validateMessageSending(to: endpoint) }
        else if !submissionEnabledForTest { throw MessageHTTPFailure.productionActivationUnavailable }
        try checkSendLease(lease)
        let key = Data(messageID.utf8)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.queryOnly }
        if sendPermitState.decisions[key] == .resubmitOriginal {
            guard sendPermitState.intents.contains(key) || confirmRestored else { throw RecoveryError.queryOnly }
            let original = try OriginalMessageSend(record, maximumBytes: endpoint.maximumRequestBytes)
            sendPermitState.decisions.removeValue(forKey: key) // consume before storage reentry
            try recovery.authorizeOriginalResubmission(messageID: messageID, lease: lease)
            sendPermitState.prepared[key] = PreparedMessageSend(digest: record.inputSHA256, head: original.head)
        }
        guard
              let permit = sendPermitState.prepared[key], permit.digest == record.inputSHA256 else { throw RecoveryError.queryOnly }
        sendPermitState.prepared.removeValue(forKey: key)
        sendPermitState.intents.insert(key)
        let submission = try recovery.beginSubmission(messageID: messageID, lease: lease)
        let output: Operations.receiveMessage.Output
        do {
            let api = try await client(lease)
            output = try await api.receiveMessage(.init(body: .binary(HTTPBody(submission.originalUTF8))))
        } catch {
            try recovery.observeUnknown(submission.operation)
            throw MessageHTTPFailure.exchangeUnknown
        }
        try checkSendLease(lease)
        switch output {
        case .ok(let response):
            let receipt = try response.body.json.receipt
            let next = permit.head.last_sequence.addingReportingOverflow(1)
            guard Data(receipt.conversation_id.utf8) == Data(permit.head.conversation_id.utf8),
                  Data(receipt.generation.utf8) == Data(permit.head.generation.utf8),
                  !next.overflow, receipt.sequence == next.partialValue, !receipt.run_id.isEmpty else {
                try recovery.observeUnknown(submission.operation)
                throw MessageHTTPFailure.invalidResponse
            }
            try recovery.observeReceipt(submission.operation, messageID: receipt.message_id,
                inputSHA256: receipt.input_sha256, receipt: JSONEncoder().encode(receipt))
            sendPermitState.heads[Data(receipt.conversation_id.utf8)] = .init(conversation_id: receipt.conversation_id,
                generation: receipt.generation, last_sequence: Int64(receipt.sequence))
            return .accepted
        case .default(let status, let response):
            let body = try response.body.json
            if status == 409, body.error.code == "INPUT_CONFLICT", body.error.category == "conflict",
               body.error.outcome == .failed, body.error.recovery == .do_not_retry {
                try recovery.observeSubmissionInputConflict(submission.operation)
                sendPermitState.decisions[key] = .integrityError
            } else { try recovery.observeUnknown(submission.operation) }
            sendPermitState.heads.removeValue(forKey: Data(permit.head.conversation_id.utf8))
            return .rejected(status: status, error: body)
        }
    }

    public func requiresResubmissionConfirmation(messageID: String, lease: Lease) throws -> Bool {
        try checkSendLease(lease)
        return !sendPermitState.intents.contains(Data(messageID.utf8))
    }

    public func sendDecision(messageID: String, lease: Lease) throws -> MessageSendDecision? {
        try checkSendLease(lease)
        return sendPermitState.decisions[Data(messageID.utf8)]
    }

    public func hasSendHead(conversationID: String, lease: Lease) throws -> Bool {
        try checkSendLease(lease)
        return sendPermitState.heads[Data(conversationID.utf8)] != nil
    }

    public func reconcileSend(messageID: String, lease: Lease) async throws -> MessageSendDecision {
        try checkSendLease(lease)
        guard let record = try recovery.action(messageID: messageID, lease: lease) else { throw RecoveryError.invalidInput }
        let original = try OriginalMessageSend(record, maximumBytes: endpoint.maximumRequestBytes)
        let key = Data(messageID.utf8), conversation = Data(original.head.conversation_id.utf8)
        sendPermitState.decisions.removeValue(forKey: key)
        sendPermitState.prepared.removeValue(forKey: key)
        sendPermitState.heads.removeValue(forKey: conversation)
        let operation = try recovery.beginQuery(messageID: messageID, lease: lease)
        do {
            let api = try await client(lease)
            let output = try await api.getMessageSendStatus(.init(query: .init(conversation_id: original.head.conversation_id, message_id: messageID)))
            try checkSendLease(lease)
            guard case .ok(let response) = output else { throw MessageHTTPFailure.exchangeUnknown }
            let body = try response.body.json
            let head: Components.Schemas.MessageHead?
            switch body.head {
            case .MessageHead(let value):
                guard Data(value.conversation_id.utf8) == conversation, !value.generation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      value.last_sequence >= 0 else { throw MessageHTTPFailure.invalidResponse }
                head = value
            case .case2(let value):
                guard value.value == nil else { throw MessageHTTPFailure.invalidResponse }
                head = nil
            }
            let decision: MessageSendDecision
            switch body.receipt {
            case .MessageReceipt(let receipt):
                guard Data(receipt.message_id.utf8) == key, Data(receipt.conversation_id.utf8) == conversation,
                      !receipt.generation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      !receipt.run_id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                      receipt.sequence > 0, receipt.input_sha256.utf8.count == 64,
                      receipt.input_sha256.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else {
                    throw MessageHTTPFailure.invalidResponse
                }
                if receipt.input_sha256 == record.inputSHA256 {
                    try recovery.observeReceipt(operation, messageID: messageID, inputSHA256: receipt.input_sha256,
                                                receipt: JSONEncoder().encode(receipt))
                    decision = .accepted
                } else {
                    try recovery.observeIntegrityError(operation)
                    decision = .integrityError
                }
            case .case2(let value):
                guard value.value == nil else { throw MessageHTTPFailure.invalidResponse }
                if let head {
                    if Data(head.generation.utf8) != Data(original.head.generation.utf8) || head.last_sequence > original.head.last_sequence {
                        decision = .notAccepted
                    } else if head.last_sequence == original.head.last_sequence { decision = .resubmitOriginal }
                    else { decision = .resyncRequired }
                } else { decision = .notAccepted }
                if decision == .notAccepted { try recovery.observeNotAccepted(operation) }
                else if decision == .resyncRequired { try recovery.observeResyncRequired(operation) }
                else { try recovery.observeNotObserved(operation) }
            }
            // The operation check above rejects stale concurrent replies before cache mutation.
            sendPermitState.decisions[key] = decision
            if decision == .notAccepted {
                sendPermitState.refreshedDecisions.remove(key)
                sendPermitState.historyEpochs[conversation] = UUID()
                sendPermitState.historyHeads.removeValue(forKey: conversation)
            }
            if decision == .accepted || decision == .notAccepted, let head { sendPermitState.heads[conversation] = head }
            return decision
        } catch {
            try recovery.observeUnknown(operation)
            throw MessageHTTPFailure.exchangeUnknown
        }
    }
}
