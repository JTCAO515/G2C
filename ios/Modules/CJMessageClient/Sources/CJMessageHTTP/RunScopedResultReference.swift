import Foundation

public enum ScopedRunResultKind: String, Sendable {
    case clarificationRequired = "clarification_required"
    case expansionRequired = "expansion_required"
}

/// Historical RUN-scoped-result.1 data bound to an original edit reference.
/// This is neither a source lease, a Proposal nor permission to expand or accept.
public struct RunScopedResultReference: Sendable, Equatable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let kind: ScopedRunResultKind
    public let resultID: String
    public let messageID: String
    public let runID: String
    public let inputSHA256: String
    public var description: String { "<redacted scoped result reference>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }

    public static func == (a: Self, b: Self) -> Bool {
        a.kind == b.kind && DiscussionJSON.same(a.resultID, b.resultID) &&
        DiscussionJSON.same(a.messageID, b.messageID) && DiscussionJSON.same(a.runID, b.runID) && a.inputSHA256 == b.inputSHA256
    }

    /// Decode only the mandatory metadata member. The enclosing reader must
    /// separately validate its own frozen envelope, status and original receipt.
    public static func decodeResponseReference(_ bytes: Data, maximumBytes: Int, matching original: MessageEditReference) throws -> Self? {
        let json = try DiscussionJSON(bytes, maximumBytes: maximumBytes)
        return try read(json.object["scoped_result"], matching: original)
    }

    static func read(_ value: Any?, matching original: MessageEditReference) throws -> Self? {
        if value is NSNull { return nil }
        let f = try DiscussionJSON.fields(value, "version kind result_id message_id run_id input_sha256")
        guard f["version"] as? String == "RUN-scoped-result.1",
              let kind = ScopedRunResultKind(rawValue: try DiscussionJSON.text(f["kind"])),
              original.intent == .proposeScopedEdit else { throw MessageHTTPFailure.invalidResponse }
        let result = try DiscussionJSON.text(f["result_id"])
        let message = try DiscussionJSON.text(f["message_id"]), run = try DiscussionJSON.text(f["run_id"])
        let hash = try DiscussionJSON.hash(f["input_sha256"])
        guard MessageTripSelection.identifier(result), DiscussionJSON.same(message, original.messageID),
              DiscussionJSON.same(run, original.runID), hash == original.inputSHA256 else { throw MessageHTTPFailure.invalidResponse }
        return Self(kind: kind, resultID: result, messageID: message, runID: run, inputSHA256: hash)
    }
}
