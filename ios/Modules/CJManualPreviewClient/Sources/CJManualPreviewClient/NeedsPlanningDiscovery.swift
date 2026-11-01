import Foundation
import CJAPI
import CJMessageHTTP
import CJTripClient

public struct NeedsPlanningContext: Sendable {
    public let tripID: String
    public let version: Int64
    public let contentSHA256: String
}
public struct NeedsPlanningCandidate: Sendable {
    public let proposalID: String
    public let tripID: String
    public let candidateHash: String
    public let status: String
    public let expiresAt: Int64
    public let content: StructuredTripDocument
    public let discoveryUTF8: Data
}
public struct NeedsPlanningDiscovery: Sendable {
    public let state: ScopedDiscoveryState
    public let reference: Components.Schemas.MessageTravelReference
    public let needsID: String?
    public let needsVersion: Int64?
    public let runStatus: String
    public let draftOutcome: String?
    public let sourceProfile: String?
    public let context: NeedsPlanningContext?
    public let candidate: NeedsPlanningCandidate?
    public let responseUTF8: Data

    public static func decode(_ bytes:Data,requestID:String,reference original:Components.Schemas.MessageTravelReference,
                              needsID:String?,needsVersion:Int64?) throws -> Self {
        let json=try ScopedWireJSON(bytes,maximumBytes:4_000_000)
        let envelope=try ScopedWireJSON.fields(json.object,"version request_id discovery")
        guard envelope["version"] as? String == "TRIP-needs-discovery.1",envelope["request_id"] as? String == requestID,
              UUID(uuidString:requestID) != nil else { throw PreviewFailure.invalidResponse }
        let d=try ScopedWireJSON.fields(envelope["discovery"],"state reference run_status draft_outcome needs_reference source_profile planning_context proposal")
        guard let state=ScopedDiscoveryState(rawValue:try ScopedWireJSON.text(d["state"])) else { throw PreviewFailure.invalidResponse }
        let reference=try decodePlanningReference(d["reference"])
        guard try planningReferenceBytes(reference)==planningReferenceBytes(original) else { throw PreviewFailure.invalidResponse }
        _=try json.integer(["discovery","reference","sequence"],minimum:1)
        _=try json.integer(["discovery","reference","selection_epoch"],minimum:1)
        if case .travel=reference { _=try json.integer(["discovery","reference","context_version"],minimum:1) }
        if let needsID,let needsVersion {
            let needs=try ScopedWireJSON.fields(d["needs_reference"],"id expected_version")
            guard needs["id"] as? String == needsID,try json.integer(["discovery","needs_reference","expected_version"],minimum:1)==needsVersion else { throw PreviewFailure.invalidResponse }
        } else { guard needsID == nil,needsVersion == nil,d["needs_reference"] is NSNull else { throw PreviewFailure.invalidResponse } }
        let run=try ScopedWireJSON.text(d["run_status"])
        guard ["queued","running","completed","unknown","failed","cancelled","context_invalid"].contains(run) else { throw PreviewFailure.invalidResponse }
        let outcome:String?
        if d["draft_outcome"] is NSNull { outcome=nil }
        else {
            let value=try ScopedWireJSON.text(d["draft_outcome"])
            guard ["validation_failed","provider_failed","budget_exhausted","provider_unknown"].contains(value) else { throw PreviewFailure.invalidResponse }
            outcome=value
        }
        let profile:String?,context:NeedsPlanningContext?,candidate:NeedsPlanningCandidate?
        if state == .published {
            guard run=="completed",outcome==nil,needsID != nil else { throw PreviewFailure.invalidResponse }
            let source=try ScopedWireJSON.text(d["source_profile"])
            guard ["TRIP-source-input.1","TRIP-source-input.2"].contains(source) else { throw PreviewFailure.invalidResponse }
            profile=source
            if d["planning_context"] is NSNull { context=nil }
            else {
                guard source=="TRIP-source-input.2" else { throw PreviewFailure.invalidResponse }
                let c=try ScopedWireJSON.fields(d["planning_context"],"trip_id version content_sha256")
                context=try .init(tripID:ScopedWireJSON.identifier(c["trip_id"]),version:json.integer(["discovery","planning_context","version"],minimum:1),contentSHA256:ScopedWireJSON.hash(c["content_sha256"]))
            }
            let p=try ScopedWireJSON.fields(d["proposal"],"proposal_id trip_id expected_version candidate_hash status expires_at content")
            guard try json.integer(["discovery","proposal","expected_version"],minimum:0)==0 else { throw PreviewFailure.invalidResponse }
            let status=try ScopedWireJSON.text(p["status"])
            guard ["pending","accepted","rejected","expired"].contains(status) else { throw PreviewFailure.invalidResponse }
            let document=try StructuredTripDocument.decode(canonical(p["content"]))
            guard document.version == .needsBound else { throw PreviewFailure.invalidResponse }
            candidate=try .init(proposalID:ScopedWireJSON.identifier(p["proposal_id"]),tripID:ScopedWireJSON.identifier(p["trip_id"]),
                candidateHash:ScopedWireJSON.hash(p["candidate_hash"]),status:status,expiresAt:json.integer(["discovery","proposal","expires_at"],minimum:1),content:document,discoveryUTF8:bytes)
        } else {
            guard d["source_profile"] is NSNull,d["planning_context"] is NSNull,d["proposal"] is NSNull else { throw PreviewFailure.invalidResponse }
            switch state {
            case .notRequested:guard needsID==nil,outcome==nil else { throw PreviewFailure.invalidResponse }
            case .pending:guard needsID != nil,["queued","running"].contains(run),outcome==nil else { throw PreviewFailure.invalidResponse }
            case .noCandidate:guard run=="completed",["validation_failed","provider_failed","budget_exhausted"].contains(outcome) else { throw PreviewFailure.invalidResponse }
            case .unknown:guard run=="unknown" || outcome=="provider_unknown" else { throw PreviewFailure.invalidResponse }
            case .unavailable:guard ["failed","cancelled","context_invalid"].contains(run) else { throw PreviewFailure.invalidResponse }
            case .published:preconditionFailure("handled above")
            }
            profile=nil;context=nil;candidate=nil
        }
        return .init(state:state,reference:reference,needsID:needsID,needsVersion:needsVersion,runStatus:run,draftOutcome:outcome,sourceProfile:profile,context:context,candidate:candidate,responseUTF8:bytes)
    }
}

func planningReferenceBytes(_ reference:Components.Schemas.MessageTravelReference) throws -> Data {
    let encoder=JSONEncoder();encoder.outputFormatting=[.sortedKeys,.withoutEscapingSlashes]
    return try encoder.encode(reference)
}
func decodePlanningReference(_ value:Any?) throws -> Components.Schemas.MessageTravelReference {
    _=try ScopedWireJSON.fields(value,"version conversation_id generation message_id run_id sequence input_sha256 message_version context_kind context_id context_version selection_epoch")
    return try JSONDecoder().decode(Components.Schemas.MessageTravelReference.self,from:canonical(value))
}
