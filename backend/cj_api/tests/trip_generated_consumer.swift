import Foundation
import CJAPI

private enum InvalidTripWire: Error { case invalid, unexpectedAcceptance }
@main struct TripGeneratedConsumer {
    static func data(_ object: [String:Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject:object,options:[.sortedKeys,.withoutEscapingSlashes])
    }
    static func receipt(_ object:[String:Any]) throws -> Components.Schemas.TripActionReceipt? {
        let response=try JSONDecoder().decode(Components.Schemas.TripActionQueryResponse.self,from:data(object))
        switch response.receipt {
        case .TripActionReceipt(let value):
            switch value.committed_version {
            case .case1(let version):guard value.kind == .accept,version>0 else { throw InvalidTripWire.invalid }
            case .case2(let container):guard container.value == nil,value.kind == .reject else { throw InvalidTripWire.invalid }
            }
            return value
        case .case2(let container):
            guard container.value == nil else { throw InvalidTripWire.invalid }
            return nil
        }
    }
    static func main() throws {
        let rid="00000000-0000-4000-8000-000000000001"
        let hash=String(repeating:"a",count:64)
        let accepted:[String:Any]=["action_id":"a1","kind":"accept","proposal_id":"p1","candidate_hash":hash,"trip_id":"t1","committed_version":1]
        guard try receipt(["request_id":rid,"receipt":accepted])?.action_id == "a1",
              try receipt(["request_id":rid,"receipt":NSNull()]) == nil else { throw InvalidTripWire.invalid }
        var rejected=accepted;rejected["kind"]="reject";rejected["committed_version"]=NSNull()
        guard try receipt(["request_id":rid,"receipt":rejected])?.kind == .reject else { throw InvalidTripWire.invalid }
        for bad in ["invalid" as Any, ["kind":"future"] as Any] {
            do { _=try receipt(["request_id":rid,"receipt":bad]);throw InvalidTripWire.unexpectedAcceptance }
            catch InvalidTripWire.invalid { }
        }
        do {
            _=try JSONDecoder().decode(Components.Schemas.TripActionQueryResponse.self,from:data(["request_id":rid]))
            throw InvalidTripWire.invalid
        } catch DecodingError.keyNotFound(let key,_) {
            guard key.stringValue=="receipt" else { throw InvalidTripWire.invalid }
        }
        print("PASS generated Trip historical accept/version, reject/null, absent receipt, missing/future invalid fallback")
        let content:[String:Any]=["title":"Synthetic e\u{301} 中文","items":[["id":"item-1","text":"Synthetic pending","verification":"pending","evidence":[]]]]
        let original=try data(content)
        let record:[String:Any]=["trip_id":"t1","version":1,"content_utf8_base64":original.base64EncodedString(),"document":content]
        let page=try JSONDecoder().decode(Components.Schemas.TripListResponse.self,
            from:data(["request_id":rid,"trips":[record],"next_after":"t1"]))
        guard page.trips.count==1,Data(base64Encoded:page.trips[0].content_utf8_base64)==original,
              page.trips[0].document.items[0].verification == .pending else { throw InvalidTripWire.invalid }
        print("PASS generated formal Trip exact UTF8 content and accepted pending evidence state")
        let snapshot:[String:Any]=["proposal_id":"p1","trip_id":"t1","expected_version":0,"basis_version":"basis1",
            "expires_at":1,"content_utf8_base64":original.base64EncodedString(),"document":content,
            "candidate_hash":hash,"status":"pending"]
        let proposal=try JSONDecoder().decode(Components.Schemas.TripProposalResponse.self,
            from:data(["request_id":rid,"proposal":snapshot])).proposal
        guard proposal.status == .pending,proposal.expires_at == 1,proposal.expected_version == 0,
              proposal.candidate_hash == hash,Data(base64Encoded:proposal.content_utf8_base64)==original else { throw InvalidTripWire.invalid }
        print("PASS generated public candidate snapshot keeps digest, elapsed pending and exact source content")
        let canonicalAction=try JSONSerialization.data(withJSONObject:["a1","accept","p1",hash,"c1"],options:[.withoutEscapingSlashes])
        guard canonicalAction==Data("[\"a1\",\"accept\",\"p1\",\"\(hash)\",\"c1\"]".utf8) else { throw InvalidTripWire.invalid }
        print("PASS Swift exact canonical five-string Action UTF8 representation")
    }
}
