import Foundation
import CJAPI
import CJMessageClient
import OpenAPIRuntime

/// NEEDS selection data, never a currentness/ownership permit. B revalidates the
/// explicit original reference in the accepted-message transaction.
public struct MessageNeedsSelection: Sendable {
    public let id: String
    public let expectedVersion: Int64
    public init(id: String,expectedVersion: Int64) throws {
        let bytes = Array(id.utf8)
        func alpha(_ c: UInt8) -> Bool { (48...57).contains(c) || (65...90).contains(c) || (97...122).contains(c) }
        guard (1...96).contains(bytes.count),let first = bytes.first,alpha(first),
              bytes.allSatisfy({ alpha($0) || [95,46,58,45].contains($0) }),expectedVersion > 0 else { throw RecoveryError.invalidInput }
        self.id = id;self.expectedVersion = expectedVersion
    }
}

extension MessageHTTPClient {
    private func checkTravelSendLease(_ lease: Lease) throws {
        try checkSendLease(lease) // canonical shared history fence, not a V1 send permit
        if travelSendPermitState.lease != lease { travelSendPermitState = SendPermitState(lease:lease) }
    }
    private func requireTravelSendCapability() throws {
        if let liveMessageTransport { try liveMessageTransport.validateTravelMessageSending(to:endpoint) }
        else if !submissionEnabledForTest { throw MessageHTTPFailure.productionActivationUnavailable }
    }
    /// Head and explicit-null receipt/reference are one current server snapshot.
    public func readTravelSendHead(conversationID: String,lease: Lease) async throws -> Components.Schemas.MessageHead? {
        try checkTravelSendLease(lease)
        guard !conversationID.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              conversationID.utf8.count <= 256,!conversationID.utf8.contains(0) else { throw RecoveryError.invalidInput }
        let key = Data(conversationID.utf8),request = UUID()
        travelSendPermitState.reads[key] = request;travelSendPermitState.heads.removeValue(forKey:key)
        let api = try await client(lease)
        let output: Operations.getMessageSendStatusV2.Output
        do { output = try await api.getMessageSendStatusV2(.init(query:.init(conversation_id:conversationID))) }
        catch { try checkTravelSendLease(lease);throw MessageHTTPFailure.exchangeUnknown }
        try checkTravelSendLease(lease)
        guard travelSendPermitState.reads[key] == request else { throw RecoveryError.staleOperation }
        guard case .ok(let response) = output else { throw MessageHTTPFailure.exchangeUnknown }
        let body = try response.body.json
        guard case .CJExplicitJSONNull = body.receipt,
              case .CJExplicitJSONNull = body.reference else { throw MessageHTTPFailure.invalidResponse }
        switch body.head {
        case .MessageHead(let head):
            try validateTravelHead(head,conversation:key)
            travelSendPermitState.heads[key] = head;return head
        case .CJExplicitJSONNull:return nil
        }
    }
    private func validateTravelHead(_ head: Components.Schemas.MessageHead,conversation: Data) throws {
        guard Data(head.conversation_id.utf8) == conversation,!head.generation.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              head.last_sequence >= 0 else { throw MessageHTTPFailure.invalidResponse }
    }
    private func readyTravelHead(conversationID: String,lease: Lease) throws -> Components.Schemas.MessageHead? {
        try checkTravelSendLease(lease)
        let conversation = Data(conversationID.utf8)
        guard let head = travelSendPermitState.heads[conversation],head.last_sequence < Int64.max else { return nil }
        let local = try recovery.localProjection(scope:scope,lease:lease)
        for reference in local.actions where reference.phase != .accepted {
            guard let record = try recovery.action(messageID:reference.messageID,lease:lease) else { throw RecoveryError.staleOperation }
            var parser = StrictJSON(bytes:Array(record.originalUTF8));try parser.check()
            guard let object = try JSONSerialization.jsonObject(with:record.originalUTF8) as? [String:Any],
                  let id = object["conversation_id"] as? String else { throw RecoveryError.invalidSnapshot }
            guard Data(id.utf8) == conversation else { continue }
            guard reference.phase == .notAccepted else { return nil }
            let expected: Components.Schemas.MessageHead
            switch object["version"] as? String {
            case "MESSAGE-send.2":expected = try OriginalTravelMessageSend(raw:record.originalUTF8,maximumBytes:endpoint.maximumRequestBytes).head
            case "MESSAGE-send.1":expected = try OriginalMessageSend(record,maximumBytes:endpoint.maximumRequestBytes).head
            default:throw RecoveryError.invalidSnapshot
            }
            if Data(expected.generation.utf8) == Data(head.generation.utf8),head.last_sequence > expected.last_sequence,
               !travelSendPermitState.refreshedDecisions.contains(Data(record.messageID.utf8)) {
                guard let history = sendPermitState.historyHeads[conversation],Data(history.generation.utf8) == Data(head.generation.utf8),
                      history.last_sequence >= head.last_sequence else { return nil }
                travelSendPermitState.refreshedDecisions.insert(Data(record.messageID.utf8))
            }
        }
        return head
    }
    public func canStartTravelSend(conversationID: String,lease: Lease) throws -> Bool {
        try requireTravelSendCapability();return try readyTravelHead(conversationID:conversationID,lease:lease) != nil
    }
    /// nil travel/NEEDS are explicitly encoded as null; neither field is omitted.
    /// A travel choice must originate in this client's current-lease B read.
    @discardableResult public func stageTravelSend(messageID: String,conversationID: String,text: String,
        creationIntent: MessageCreationIntent,travelContext: MessageReadResult<Components.Schemas.TravelContextReadResponse.travel_contextPayload>?,
        needsReference: MessageNeedsSelection?,lease: Lease) throws -> ActionRecord {
        try requireTravelSendCapability();try checkTravelSendLease(lease)
        let context: Any
        if let travelContext {
            try validateRead(travelContext,lease:lease)
            guard travelContext.value.active else { throw RecoveryError.invalidInput }
            context = ["id":travelContext.value.id,"expected_version":travelContext.value.version]
        } else { context = NSNull() }
        let needs: Any
        if let needsReference { needs = ["id":needsReference.id,"expected_version":needsReference.expectedVersion] }
        else { needs = NSNull() }
        guard let head = try readyTravelHead(conversationID:conversationID,lease:lease),
              try recovery.action(messageID:messageID,lease:lease) == nil else { throw RecoveryError.queryOnly }
        let raw = try JSONSerialization.data(withJSONObject:["version":"MESSAGE-send.2","message_id":messageID,
            "conversation_id":conversationID,"text":text,"trip_id":NSNull(),"creation_intent":creationIntent.rawValue,
            "expected_generation":head.generation,"expected_sequence":head.last_sequence,"travel_context":context,"needs_reference":needs],options:[.sortedKeys])
        _ = try OriginalTravelMessageSend(raw:raw,maximumBytes:endpoint.maximumRequestBytes,expectedMessageID:messageID)
        let conversation = Data(conversationID.utf8),key = Data(messageID.utf8)
        travelSendPermitState.heads.removeValue(forKey:conversation)
        try recovery.stage(messageID:messageID,originalUTF8:raw,lease:lease)
        guard let record = try recovery.action(messageID:messageID,lease:lease) else { throw RecoveryError.staleOperation }
        travelSendPermitState.prepared[key] = PreparedMessageSend(digest:record.inputSHA256,head:head)
        return record
    }
    public func submitPreparedTravelSend(messageID: String,lease: Lease,confirmRestored: Bool = false) async throws -> MessageHTTPOutcome {
        try requireTravelSendCapability();try checkTravelSendLease(lease)
        let key = Data(messageID.utf8)
        guard let record = try recovery.action(messageID:messageID,lease:lease) else { throw RecoveryError.queryOnly }
        let original = try OriginalTravelMessageSend(raw:record.originalUTF8,maximumBytes:endpoint.maximumRequestBytes,expectedMessageID:messageID)
        if travelSendPermitState.decisions[key] == .resubmitOriginal {
            guard travelSendPermitState.intents.contains(key) || confirmRestored else { throw RecoveryError.queryOnly }
            travelSendPermitState.decisions.removeValue(forKey:key)
            try recovery.authorizeOriginalResubmission(messageID:messageID,lease:lease)
            travelSendPermitState.prepared[key] = PreparedMessageSend(digest:record.inputSHA256,head:original.head)
        }
        guard let permit = travelSendPermitState.prepared[key],permit.digest == record.inputSHA256 else { throw RecoveryError.queryOnly }
        travelSendPermitState.prepared.removeValue(forKey:key);travelSendPermitState.intents.insert(key)
        let submission = try recovery.beginSubmission(messageID:messageID,lease:lease)
        do {
            let api = try await client(lease)
            let output = try await api.receiveMessageV2(.init(body:.binary(HTTPBody(submission.originalUTF8))))
            try checkTravelSendLease(lease)
            switch output {
            case .ok(let response):
                let body = try response.body.json
                _ = try ValidatedTravelMessageReceipt(receipt:body.receipt,reference:body.reference,original:original)
                try recovery.observeReceipt(submission.operation,messageID:body.receipt.message_id,inputSHA256:body.receipt.input_sha256,receipt:JSONEncoder().encode(body))
                travelSendPermitState.heads[Data(body.receipt.conversation_id.utf8)] = .init(conversation_id:body.receipt.conversation_id,generation:body.receipt.generation,last_sequence:Int64(body.receipt.sequence))
                return .accepted
            case .default(let status,let response):
                let body = try response.body.json
                if status == 409,body.error.code == "INPUT_CONFLICT",body.error.category == "conflict",body.error.outcome == .failed,body.error.recovery == .do_not_retry {
                    try recovery.observeSubmissionInputConflict(submission.operation);travelSendPermitState.decisions[key] = .integrityError
                } else { try recovery.observeUnknown(submission.operation) }
                travelSendPermitState.heads.removeValue(forKey:Data(original.head.conversation_id.utf8))
                return .rejected(status:status,error:body)
            }
        } catch {
            try recovery.observeUnknown(submission.operation);throw MessageHTTPFailure.exchangeUnknown
        }
    }
    public func requiresTravelResubmissionConfirmation(messageID: String,lease: Lease) throws -> Bool {
        try checkTravelSendLease(lease);return !travelSendPermitState.intents.contains(Data(messageID.utf8))
    }
    public func travelSendDecision(messageID: String,lease: Lease) throws -> MessageSendDecision? {
        try checkTravelSendLease(lease);return travelSendPermitState.decisions[Data(messageID.utf8)]
    }
    public func reconcileTravelSend(messageID: String,lease: Lease) async throws -> MessageSendDecision {
        try checkTravelSendLease(lease)
        guard let record = try recovery.action(messageID:messageID,lease:lease) else { throw RecoveryError.invalidInput }
        let original = try OriginalTravelMessageSend(raw:record.originalUTF8,maximumBytes:endpoint.maximumRequestBytes,expectedMessageID:messageID)
        let key = Data(messageID.utf8),conversation = Data(original.head.conversation_id.utf8)
        travelSendPermitState.decisions.removeValue(forKey:key);travelSendPermitState.prepared.removeValue(forKey:key);travelSendPermitState.heads.removeValue(forKey:conversation)
        let operation = try recovery.beginQuery(messageID:messageID,lease:lease)
        do {
            let api = try await client(lease)
            let output = try await api.getMessageSendStatusV2(.init(query:.init(conversation_id:original.head.conversation_id,message_id:messageID)))
            try checkTravelSendLease(lease)
            guard case .ok(let response) = output else { throw MessageHTTPFailure.exchangeUnknown }
            let body = try response.body.json
            let head: Components.Schemas.MessageHead?
            switch body.head {
            case .MessageHead(let value):try validateTravelHead(value,conversation:conversation);head = value
            case .CJExplicitJSONNull:head = nil
            }
            let decision: MessageSendDecision
            switch body.receipt {
            case .MessageReceipt(let receipt):
                guard case .MessageTravelReference(let reference) = body.reference else { throw MessageHTTPFailure.invalidResponse }
                _ = try ValidatedTravelMessageReceipt(receipt:receipt,reference:reference,original:original)
                let accepted = Components.Schemas.MessageReceiveV2Response(request_id:body.request_id,version:.MESSAGE_hyphen_accept_period_2,receipt:receipt,reference:reference)
                try recovery.observeReceipt(operation,messageID:receipt.message_id,inputSHA256:receipt.input_sha256,receipt:JSONEncoder().encode(accepted))
                decision = .accepted
            case .CJExplicitJSONNull:
                guard case .CJExplicitJSONNull = body.reference else { throw MessageHTTPFailure.invalidResponse }
                if let head {
                    if Data(head.generation.utf8) != Data(original.head.generation.utf8) || head.last_sequence > original.head.last_sequence { decision = .notAccepted }
                    else if head.last_sequence == original.head.last_sequence { decision = .resubmitOriginal }
                    else { decision = .resyncRequired }
                } else { decision = .notAccepted }
                if decision == .notAccepted { try recovery.observeNotAccepted(operation) }
                else if decision == .resyncRequired { try recovery.observeResyncRequired(operation) }
                else { try recovery.observeNotObserved(operation) }
            }
            travelSendPermitState.decisions[key] = decision
            if decision == .notAccepted {
                travelSendPermitState.refreshedDecisions.remove(key)
                sendPermitState.historyEpochs[conversation] = UUID();sendPermitState.historyHeads.removeValue(forKey:conversation)
            }
            if (decision == .accepted || decision == .notAccepted),let head { travelSendPermitState.heads[conversation] = head }
            return decision
        } catch { try recovery.observeUnknown(operation);throw MessageHTTPFailure.exchangeUnknown }
    }
}
