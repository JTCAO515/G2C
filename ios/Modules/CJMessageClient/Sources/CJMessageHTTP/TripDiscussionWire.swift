import Foundation
import CryptoKit
import CJAPI

/// Explicit selection data for frozen SEND-V3. This is neither an ownership
/// permit nor a Trip write capability; the server validates current membership.
public struct MessageTripSelection: Sendable, Equatable {
    public struct Day: Sendable, Equatable {
        public let date: String
        public let timezone: String
        public init(date: String, timezone: String) throws {
            let bytes = Array(date.utf8)
            guard bytes.count == 10, bytes[4] == 45, bytes[7] == 45,
                  bytes.enumerated().allSatisfy({ [4, 7].contains($0.offset) || (48...57).contains($0.element) }),
                  let year = Int(date.prefix(4)), year > 0,
                  let month = Int(date.dropFirst(5).prefix(2)), (1...12).contains(month),
                  let day = Int(date.suffix(2)) else { throw MessageHTTPFailure.invalidResponse }
            let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
            let days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            guard (1...days[month - 1]).contains(day), timezone.count <= 128,
                  TimeZone.knownTimeZoneIdentifiers.contains(timezone) || ["UTC", "Etc/UTC", "GMT", "Etc/GMT"].contains(timezone),
                  TimeZone(identifier: timezone) != nil else { throw MessageHTTPFailure.invalidResponse }
            self.date = date; self.timezone = timezone
        }
        var object: [String: Any] { ["date": date, "timezone": timezone] }
    }
    public let id: String
    public let expectedVersion: Int64
    public let day: Day?
    public let itemID: String?
    public init(id: String, expectedVersion: Int64, day: Day?, itemID: String?) throws {
        guard Self.identifier(id), expectedVersion > 0,
              itemID.map(Self.identifier) ?? true else { throw MessageHTTPFailure.invalidResponse }
        self.id = id; self.expectedVersion = expectedVersion; self.day = day; self.itemID = itemID
    }
    static func identifier(_ text: String) -> Bool {
        let bytes = Array(text.utf8)
        func alpha(_ c: UInt8) -> Bool { (48...57).contains(c) || (65...90).contains(c) || (97...122).contains(c) }
        return (1...128).contains(bytes.count) && alpha(bytes[0]) && bytes.allSatisfy { alpha($0) || [95, 46, 58, 45].contains($0) }
    }
    var object: [String: Any] {
        ["id": id, "expected_version": expectedVersion, "day": day.map { $0.object as Any } ?? NSNull(), "item_id": itemID.map { $0 as Any } ?? NSNull()]
    }
    static func read(_ value: Any?, json: DiscussionJSON, path: [String]) throws -> Self {
        let fields = try DiscussionJSON.fields(value, "id expected_version day item_id")
        let day: Day?
        if fields["day"] is NSNull { day = nil }
        else {
            let value = try DiscussionJSON.fields(fields["day"], "date timezone")
            day = try Day(date: DiscussionJSON.text(value["date"]), timezone: DiscussionJSON.text(value["timezone"]))
        }
        let item = try DiscussionJSON.nullableText(fields["item_id"])
        return try .init(id: DiscussionJSON.text(fields["id"]), expectedVersion: json.integer(path + ["expected_version"], minimum: 1), day: day, itemID: item)
    }
}

/// Duplicate keys and integer lexemes are checked before Foundation conversion.
/// No rounding, omitted-null default, unknown-field stripping or raw-byte rewrite.
struct DiscussionJSON {
    let object: [String: Any]
    let integers: [[String]: Int64]
    init(_ bytes: Data, maximumBytes: Int) throws {
        guard bytes.count <= maximumBytes else { throw MessageHTTPFailure.invalidResponse }
        integers = try validateUnambiguousJSON(bytes)
        guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any] else { throw MessageHTTPFailure.invalidResponse }
        self.object = object
    }
    static func fields(_ value: Any?, _ names: String) throws -> [String: Any] {
        guard let fields = value as? [String: Any], Set(fields.keys) == Set(names.split(separator: " ").map(String.init)) else { throw MessageHTTPFailure.invalidResponse }
        return fields
    }
    static func text(_ value: Any?) throws -> String {
        guard let text = value as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw MessageHTTPFailure.invalidResponse }
        return text
    }
    static func nullableText(_ value: Any?) throws -> String? {
        if value is NSNull { return nil }
        return try text(value)
    }
    func integer(_ path: [String], minimum: Int64) throws -> Int64 {
        guard let value = integers[path], value >= minimum else { throw MessageHTTPFailure.invalidResponse }
        return value
    }
    static func same(_ a: String, _ b: String) -> Bool { Data(a.utf8) == Data(b.utf8) }
    static func hash(_ value: Any?) throws -> String {
        let text = try text(value)
        guard text.utf8.count == 64, text.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { throw MessageHTTPFailure.invalidResponse }
        return text
    }
}

struct OriginalTripDiscussion {
    let originalUTF8: Data
    let messageID: String
    let text: String
    let head: Components.Schemas.MessageHead
    let trip: MessageTripSelection?
    let travel: OriginalTravelMessageSend.Selection?
    init(raw: Data, maximumBytes: Int, expectedMessageID: String? = nil) throws {
        let json = try DiscussionJSON(raw, maximumBytes: maximumBytes)
        let fields = try DiscussionJSON.fields(json.object, "version conversation_id message_id text trip_id creation_intent expected_generation expected_sequence travel_context needs_reference trip_context")
        guard fields["version"] as? String == "MESSAGE-send.3", fields["trip_id"] is NSNull,
              fields["creation_intent"] as? String == "none", fields["needs_reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
        let conversation = try DiscussionJSON.text(fields["conversation_id"])
        let message = try DiscussionJSON.text(fields["message_id"])
        guard conversation.utf8.count <= 256, !conversation.utf8.contains(0),
              expectedMessageID.map({ DiscussionJSON.same($0, message) }) ?? true else { throw MessageHTTPFailure.invalidResponse }
        if fields["trip_context"] is NSNull { trip = nil }
        else { trip = try MessageTripSelection.read(fields["trip_context"], json: json, path: ["trip_context"]) }
        if fields["travel_context"] is NSNull { travel = nil }
        else {
            let choice = try DiscussionJSON.fields(fields["travel_context"], "id expected_version")
            let id = try DiscussionJSON.text(choice["id"])
            guard trip == nil, id.utf8.count == 32, id.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { throw MessageHTTPFailure.invalidResponse }
            travel = try .init(id: id, expectedVersion: json.integer(["travel_context", "expected_version"], minimum: 1))
        }
        originalUTF8 = raw; messageID = message; text = try DiscussionJSON.text(fields["text"])
        head = try .init(conversation_id: conversation, generation: DiscussionJSON.text(fields["expected_generation"]), last_sequence: json.integer(["expected_sequence"], minimum: 0))
    }
}

/// Original SEND-V3 association data only. Constructor is closed to wire readers;
/// this reference never refreshes a selection or grants execution authority.
public struct MessageTripReference: Sendable, Equatable {
    public let conversationID: String
    public let generation: String
    public let messageID: String
    public let runID: String
    public let sequence: Int64
    public let inputSHA256: String
    public let selectionEpoch: Int64
    public let trip: MessageTripSelection?
    public let contentVersion: String?
    public let contentSHA256: String?
    let contextID: String?
    let contextVersion: Int64?
    let contextKind: String
    public static func == (lhs: Self, rhs: Self) -> Bool {
        DiscussionJSON.same(lhs.conversationID, rhs.conversationID) && DiscussionJSON.same(lhs.generation, rhs.generation) &&
        DiscussionJSON.same(lhs.messageID, rhs.messageID) && DiscussionJSON.same(lhs.runID, rhs.runID) &&
        lhs.sequence == rhs.sequence && lhs.inputSHA256 == rhs.inputSHA256 && lhs.selectionEpoch == rhs.selectionEpoch &&
        lhs.trip == rhs.trip && lhs.contentVersion == rhs.contentVersion && lhs.contentSHA256 == rhs.contentSHA256 &&
        lhs.contextID == rhs.contextID && lhs.contextVersion == rhs.contextVersion && lhs.contextKind == rhs.contextKind
    }
    static func read(_ value: Any?, json: DiscussionJSON, path: [String]) throws -> Self {
        let f = try DiscussionJSON.fields(value, "version conversation_id generation message_id run_id sequence input_sha256 message_version context_kind context_id context_version selection_epoch trip_context content_version content_sha256")
        guard f["version"] as? String == "MESSAGE-trip-reference.1", f["message_version"] as? String == "MESSAGE-send.3" else { throw MessageHTTPFailure.invalidResponse }
        let kind = try DiscussionJSON.text(f["context_kind"])
        let contextID = try DiscussionJSON.nullableText(f["context_id"])
        let contextVersion = try f["context_version"] is NSNull ? nil : json.integer(path + ["context_version"], minimum: 1)
        let trip = try f["trip_context"] is NSNull ? nil : MessageTripSelection.read(f["trip_context"], json: json, path: path + ["trip_context"])
        let contentVersion = try DiscussionJSON.nullableText(f["content_version"])
        let contentHash = try f["content_sha256"] is NSNull ? nil : DiscussionJSON.hash(f["content_sha256"])
        switch kind {
        case "trip":
            guard let trip, contextID == trip.id, contextVersion == trip.expectedVersion,
                  contentVersion == "structured.1" || contentVersion == "structured.2", contentHash != nil else { throw MessageHTTPFailure.invalidResponse }
        case "travel":
            guard let contextID, contextID.utf8.count == 32, contextID.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
                  contextVersion != nil, trip == nil, contentVersion == nil, contentHash == nil else { throw MessageHTTPFailure.invalidResponse }
        case "none":
            guard contextID == nil, contextVersion == nil, trip == nil, contentVersion == nil, contentHash == nil else { throw MessageHTTPFailure.invalidResponse }
        default: throw MessageHTTPFailure.invalidResponse
        }
        let sequence = try json.integer(path + ["sequence"], minimum: 1)
        let epoch = try json.integer(path + ["selection_epoch"], minimum: 1)
        guard epoch <= sequence else { throw MessageHTTPFailure.invalidResponse }
        return try .init(conversationID: DiscussionJSON.text(f["conversation_id"]), generation: DiscussionJSON.text(f["generation"]), messageID: DiscussionJSON.text(f["message_id"]), runID: DiscussionJSON.text(f["run_id"]), sequence: sequence, inputSHA256: DiscussionJSON.hash(f["input_sha256"]), selectionEpoch: epoch, trip: trip, contentVersion: contentVersion, contentSHA256: contentHash, contextID: contextID, contextVersion: contextVersion, contextKind: kind)
    }
    func validate(receipt: Components.Schemas.MessageReceipt, original: OriginalTripDiscussion) throws {
        let next = original.head.last_sequence.addingReportingOverflow(1)
        let hash = SHA256.hash(data: original.originalUTF8).map { String(format: "%02x", $0) }.joined()
        guard !next.overflow, receipt.sequence == next.partialValue, sequence == receipt.sequence,
              DiscussionJSON.same(receipt.message_id, original.messageID), DiscussionJSON.same(messageID, receipt.message_id),
              DiscussionJSON.same(receipt.conversation_id, original.head.conversation_id), DiscussionJSON.same(conversationID, receipt.conversation_id),
              DiscussionJSON.same(receipt.generation, original.head.generation), DiscussionJSON.same(generation, receipt.generation),
              DiscussionJSON.same(runID, receipt.run_id), !runID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              inputSHA256 == hash, receipt.input_sha256 == hash, trip == original.trip else { throw MessageHTTPFailure.invalidResponse }
        if let travel = original.travel {
            guard contextKind == "travel", contextID == travel.id, contextVersion == travel.expectedVersion else { throw MessageHTTPFailure.invalidResponse }
        } else if original.trip == nil {
            guard contextKind == "none" else { throw MessageHTTPFailure.invalidResponse }
        }
    }
}

struct TripDiscussionAcceptance {
    let receipt: Components.Schemas.MessageReceipt
    let reference: MessageTripReference
    init(raw: Data, maximumBytes: Int, requestID: String, original: OriginalTripDiscussion) throws {
        let json = try DiscussionJSON(raw, maximumBytes: maximumBytes)
        let f = try DiscussionJSON.fields(json.object, "request_id version receipt reference")
        guard f["version"] as? String == "MESSAGE-accept.3", f["request_id"] as? String == requestID,
              UUID(uuidString: requestID) != nil else { throw MessageHTTPFailure.invalidResponse }
        try self.init(fields: f, json: json, original: original)
    }
    init(fields f: [String: Any], json: DiscussionJSON, original: OriginalTripDiscussion) throws {
        _ = try DiscussionJSON.fields(f["receipt"], "message_id conversation_id generation sequence run_id input_sha256")
        // Validate the lexical sequence before decoding the generated receipt.
        _ = try json.integer(["receipt", "sequence"], minimum: 1)
        receipt = try JSONDecoder().decode(Components.Schemas.MessageReceipt.self, from: JSONSerialization.data(withJSONObject: f["receipt"]!))
        reference = try MessageTripReference.read(f["reference"], json: json, path: ["reference"])
        try reference.validate(receipt: receipt, original: original)
    }
}

struct TripDiscussionStatus {
    let head: Components.Schemas.MessageHead?
    let acceptance: TripDiscussionAcceptance?
    let acceptedUTF8: Data?
    init(raw: Data, maximumBytes: Int, requestID: String, conversationID: String, original: OriginalTripDiscussion?) throws {
        let json = try DiscussionJSON(raw, maximumBytes: maximumBytes)
        let f = try DiscussionJSON.fields(json.object, "request_id version receipt reference head")
        guard f["version"] as? String == "MESSAGE-send-status.3", f["request_id"] as? String == requestID,
              UUID(uuidString: requestID) != nil else { throw MessageHTTPFailure.invalidResponse }
        if f["head"] is NSNull { head = nil }
        else {
            let fields = try DiscussionJSON.fields(f["head"], "conversation_id generation last_sequence")
            let id = try DiscussionJSON.text(fields["conversation_id"])
            guard DiscussionJSON.same(id, conversationID) else { throw MessageHTTPFailure.invalidResponse }
            head = try .init(conversation_id: id, generation: DiscussionJSON.text(fields["generation"]), last_sequence: json.integer(["head", "last_sequence"], minimum: 0))
        }
        if f["receipt"] is NSNull {
            guard f["reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
            acceptance = nil; acceptedUTF8 = nil
        } else {
            guard let original else { throw MessageHTTPFailure.invalidResponse }
            acceptance = try .init(fields: f, json: json, original: original)
            // Store an accepted envelope only after validating the original status
            // lexemes. The immutable send bytes are never reconstructed.
            acceptedUTF8 = try JSONSerialization.data(withJSONObject: ["request_id": requestID, "version": "MESSAGE-accept.3", "receipt": f["receipt"]!, "reference": f["reference"]!], options: [.sortedKeys])
        }
    }
}
