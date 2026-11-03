import Foundation
import CryptoKit
import CJAPI

public enum MessageHumanSourceState: String, Sendable {
    case retained, erased, notApplicable = "not_applicable"
}

/// Human display only. No original command bytes, typed effect reference,
/// scoped result or conversion to an accepted send/recovery grant is exposed.
public struct MessageHumanHistoryItem: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let receipt: Components.Schemas.MessageReceipt
    public let text: String
    public let sourceState: MessageHumanSourceState
    public var description: String { "<private human history>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
    public let id = UUID()
    fileprivate let reference: Data?
    fileprivate let canEraseSource: Bool
    fileprivate init(receipt: Components.Schemas.MessageReceipt, text: String,
        sourceState: MessageHumanSourceState, reference: Data?, canEraseSource: Bool) {
        self.receipt = receipt; self.text = text; self.sourceState = sourceState; self.reference = reference; self.canEraseSource = canEraseSource
    }
}

public struct MessageHumanRun: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let snapshot: Components.Schemas.RunDisplaySnapshot
    public let sourceState: MessageHumanSourceState
    public let requestID: String
    public var description: String { "<private human answer>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

struct PreservedHistoryPage {
    let rows: [MessageHumanHistoryItem]
    let next: String?
    init(raw: Data, maximumBytes: Int, decodedLimit: Int, limit: Int, requestID: String) throws {
        let json = try DiscussionJSON(raw, maximumBytes: maximumBytes)
        let fields = try DiscussionJSON.fields(json.object, "request_id version messages next_cursor")
        guard fields["version"] as? String == "MESSAGE-history.5",
              fields["request_id"] as? String == requestID, UUID(uuidString: requestID) != nil,
              let values = fields["messages"] as? [[String: Any]], values.count <= limit else { throw MessageHTTPFailure.invalidResponse }
        next = try DiscussionJSON.nullableText(fields["next_cursor"])
        var rows: [MessageHumanHistoryItem] = [], remaining = decodedLimit
        for (index, value) in values.enumerated() {
            let f = try DiscussionJSON.fields(value, "receipt original_utf8_base64 text reference source_state")
            _ = try DiscussionJSON.fields(f["receipt"], "message_id conversation_id generation sequence run_id input_sha256")
            _ = try json.integer(["messages", String(index), "receipt", "sequence"], minimum: 1)
            let receipt = try JSONDecoder().decode(Components.Schemas.MessageReceipt.self,
                from: JSONSerialization.data(withJSONObject: f["receipt"]!))
            guard let encoded = f["original_utf8_base64"] as? String, let original = Data(base64Encoded: encoded),
                  original.count <= remaining, original.base64EncodedString() == encoded,
                  let text = f["text"] as? String,
                  let state = (f["source_state"] as? String).flatMap(MessageHumanSourceState.init(rawValue:)) else { throw MessageHTTPFailure.invalidResponse }
            remaining -= original.count
            let source = try DiscussionJSON(original, maximumBytes: decodedLimit)
            guard let message = source.object["message_id"] as? String, let conversation = source.object["conversation_id"] as? String,
                  let originalText = source.object["text"] as? String,
                  DiscussionJSON.same(message, receipt.message_id), DiscussionJSON.same(conversation, receipt.conversation_id),
                  DiscussionJSON.same(text, originalText),
                  SHA256.hash(data: original).map({ String(format: "%02x", $0) }).joined() == receipt.input_sha256 else { throw MessageHTTPFailure.invalidResponse }
            let path = ["messages", String(index), "reference"]
            var canEraseSource = false
            switch source.object["version"] as? String {
            case "MESSAGE-send.3":
                let command = try OriginalTripDiscussion(raw: original, maximumBytes: decodedLimit, expectedMessageID: receipt.message_id)
                try preservedHead(command.head, receipt: receipt)
                canEraseSource = command.trip != nil
                if state == .retained {
                    try MessageTripReference.read(f["reference"], json: json, path: path).validate(receipt: receipt, original: command)
                } else {
                    guard state == .erased, command.trip != nil, f["reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
                }
            case "MESSAGE-send.4":
                let command = try OriginalTripEdit(raw: original, maximumBytes: decodedLimit, expectedMessageID: receipt.message_id)
                try preservedHead(command.head, receipt: receipt)
                canEraseSource = true
                if state == .retained {
                    try MessageEditReference.read(f["reference"], json: json, path: path).validate(receipt: receipt, original: command)
                } else {
                    guard state == .erased, f["reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
                }
            case "MESSAGE-send.2":
                guard state == .retained else { throw MessageHTTPFailure.invalidResponse }
                let command = try OriginalTravelMessageSend(raw: original, maximumBytes: decodedLimit, expectedMessageID: receipt.message_id)
                let ref = try DiscussionJSON.fields(f["reference"], "version conversation_id generation message_id run_id sequence input_sha256 message_version context_kind context_id context_version selection_epoch")
                _ = try json.integer(path + ["sequence"], minimum: 1)
                _ = try json.integer(path + ["selection_epoch"], minimum: 1)
                if !(ref["context_version"] is NSNull) { _ = try json.integer(path + ["context_version"], minimum: 1) }
                let decoded = try JSONDecoder().decode(Components.Schemas.MessageTravelReference.self, from: JSONSerialization.data(withJSONObject: ref))
                _ = try ValidatedTravelMessageReceipt(receipt: receipt, reference: decoded, original: command)
            case "MESSAGE-send.1", "MESSAGE-draft.1":
                guard state == .notApplicable, f["reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
            default: throw MessageHTTPFailure.invalidResponse
            }
            let reference = state == .retained ? try JSONSerialization.data(withJSONObject: f["reference"]!, options: [.sortedKeys, .withoutEscapingSlashes]) : nil
            rows.append(.init(receipt: receipt, text: text, sourceState: state, reference: reference, canEraseSource: canEraseSource))
        }
        self.rows = rows
    }
}

private func preservedHead(_ head: Components.Schemas.MessageHead, receipt: Components.Schemas.MessageReceipt) throws {
    let next = head.last_sequence.addingReportingOverflow(1)
    guard !next.overflow, next.partialValue == receipt.sequence,
          DiscussionJSON.same(head.generation, receipt.generation) else { throw MessageHTTPFailure.invalidResponse }
}

func decodePreservedRun(_ raw: Data, maximumBytes: Int, textLimit: Int, trace: String,
    row: MessageHumanHistoryItem) throws -> MessageHumanRun {
    let json = try DiscussionJSON(raw, maximumBytes: maximumBytes)
    let f = try DiscussionJSON.fields(json.object, "request_id version snapshot reference source_state")
    guard f["version"] as? String == "RUN-display.6", f["request_id"] as? String == trace,
          UUID(uuidString: trace) != nil,
          let state = (f["source_state"] as? String).flatMap(MessageHumanSourceState.init(rawValue:)) else { throw MessageHTTPFailure.invalidResponse }
    switch state {
    case .retained:
        guard row.sourceState == .retained,
              let value = f["reference"] as? [String: Any],
              try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes]) == row.reference else { throw MessageHTTPFailure.invalidResponse }
    case .erased:
        guard row.canEraseSource, row.sourceState != .notApplicable, f["reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
    case .notApplicable:
        guard row.sourceState == .notApplicable, f["reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
    }
    let snapshotValue = try DiscussionJSON.fields(f["snapshot"], "conversation_id generation message_id run_id message_sequence status event_highwater text text_state")
    _ = try json.integer(["snapshot", "message_sequence"], minimum: 1)
    _ = try json.integer(["snapshot", "event_highwater"], minimum: 0)
    let snapshot = try JSONDecoder().decode(Components.Schemas.RunDisplaySnapshot.self,
        from: JSONSerialization.data(withJSONObject: snapshotValue))
    let r = row.receipt
    guard DiscussionJSON.same(snapshot.conversation_id, r.conversation_id), DiscussionJSON.same(snapshot.generation, r.generation),
          DiscussionJSON.same(snapshot.message_id, r.message_id), DiscussionJSON.same(snapshot.run_id, r.run_id),
          snapshot.message_sequence == r.sequence, snapshot.text.utf8.count <= textLimit,
          (snapshot.text_state == .complete) == (snapshot.status == .completed) else { throw MessageHTTPFailure.invalidResponse }
    return .init(snapshot: snapshot, sourceState: state, requestID: trace)
}
