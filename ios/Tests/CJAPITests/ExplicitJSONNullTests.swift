import Foundation
import Testing
import CJAPI

struct ExplicitJSONNullTests {
    let trace="6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    @Test func nullCodecRejectsEveryNonNullJSONType() throws {
        let value=try JSONDecoder().decode(ExplicitJSONNull.self,from:Data("null".utf8))
        #expect(try JSONEncoder().encode(value)==Data("null".utf8))
        for input in ["true","false","0","1.0","\"null\"","{}","[]"] {
            #expect(throws:(any Error).self) { try JSONDecoder().decode(ExplicitJSONNull.self,from:Data(input.utf8)) }
        }
    }
    @Test func requiredNullsInTypedStatusSurviveDecodeAndEncode() throws {
        let raw=Data("{\"version\":\"MESSAGE-send-status.2\",\"request_id\":\"\(trace)\",\"receipt\":null,\"head\":null,\"reference\":null}".utf8)
        let decoded=try JSONDecoder().decode(Components.Schemas.MessageSendStatusV2Response.self,from:raw)
        guard case .CJExplicitJSONNull=decoded.receipt,case .CJExplicitJSONNull=decoded.head,case .CJExplicitJSONNull=decoded.reference else { Issue.record("lost explicit null");return }
        let object=try JSONSerialization.jsonObject(with:JSONEncoder().encode(decoded)) as! [String:Any]
        #expect(Set(object.keys)==["version","request_id","receipt","head","reference"])
        #expect(object["receipt"] is NSNull);#expect(object["head"] is NSNull);#expect(object["reference"] is NSNull)
        for key in ["receipt","head","reference"] {
            var missing=object;missing.removeValue(forKey:key)
            let bytes=try JSONSerialization.data(withJSONObject:missing)
            #expect(throws:(any Error).self) { try JSONDecoder().decode(Components.Schemas.MessageSendStatusV2Response.self,from:bytes) }
        }
    }
    @Test func malformedNullableStatusObjectsCannotFallThroughToAnyValue() throws {
        for field in ["receipt","head","reference"] {
            for invalid:Any in [true,7,"null",[String:Any](),[Any]()] {
                var object:[String:Any]=["version":"MESSAGE-send-status.2","request_id":trace,"receipt":NSNull(),"head":NSNull(),"reference":NSNull()]
                object[field]=invalid
                let bytes=try JSONSerialization.data(withJSONObject:object)
                #expect(throws:(any Error).self) { try JSONDecoder().decode(Components.Schemas.MessageSendStatusV2Response.self,from:bytes) }
            }
        }
    }
    @Test func noneReferenceKeepsItsRequiredNullFieldsClosed() throws {
        let object:[String:Any]=["version":"MESSAGE-travel-reference.1","message_version":"MESSAGE-send.2","conversation_id":"chat","generation":"g1","message_id":"m1","run_id":"r1","sequence":1,"input_sha256":String(repeating:"a",count:64),"context_kind":"none","context_id":NSNull(),"context_version":NSNull(),"selection_epoch":1]
        let bytes=try JSONSerialization.data(withJSONObject:object)
        let value=try JSONDecoder().decode(Components.Schemas.MessageTravelReferenceNone.self,from:bytes)
        let encoded=try JSONSerialization.jsonObject(with:JSONEncoder().encode(value)) as! [String:Any]
        #expect(encoded["context_id"] is NSNull);#expect(encoded["context_version"] is NSNull)
        for field in ["context_id","context_version"] {
            var changed=object;changed[field]="not-null"
            let invalid=try JSONSerialization.data(withJSONObject:changed)
            #expect(throws:(any Error).self) { try JSONDecoder().decode(Components.Schemas.MessageTravelReferenceNone.self,from:invalid) }
        }
    }
}
