import Foundation
import CJAPI
import CJMessageHTTP

enum RunFormalReference: Sendable {
    case discussion(MessageTripReference), edit(MessageEditReference)
    var wireVersion: Int { switch self { case .discussion: 3; case .edit: 4 } }
    var displayOperation: String { switch self { case .discussion: "getTripRunDisplayV3"; case .edit: "getTripEditRunDisplayV4" } }
    var cancelOperation: String { switch self { case .discussion: "cancelOriginalTripRunV3"; case .edit: "cancelOriginalTripEditRunV4" } }
    func requireOriginal(_ bytes: Data) throws {
        let matches: Bool
        switch self {
        case .discussion(let reference):matches = try MessageTripReference.decodeResponseReference(bytes,maximumBytes:bytes.count) == reference
        case .edit(let reference):matches = try MessageEditReference.decodeResponseReference(bytes,maximumBytes:bytes.count) == reference
        }
        guard matches else { throw RunDisplayFailure.invalidReference }
    }
}

/// Frozen discussion/edit RUN envelopes retain their separate wire versions. The original
/// Message reference is compared in full, including epoch, day/item and hash.
struct RunTripEnvelope {
    let object: [String: Any]
    let integers: [[String]: Int64]
    init(_ bytes: Data, fields: String, version: String, reference: MessageTripReference) throws {
        try self.init(bytes,fields:fields,version:version,reference:.discussion(reference))
    }
    init(_ bytes: Data, fields: String, version: String, reference: MessageEditReference) throws {
        try self.init(bytes,fields:fields,version:version,reference:.edit(reference))
    }
    init(_ bytes: Data, fields: String, version: String, reference: RunFormalReference) throws {
        integers = try validateUnambiguousJSON(bytes)
        guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              Set(object.keys) == Set(fields.split(separator: " ").map(String.init)),
              object["version"] as? String == version else { throw RunDisplayFailure.invalidReference }
        try reference.requireOriginal(bytes)
        self.object = object
    }
    func requireIntegers(_ names: [String], prefix: [String] = []) throws {
        for name in names { guard integers[prefix + [name]] != nil else { throw RunDisplayFailure.invalidResponse } }
    }
    func display() throws -> (Components.Schemas.RunDisplaySnapshot, String) {
        guard let snapshot = object["snapshot"] as? [String: Any],
              Set(snapshot.keys) == Set("conversation_id generation message_id run_id message_sequence status event_highwater text text_state".split(separator: " ").map(String.init)),
              let trace = object["request_id"] as? String else { throw RunDisplayFailure.invalidResponse }
        try requireIntegers(["message_sequence", "event_highwater"], prefix: ["snapshot"])
        return (try JSONDecoder().decode(Components.Schemas.RunDisplaySnapshot.self, from: JSONSerialization.data(withJSONObject: snapshot)), trace)
    }
}

public struct RunTripDraftStatus: Sendable {
    public let runStatus: Components.Schemas.RunDraftStatusV2Response.run_statusPayload
    public let draftOutcome: Components.Schemas.RunDraftStatusV2Response.draft_outcomePayload
    public let budgetStage: Components.Schemas.RunDraftStatusV2Response.budget_exhausted_stagePayload
    public let reference: MessageTripReference
}
public struct RunEditDraftStatus: Sendable {
    public let runStatus: Components.Schemas.RunDraftStatusV2Response.run_statusPayload
    public let draftOutcome: Components.Schemas.RunDraftStatusV2Response.draft_outcomePayload
    public let budgetStage: Components.Schemas.RunDraftStatusV2Response.budget_exhausted_stagePayload
    public let reference: MessageEditReference
}

private struct TripDraftProjection: Decodable {
    let request_id,conversation_id,generation,message_id,run_id: String
    let message_sequence,event_highwater: Int
    let run_status: Components.Schemas.RunDraftStatusV2Response.run_statusPayload
    let draft_outcome: Components.Schemas.RunDraftStatusV2Response.draft_outcomePayload
    let budget_exhausted_stage: Components.Schemas.RunDraftStatusV2Response.budget_exhausted_stagePayload
}

func decodeTripDraftStatus(_ bytes: Data, reference: MessageTripReference) throws -> (RunTripDraftStatus, (String,String,String,String,String,Int,Int,String)) {
    let envelope = try RunTripEnvelope(bytes, fields: "request_id version conversation_id generation message_id run_id message_sequence event_highwater run_status draft_outcome budget_exhausted_stage reference", version: "RUN-draft-status.4", reference: reference)
    try envelope.requireIntegers(["message_sequence", "event_highwater"])
    let p = try JSONDecoder().decode(TripDraftProjection.self, from: bytes)
    return (RunTripDraftStatus(runStatus:p.run_status,draftOutcome:p.draft_outcome,budgetStage:p.budget_exhausted_stage,reference:reference),
        (p.request_id,p.conversation_id,p.generation,p.message_id,p.run_id,p.message_sequence,p.event_highwater,p.run_status.rawValue))
}
func decodeEditDraftStatus(_ bytes: Data, reference: MessageEditReference) throws -> (RunEditDraftStatus, (String,String,String,String,String,Int,Int,String)) {
    let envelope = try RunTripEnvelope(bytes, fields: "request_id version conversation_id generation message_id run_id message_sequence event_highwater run_status draft_outcome budget_exhausted_stage reference", version: "RUN-draft-status.5", reference: reference)
    try envelope.requireIntegers(["message_sequence", "event_highwater"])
    let p = try JSONDecoder().decode(TripDraftProjection.self, from: bytes)
    return (RunEditDraftStatus(runStatus:p.run_status,draftOutcome:p.draft_outcome,budgetStage:p.budget_exhausted_stage,reference:reference),
        (p.request_id,p.conversation_id,p.generation,p.message_id,p.run_id,p.message_sequence,p.event_highwater,p.run_status.rawValue))
}
