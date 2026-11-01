import Foundation

public struct NeedsPlanningAction: Sendable {
    public typealias Kind=ScopedAction.Kind
    public let actionID:String
    public let kind:Kind
    public let proposalID:String
    public let candidateHash:String
    public let originalUTF8:Data
    static func stage(kind:Kind,candidate:NeedsPlanningCandidate) throws -> Self {
        try .init(originalUTF8:canonical(["version":"TRIP-needs-action.1","action_id":UUID().uuidString,
            "kind":kind.rawValue,"proposal_id":candidate.proposalID,"candidate_hash":candidate.candidateHash]))
    }
    public init(originalUTF8:Data) throws {
        let json=try ScopedWireJSON(originalUTF8,maximumBytes:32768)
        let f=try ScopedWireJSON.fields(json.object,"version action_id kind proposal_id candidate_hash")
        guard f["version"] as? String == "TRIP-needs-action.1",let kind=Kind(rawValue:try ScopedWireJSON.text(f["kind"])),
              try canonical(f)==originalUTF8 else { throw PreviewFailure.invalidInput }
        actionID=try ScopedWireJSON.identifier(f["action_id"]);proposalID=try ScopedWireJSON.identifier(f["proposal_id"])
        candidateHash=try ScopedWireJSON.hash(f["candidate_hash"]);self.kind=kind;self.originalUTF8=originalUTF8
    }
}
public struct NeedsPlanningReceipt:Sendable {
    public let actionID:String
    public let kind:NeedsPlanningAction.Kind
    public let proposalID:String
    public let candidateHash:String
    public let tripID:String
    public let committedVersion:Int64?
    static func decode(_ bytes:Data,trace:String,action:NeedsPlanningAction,candidate:NeedsPlanningCandidate) throws -> Self? {
        let json=try ScopedWireJSON(bytes,maximumBytes:65536)
        let e=try ScopedWireJSON.fields(json.object,"version request_id receipt")
        guard e["version"] as? String == "TRIP-needs-result.1",e["request_id"] as? String == trace,UUID(uuidString:trace) != nil else { throw PreviewFailure.invalidResponse }
        if e["receipt"] is NSNull { return nil }
        let r=try ScopedWireJSON.fields(e["receipt"],"action_id kind proposal_id candidate_hash trip_id committed_version")
        guard r["action_id"] as? String == action.actionID,r["kind"] as? String == action.kind.rawValue,
              r["proposal_id"] as? String == action.proposalID,r["candidate_hash"] as? String == action.candidateHash,
              r["trip_id"] as? String == candidate.tripID else { throw PreviewFailure.invalidResponse }
        let version:Int64?
        if action.kind == .accept {
            let v=try json.integer(["receipt","committed_version"],minimum:1)
            guard v==1 else { throw PreviewFailure.invalidResponse };version=v
        } else { guard r["committed_version"] is NSNull else { throw PreviewFailure.invalidResponse };version=nil }
        return .init(actionID:action.actionID,kind:action.kind,proposalID:action.proposalID,candidateHash:action.candidateHash,tripID:candidate.tripID,committedVersion:version)
    }
}

struct NeedsPlanningOriginal:ScopedJournalRecord,Sendable {
    let actionID:String
    let actionUTF8:Data
    let discoveryUTF8:Data
    var action:NeedsPlanningAction { get throws { try .init(originalUTF8:actionUTF8) } }
    func discovery() throws -> NeedsPlanningDiscovery {
        let json=try ScopedWireJSON(discoveryUTF8,maximumBytes:4_000_000)
        let d=try ScopedWireJSON.fields(json.object["discovery"],"state reference run_status draft_outcome needs_reference source_profile planning_context proposal")
        let n=try ScopedWireJSON.fields(d["needs_reference"],"id expected_version")
        return try .decode(discoveryUTF8,requestID:ScopedWireJSON.text(json.object["request_id"]),reference:decodePlanningReference(d["reference"]),
            needsID:ScopedWireJSON.text(n["id"]),needsVersion:json.integer(["discovery","needs_reference","expected_version"],minimum:1))
    }
    func validate() throws {
        let a=try action
        guard exact(actionID,a.actionID),let candidate=try discovery().candidate,
              exact(a.proposalID,candidate.proposalID),a.candidateHash==candidate.candidateHash else { throw PreviewFailure.invalidResponse }
    }
}
struct NeedsPlanningSettlement:ScopedJournalRecord,Sendable {
    let actionID:String
    let original:NeedsPlanningOriginal
    let responseUTF8:Data
    let trace:String
    let httpStatus:Int
    func receipt() throws -> NeedsPlanningReceipt {
        guard let candidate=try original.discovery().candidate,
              let result=try NeedsPlanningReceipt.decode(responseUTF8,trace:trace,action:original.action,candidate:candidate) else { throw PreviewFailure.invalidResponse }
        return result
    }
    func validate() throws {
        try original.validate();guard exact(actionID,original.actionID) else { throw PreviewFailure.invalidResponse }
        if httpStatus==200 { _=try receipt() }
        else { try validateScopedRejection(responseUTF8,trace:trace,status:httpStatus) }
    }
}
