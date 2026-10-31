import Foundation
import CJMessageHTTP

/// Existing C TRIP-scoped-action.1 only. This immutable command is data,
/// never a current-source or confirmation permit.
public struct ScopedAction: Sendable {
    public enum Kind: String, Sendable { case accept, reject }
    public let actionID: String
    public let kind: Kind
    public let proposalID: String
    public let candidateHash: String
    public let originalUTF8: Data
    public static func stage(kind: Kind, proposalID: String, candidateHash: String) throws -> Self {
        try Self(actionID: UUID().uuidString, kind: kind, proposalID: proposalID, candidateHash: candidateHash)
    }
    init(actionID: String, kind: Kind, proposalID: String, candidateHash: String) throws {
        let raw=try JSONSerialization.data(withJSONObject:["version":"TRIP-scoped-action.1","action_id":actionID,
            "kind":kind.rawValue,"proposal_id":proposalID,"candidate_hash":candidateHash],options:[.sortedKeys,.withoutEscapingSlashes])
        try self.init(originalUTF8:raw)
    }
    public init(originalUTF8: Data) throws {
        let json=try ScopedWireJSON(originalUTF8,maximumBytes:32768)
        let fields=try ScopedWireJSON.fields(json.object,"version action_id kind proposal_id candidate_hash")
        guard fields["version"] as? String == "TRIP-scoped-action.1",
              let kind=Kind(rawValue:try ScopedWireJSON.text(fields["kind"])) else { throw PreviewFailure.invalidInput }
        actionID=try ScopedWireJSON.identifier(fields["action_id"])
        proposalID=try ScopedWireJSON.identifier(fields["proposal_id"])
        candidateHash=try ScopedWireJSON.hash(fields["candidate_hash"])
        let canonical=try JSONSerialization.data(withJSONObject:fields,options:[.sortedKeys,.withoutEscapingSlashes])
        guard canonical==originalUTF8 else { throw PreviewFailure.invalidInput }
        self.kind=kind;self.originalUTF8=originalUTF8
    }
}

/// Transport-checked original receipt. Null is kept as null, never a failed
/// action proof, a replacement ID or permission to retry a write.
public struct ScopedActionReceipt: Sendable, Equatable {
    public let actionID: String
    public let kind: ScopedAction.Kind
    public let proposalID: String
    public let candidateHash: String
    public let tripID: String
    public let committedVersion: Int64?
    public let responseUTF8: Data
    public static func decode(_ bytes: Data, requestID: String, original: ScopedAction,
                              tripID: String, expectedVersion: Int64, maximumBytes: Int) throws -> Self? {
        let json=try ScopedWireJSON(bytes,maximumBytes:maximumBytes)
        let fields=try ScopedWireJSON.fields(json.object,"version request_id receipt")
        guard fields["version"] as? String == "TRIP-scoped-result.1",
              fields["request_id"] as? String == requestID,UUID(uuidString:requestID) != nil else { throw PreviewFailure.invalidResponse }
        if fields["receipt"] is NSNull { return nil }
        let value=try ScopedWireJSON.fields(fields["receipt"],"action_id kind proposal_id candidate_hash trip_id committed_version")
        let aid=try ScopedWireJSON.identifier(value["action_id"]),pid=try ScopedWireJSON.identifier(value["proposal_id"])
        let digest=try ScopedWireJSON.hash(value["candidate_hash"]),tid=try ScopedWireJSON.identifier(value["trip_id"])
        guard value["kind"] as? String == original.kind.rawValue,aid==original.actionID,pid==original.proposalID,
              digest==original.candidateHash,tid==tripID,expectedVersion>0 else { throw PreviewFailure.invalidResponse }
        let version:Int64?
        switch original.kind {
        case .accept:
            let next=expectedVersion.addingReportingOverflow(1)
            let returned=try json.integer(["receipt","committed_version"],minimum:1)
            guard !next.overflow,returned==next.partialValue else { throw PreviewFailure.invalidResponse }
            version=returned
        case .reject:
            guard value["committed_version"] is NSNull else { throw PreviewFailure.invalidResponse };version=nil
        }
        return .init(actionID:aid,kind:original.kind,proposalID:pid,candidateHash:digest,tripID:tid,committedVersion:version,responseUTF8:bytes)
    }
}

/// Shared boundary within the existing preview package. Integer lexemes and
/// duplicate keys use the original MESSAGE validator; there is no new parser.
struct ScopedWireJSON {
    let object:[String:Any]
    let integers:[[String]:Int64]
    init(_ bytes:Data,maximumBytes:Int) throws {
        guard !bytes.isEmpty,bytes.count<=maximumBytes else { throw PreviewFailure.invalidResponse }
        integers=try validateUnambiguousJSON(bytes)
        guard let value=try JSONSerialization.jsonObject(with:bytes) as? [String:Any] else { throw PreviewFailure.invalidResponse }
        object=value
    }
    static func fields(_ value:Any?,_ names:String) throws -> [String:Any] {
        guard let fields=value as? [String:Any],Set(fields.keys)==Set(names.split(separator:" ").map(String.init)) else { throw PreviewFailure.invalidResponse }
        return fields
    }
    static func text(_ value:Any?) throws -> String {
        guard let text=value as? String,!text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else { throw PreviewFailure.invalidResponse };return text
    }
    static func identifier(_ value:Any?) throws -> String {
        let text=try text(value),bytes=Array(text.utf8)
        func alpha(_ b:UInt8)->Bool { (48...57).contains(b)||(65...90).contains(b)||(97...122).contains(b) }
        guard (1...128).contains(bytes.count),alpha(bytes[0]),bytes.allSatisfy({alpha($0)||[95,46,58,45].contains($0)}) else { throw PreviewFailure.invalidResponse };return text
    }
    static func hash(_ value:Any?) throws -> String {
        let text=try text(value)
        guard text.utf8.count==64,text.utf8.allSatisfy({(48...57).contains($0)||(97...102).contains($0)}) else { throw PreviewFailure.invalidResponse };return text
    }
    func integer(_ path:[String],minimum:Int64) throws -> Int64 {
        guard let value=integers[path],value>=minimum else { throw PreviewFailure.invalidResponse };return value
    }
}
