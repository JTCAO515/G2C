import Foundation
import Testing
import CJAPI
import CJMessageHTTP
@testable import CJManualPreviewClient

struct NeedsPlanningWireTests {
    func fixture() throws -> [String:Any] {
        let file=Bundle.module.url(forResource:"NEEDS-PLANNING-V1",withExtension:"json",subdirectory:"Fixtures")!
        return try JSONSerialization.jsonObject(with:Data(contentsOf:file)) as! [String:Any]
    }
    func decode(_ value:[String:Any],fixture:[String:Any]) throws -> NeedsPlanningDiscovery {
        let reference=try JSONDecoder().decode(Components.Schemas.MessageTravelReference.self,from:canonical(fixture["reference"]))
        return try .decode(canonical(value),requestID:value["request_id"] as! String,reference:reference,
            needsID:fixture["needs_id"] as? String,needsVersion:(fixture["needs_version"] as! NSNumber).int64Value)
    }
    @Test func source1PlanningIsASeparateNewTripAndOpaqueProposalHash() throws {
        let f=try fixture(),wire=f["discovery"] as! [String:Any]
        let d=try decode(wire,fixture:f),p=try #require(d.candidate)
        #expect(d.state == .published && d.sourceProfile=="TRIP-source-input.1" && d.context==nil)
        #expect(p.content.version.rawValue=="structured.2" && p.content.items.count==2)
        #expect(p.candidateHash != p.content.contentSHA256)
    }
    @Test func source2ContextAndProposedTripAreNotTheSameIdentity() throws {
        let f=try fixture();var wire=f["discovery"] as! [String:Any],d=wire["discovery"] as! [String:Any]
        d["source_profile"]="TRIP-source-input.2"
        d["planning_context"]=["trip_id":"prior-context-trip","version":3,"content_sha256":String(repeating:"a",count:64)]
        wire["discovery"]=d;let decoded=try decode(wire,fixture:f)
        #expect(decoded.context?.tripID=="prior-context-trip" && decoded.context?.version==3)
        #expect(decoded.candidate?.tripID != decoded.context?.tripID)
        d["source_profile"]="TRIP-source-input.1";wire["discovery"]=d
        #expect(throws:(any Error).self) { try decode(wire,fixture:f) }
    }
    @Test func mismatchedOriginalNeedsReferenceUnknownVersionsAndIntegerLexemesRefuse() throws {
        let f=try fixture(),original=f["discovery"] as! [String:Any]
        for kind in 0..<5 {
            var wire=original,d=wire["discovery"] as! [String:Any]
            switch kind {
            case 0: var reference=d["reference"] as! [String:Any];reference["message_id"]="another-original";d["reference"]=reference
            case 1:d["needs_reference"]=["id":"another-needs","expected_version":1]
            case 2:wire["version"]="TRIP-needs-discovery.2"
            case 3:d["source_profile"]="future-source"
            default:var p=d["proposal"] as! [String:Any];p["expected_version"]=true;d["proposal"]=p
            }
            wire["discovery"]=d
            #expect(throws:(any Error).self) { try decode(wire,fixture:f) }
        }
        let raw=String(data:try canonical(original),encoding:.utf8)!
        let floating=raw.replacingOccurrences(of:"\"expected_version\":0",with:"\"expected_version\":0.0")
        #expect(floating != raw)
        let ref=try JSONDecoder().decode(Components.Schemas.MessageTravelReference.self,from:canonical(f["reference"]))
        #expect(throws:(any Error).self) { try NeedsPlanningDiscovery.decode(Data(floating.utf8),requestID:original["request_id"] as! String,reference:ref,needsID:"visit",needsVersion:1) }
    }
    @Test func pendingUnknownAndNoCandidateNeverAcquireAProposal() throws {
        let f=try fixture(),original=f["discovery"] as! [String:Any]
        for (state,run,outcome) in [("pending","running",nil as String?),("unknown","unknown","provider_unknown"),("no_candidate","completed","validation_failed")] {
            var wire=original,d=wire["discovery"] as! [String:Any]
            d["state"]=state;d["run_status"]=run;d["draft_outcome"]=outcome.map { $0 as Any } ?? NSNull()
            for key in ["source_profile","planning_context","proposal"] { d[key]=NSNull() }
            wire["discovery"]=d;#expect(try decode(wire,fixture:f).candidate==nil)
            d["proposal"]=(original["discovery"] as! [String:Any])["proposal"];wire["discovery"]=d
            #expect(throws:(any Error).self) { try decode(wire,fixture:f) }
        }
    }
    @Test func exactNeedsActionReceiptBindsOriginalAndNullIsUnknown() throws {
        let f=try fixture(),candidate=try #require(decode(f["discovery"] as! [String:Any],fixture:f).candidate)
        let action=try NeedsPlanningAction(originalUTF8:canonical(f["action"]))
        let wire=f["receipt"] as! [String:Any],trace=wire["request_id"] as! String
        let optionalReceipt=try NeedsPlanningReceipt.decode(canonical(wire),trace:trace,action:action,candidate:candidate)
        let result=try #require(optionalReceipt)
        #expect(result.kind == .accept && result.committedVersion==1 && result.tripID==candidate.tripID)
        var missing=wire;missing["receipt"]=NSNull()
        #expect(try NeedsPlanningReceipt.decode(canonical(missing),trace:trace,action:action,candidate:candidate)==nil)
        var bad=wire,r=bad["receipt"] as! [String:Any];r["committed_version"]=2;bad["receipt"]=r
        #expect(throws:(any Error).self) { try NeedsPlanningReceipt.decode(canonical(bad),trace:trace,action:action,candidate:candidate) }
        var rejectedAction=f["action"] as! [String:Any];rejectedAction["kind"]="reject"
        let reject=try NeedsPlanningAction(originalUTF8:canonical(rejectedAction))
        r["kind"]="reject";r["committed_version"]=NSNull();bad["receipt"]=r
        let optionalRejection=try NeedsPlanningReceipt.decode(canonical(bad),trace:trace,action:reject,candidate:candidate)
        let rejected=try #require(optionalRejection)
        #expect(rejected.kind == .reject && rejected.committedVersion==nil)
        #expect(throws:(any Error).self) { try NeedsPlanningAction(originalUTF8:Data(" ".utf8)+action.originalUTF8) }
    }
    @Test func persistedOriginalCannotSubstituteCandidateOrOldActionProtocol() throws {
        let f=try fixture(),raw=try canonical(f["discovery"]),action=try NeedsPlanningAction(originalUTF8:canonical(f["action"]))
        let original=NeedsPlanningOriginal(actionID:action.actionID,actionUTF8:action.originalUTF8,discoveryUTF8:raw)
        try original.validate()
        var wrong=f["action"] as! [String:Any];wrong["proposal_id"]="another-candidate"
        #expect(throws:(any Error).self) { try NeedsPlanningOriginal(actionID:action.actionID,actionUTF8:canonical(wrong),discoveryUTF8:raw).validate() }
        wrong["version"]="TRIP-scoped-action.1"
        #expect(throws:(any Error).self) { try NeedsPlanningAction(originalUTF8:canonical(wrong)) }
    }
}
