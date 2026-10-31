import Foundation
import CryptoKit
import CJAPI

/// Frozen send.4 selections are data. Only B/C can establish current sources,
/// generate a candidate or accept it; discussion text cannot confer that intent.
public enum MessageModificationIntent: String, Sendable {
    case none
    case proposeScopedEdit = "propose_scoped_edit"
}

public struct MessageEditTripSelection: Sendable, Equatable {
    public let id: String
    public let expectedVersion: Int64
    public let contentSHA256: String
    public let day: MessageTripSelection.Day?
    public let itemIDs: [String]
    public init(id: String, expectedVersion: Int64, contentSHA256: String,
                day: MessageTripSelection.Day?, itemIDs: [String]) throws {
        guard MessageTripSelection.identifier(id), expectedVersion > 0,
              itemIDs.count <= 60, Set(itemIDs).count == itemIDs.count,
              itemIDs.allSatisfy(MessageTripSelection.identifier) else { throw MessageHTTPFailure.invalidResponse }
        self.id = id; self.expectedVersion = expectedVersion
        self.contentSHA256 = try DiscussionJSON.hash(contentSHA256)
        self.day = day; self.itemIDs = itemIDs
    }
    var object: [String: Any] {
        ["id": id, "expected_version": expectedVersion, "content_sha256": contentSHA256,
         "day": day.map { $0.object as Any } ?? NSNull(), "item_ids": itemIDs]
    }
    static func read(_ value: Any?, json: DiscussionJSON, path: [String]) throws -> Self {
        let f = try DiscussionJSON.fields(value, "id expected_version content_sha256 day item_ids")
        let day: MessageTripSelection.Day?
        if f["day"] is NSNull { day = nil }
        else {
            let d = try DiscussionJSON.fields(f["day"], "date timezone")
            day = try .init(date: DiscussionJSON.text(d["date"]), timezone: DiscussionJSON.text(d["timezone"]))
        }
        guard let items = f["item_ids"] as? [String] else { throw MessageHTTPFailure.invalidResponse }
        return try .init(id: DiscussionJSON.text(f["id"]), expectedVersion: json.integer(path + ["expected_version"], minimum: 1),
                         contentSHA256: DiscussionJSON.hash(f["content_sha256"]), day: day, itemIDs: items)
    }
}

/// An independent travel namespace, never derived from the formal Trip ID.
public struct MessageEditNamespace: Sendable, Equatable {
    public let id: String
    public let expectedVersion: Int64
    public init(id: String, expectedVersion: Int64) throws {
        guard id.utf8.count == 32,
              id.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
              expectedVersion > 0 else { throw MessageHTTPFailure.invalidResponse }
        self.id = id; self.expectedVersion = expectedVersion
    }
    var object: [String: Any] { ["id": id, "expected_version": expectedVersion] }
    static func read(_ value: Any?, json: DiscussionJSON, path: [String]) throws -> Self {
        let f = try DiscussionJSON.fields(value, "id expected_version")
        return try .init(id: DiscussionJSON.text(f["id"]), expectedVersion: json.integer(path + ["expected_version"], minimum: 1))
    }
}

private func editNeeds(_ value: Any?, json: DiscussionJSON, path: [String]) throws -> MessageNeedsSelection? {
    if value is NSNull { return nil }
    let f = try DiscussionJSON.fields(value, "id expected_version")
    return try .init(id: DiscussionJSON.text(f["id"]), expectedVersion: json.integer(path + ["expected_version"], minimum: 1))
}

struct OriginalTripEdit {
    let originalUTF8: Data
    let head: Components.Schemas.MessageHead
    let messageID: String
    let text: String
    let intent: MessageModificationIntent
    let trip: MessageEditTripSelection
    let namespace: MessageEditNamespace
    let needs: MessageNeedsSelection?
    init(raw: Data, maximumBytes: Int, expectedMessageID: String? = nil) throws {
        let json = try DiscussionJSON(raw, maximumBytes: maximumBytes)
        let f = try DiscussionJSON.fields(json.object, "version conversation_id message_id text trip_id creation_intent expected_generation expected_sequence trip_context travel_context needs_reference modification_intent")
        guard f["version"] as? String == "MESSAGE-send.4", f["trip_id"] is NSNull,
              f["creation_intent"] as? String == "none",
              let intent = MessageModificationIntent(rawValue: try DiscussionJSON.text(f["modification_intent"])) else { throw MessageHTTPFailure.invalidResponse }
        let conversation = try DiscussionJSON.text(f["conversation_id"])
        let message = try DiscussionJSON.text(f["message_id"])
        guard conversation.utf8.count <= 256, !conversation.utf8.contains(0),
              expectedMessageID.map({ DiscussionJSON.same($0, message) }) ?? true else { throw MessageHTTPFailure.invalidResponse }
        let trip = try MessageEditTripSelection.read(f["trip_context"], json: json, path: ["trip_context"])
        let needs = try editNeeds(f["needs_reference"], json: json, path: ["needs_reference"])
        if intent == .proposeScopedEdit {
            guard (trip.day != nil) != !trip.itemIDs.isEmpty, needs != nil else { throw MessageHTTPFailure.invalidResponse }
        } else { guard needs == nil else { throw MessageHTTPFailure.invalidResponse } }
        originalUTF8 = raw; messageID = message; text = try DiscussionJSON.text(f["text"])
        head = try .init(conversation_id: conversation, generation: DiscussionJSON.text(f["expected_generation"]), last_sequence: json.integer(["expected_sequence"], minimum: 0))
        self.intent = intent; self.trip = trip; self.needs = needs
        namespace = try .read(f["travel_context"], json: json, path: ["travel_context"])
    }
}

/// Original accepted association. Decoding this value cannot issue a source
/// lease, update a selection or grant confirmation permission.
public struct MessageEditReference: Sendable, Equatable {
    public let conversationID: String
    public let generation: String
    public let messageID: String
    public let runID: String
    public let sequence: Int64
    public let inputSHA256: String
    public let intent: MessageModificationIntent
    public let trip: MessageEditTripSelection
    public let resolvedItemIDs: [String]
    public let contentVersion: String
    public let namespace: MessageEditNamespace
    public let needs: MessageNeedsSelection?
    public let selectionEpoch: Int64
    public static func == (a: Self, b: Self) -> Bool {
        DiscussionJSON.same(a.conversationID, b.conversationID) && DiscussionJSON.same(a.generation, b.generation) &&
        DiscussionJSON.same(a.messageID, b.messageID) && DiscussionJSON.same(a.runID, b.runID) &&
        a.sequence == b.sequence && a.inputSHA256 == b.inputSHA256 && a.intent == b.intent && a.trip == b.trip &&
        a.resolvedItemIDs == b.resolvedItemIDs && a.contentVersion == b.contentVersion &&
        a.namespace == b.namespace && a.needs == b.needs && a.selectionEpoch == b.selectionEpoch
    }
    public static func decodeResponseReference(_ bytes: Data, maximumBytes: Int) throws -> Self {
        let json = try DiscussionJSON(bytes, maximumBytes: maximumBytes)
        return try read(json.object["reference"], json: json, path: ["reference"])
    }
    static func read(_ value: Any?, json: DiscussionJSON, path: [String]) throws -> Self {
        let f = try DiscussionJSON.fields(value, "version message_version conversation_id generation message_id run_id sequence input_sha256 modification_intent trip_context resolved_item_ids content_version namespace needs_reference selection_epoch")
        guard f["version"] as? String == "MESSAGE-edit-reference.1", f["message_version"] as? String == "MESSAGE-send.4",
              let intent = MessageModificationIntent(rawValue: try DiscussionJSON.text(f["modification_intent"])),
              let ids = f["resolved_item_ids"] as? [String], (1...60).contains(ids.count),
              Set(ids).count == ids.count, ids.allSatisfy(MessageTripSelection.identifier) else { throw MessageHTTPFailure.invalidResponse }
        let trip = try MessageEditTripSelection.read(f["trip_context"], json: json, path: path + ["trip_context"])
        let needs = try editNeeds(f["needs_reference"], json: json, path: path + ["needs_reference"])
        if intent == .proposeScopedEdit {
            guard (trip.day != nil) != !trip.itemIDs.isEmpty, needs != nil else { throw MessageHTTPFailure.invalidResponse }
        } else { guard needs == nil else { throw MessageHTTPFailure.invalidResponse } }
        if trip.day == nil && !trip.itemIDs.isEmpty { guard ids == trip.itemIDs else { throw MessageHTTPFailure.invalidResponse } }
        let n = try DiscussionJSON.fields(f["namespace"], "kind id version")
        guard n["kind"] as? String == "travel" else { throw MessageHTTPFailure.invalidResponse }
        let namespace = try MessageEditNamespace(id: DiscussionJSON.text(n["id"]), expectedVersion: json.integer(path + ["namespace", "version"], minimum: 1))
        let version = try DiscussionJSON.text(f["content_version"])
        guard version == "structured.1" || version == "structured.2" else { throw MessageHTTPFailure.invalidResponse }
        let sequence = try json.integer(path + ["sequence"], minimum: 1)
        let epoch = try json.integer(path + ["selection_epoch"], minimum: 1)
        guard epoch <= sequence else { throw MessageHTTPFailure.invalidResponse }
        return try .init(conversationID: DiscussionJSON.text(f["conversation_id"]), generation: DiscussionJSON.text(f["generation"]),
                         messageID: DiscussionJSON.text(f["message_id"]), runID: DiscussionJSON.text(f["run_id"]), sequence: sequence,
                         inputSHA256: DiscussionJSON.hash(f["input_sha256"]), intent: intent, trip: trip, resolvedItemIDs: ids,
                         contentVersion: version, namespace: namespace, needs: needs, selectionEpoch: epoch)
    }
    func validate(receipt: Components.Schemas.MessageReceipt, original: OriginalTripEdit) throws {
        let next = original.head.last_sequence.addingReportingOverflow(1)
        let hash = SHA256.hash(data: original.originalUTF8).map { String(format: "%02x", $0) }.joined()
        guard !next.overflow, receipt.sequence == next.partialValue, sequence == receipt.sequence,
              DiscussionJSON.same(receipt.message_id, original.messageID), DiscussionJSON.same(messageID, receipt.message_id),
              DiscussionJSON.same(receipt.conversation_id, original.head.conversation_id), DiscussionJSON.same(conversationID, receipt.conversation_id),
              DiscussionJSON.same(receipt.generation, original.head.generation), DiscussionJSON.same(generation, receipt.generation),
              DiscussionJSON.same(runID, receipt.run_id), inputSHA256 == hash, receipt.input_sha256 == hash,
              intent == original.intent, trip == original.trip, namespace == original.namespace, needs == original.needs else { throw MessageHTTPFailure.invalidResponse }
    }
}

struct TripEditAcceptance {
    let receipt: Components.Schemas.MessageReceipt
    let reference: MessageEditReference
    init(raw: Data, maximumBytes: Int, requestID: String, original: OriginalTripEdit) throws {
        let json = try DiscussionJSON(raw, maximumBytes: maximumBytes)
        let f = try DiscussionJSON.fields(json.object, "request_id version receipt reference")
        guard f["version"] as? String == "MESSAGE-accept.4", f["request_id"] as? String == requestID,
              UUID(uuidString: requestID) != nil else { throw MessageHTTPFailure.invalidResponse }
        try self.init(fields: f, json: json, original: original)
    }
    init(fields: [String: Any], json: DiscussionJSON, original: OriginalTripEdit) throws {
        _ = try DiscussionJSON.fields(fields["receipt"], "message_id conversation_id generation sequence run_id input_sha256")
        _ = try json.integer(["receipt", "sequence"], minimum: 1)
        receipt = try JSONDecoder().decode(Components.Schemas.MessageReceipt.self, from: JSONSerialization.data(withJSONObject: fields["receipt"]!))
        reference = try .read(fields["reference"], json: json, path: ["reference"])
        try reference.validate(receipt: receipt, original: original)
    }
}

struct TripEditStatus {
    let head: Components.Schemas.MessageHead?
    let acceptance: TripEditAcceptance?
    let acceptedUTF8: Data?
    init(raw: Data, maximumBytes: Int, requestID: String, conversationID: String, original: OriginalTripEdit?) throws {
        let json = try DiscussionJSON(raw, maximumBytes: maximumBytes)
        let f = try DiscussionJSON.fields(json.object, "request_id version receipt reference head")
        guard f["version"] as? String == "MESSAGE-send-status.4", f["request_id"] as? String == requestID,
              UUID(uuidString: requestID) != nil else { throw MessageHTTPFailure.invalidResponse }
        if f["head"] is NSNull { head = nil }
        else {
            let h = try DiscussionJSON.fields(f["head"], "conversation_id generation last_sequence")
            let id = try DiscussionJSON.text(h["conversation_id"])
            guard DiscussionJSON.same(id, conversationID) else { throw MessageHTTPFailure.invalidResponse }
            head = try .init(conversation_id: id, generation: DiscussionJSON.text(h["generation"]), last_sequence: json.integer(["head", "last_sequence"], minimum: 0))
        }
        if f["receipt"] is NSNull {
            guard f["reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
            acceptance = nil; acceptedUTF8 = nil
        } else {
            guard let original else { throw MessageHTTPFailure.invalidResponse }
            acceptance = try .init(fields: f, json: json, original: original)
            acceptedUTF8 = try JSONSerialization.data(withJSONObject: ["request_id": requestID, "version": "MESSAGE-accept.4", "receipt": f["receipt"]!, "reference": f["reference"]!], options: [.sortedKeys])
        }
    }
}
