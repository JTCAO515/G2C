import Foundation
import CJAPI
private enum Failed:Error { case check,unexpectedAcceptance }
@main struct NeedsGeneratedConsumer {
    static func data(_ value:[String:Any]) throws -> Data { try JSONSerialization.data(withJSONObject:value) }
    static func main() throws {
        let rid="00000000-0000-4000-8000-000000000001"
        let fields:[String:Any]=["party_size":["state":"known","value":3],"budget_total":["state":"unknown"],"budget_paid":["state":"missing"],"pace":["state":"uncertain","note":"Undecided / 未定"]]
        let raw=try data(fields)
        let snapshot:[String:Any]=["needs_id":"n1","version":1,"source_kind":"user_provided","content_utf8_base64":raw.base64EncodedString(),"fields":fields]
        let body=try JSONDecoder().decode(Components.Schemas.NeedsDetailResponse.self,from:data(["request_id":rid,"needs":snapshot]))
        guard case .NeedsSnapshot(let value)=body.needs,value.fields.arrival==nil,value.fields.budget_currency==nil,
              case .NeedsPartySizeObservationKnown(let party)?=value.fields.party_size,party.value==3,
              case .NeedsUnknownObservation?=value.fields.budget_total,
              case .NeedsMissingObservation?=value.fields.budget_paid,
              case .NeedsUncertainObservation(let note)?=value.fields.pace,note.note=="Undecided / 未定" else { throw Failed.check }
        let absent=try JSONDecoder().decode(Components.Schemas.NeedsDetailResponse.self,from:data(["request_id":rid,"needs":NSNull()]))
        guard case .case2(let null)=absent.needs,null.value==nil else { throw Failed.check }
        do { _=try JSONDecoder().decode(Components.Schemas.NeedsDetailResponse.self,from:data(["request_id":rid]));throw Failed.unexpectedAcceptance }
        catch DecodingError.keyNotFound(let key,_) { guard key.stringValue=="needs" else { throw Failed.check } }
        let invalid=try JSONDecoder().decode(Components.Schemas.NeedsDetailResponse.self,from:data(["request_id":rid,"needs":"malformed"]));
        guard case .case2(let notNull)=invalid.needs,notNull.value != nil else { throw Failed.check }
        print("PASS generated NEEDS four observation states, omitted fields, required null/missing and nonnull invalid fallback")
    }
}
