import Foundation
import CJAPI

private enum InvalidWire: Error { case invalid, expectationFailed }

@main
struct HistoryGeneratedConsumer {
    static func data(_ object:[String:Any]) throws -> Data { try JSONSerialization.data(withJSONObject:object) }
    static func raw(_ encoded:String) throws -> Data {
        guard let bytes=Data(base64Encoded:encoded), bytes.base64EncodedString()==encoded,
              String(data:bytes,encoding:.utf8) != nil else { throw InvalidWire.invalid }
        return bytes
    }
    static func draft(_ object:[String:Any]) throws -> Data? {
        let response=try JSONDecoder().decode(Components.Schemas.MessageDraftReadResponse.self,from:data(object))
        switch response.draft {
        case .MessageDraftSnapshot(let snapshot):return try raw(snapshot.original_utf8_base64)
        case .case2(let container):
            guard container.value == nil else { throw InvalidWire.invalid }
            return nil
        }
    }
    static func missing<T:Decodable>(_ type:T.Type,_ object:[String:Any],_ key:String) throws {
        do {
            _=try JSONDecoder().decode(type,from:data(object))
            throw InvalidWire.invalid
        } catch DecodingError.keyNotFound(let actual,_) {
            guard actual.stringValue==key else { throw InvalidWire.invalid }
        }
    }
    static func main() throws {
        let rid="00000000-0000-4000-8000-000000000001"
        for value in ["opaque-token" as Any,NSNull()] {
            let page=try JSONDecoder().decode(Components.Schemas.ConversationPageResponse.self,
                from:data(["request_id":rid,"conversations":[],"next_cursor":value]))
            switch page.next_cursor {
            case .case1(let token):guard token=="opaque-token" else { throw InvalidWire.invalid }
            case .case2(let container):guard container.value==nil else { throw InvalidWire.invalid }
            }
        }
        try missing(Components.Schemas.ConversationPageResponse.self,["request_id":rid,"conversations":[]],"next_cursor")
        try missing(Components.Schemas.MessageHistoryResponse.self,["request_id":rid,"messages":[]],"next_cursor")
        print("PASS generated list/history next_cursor object-string/null/missing distinctions")
        let original=Data("e\u{301} + 中文\n".utf8)
        let snapshot:[String:Any]=["conversation_id":"c","generation":"g","revision":1,"original_utf8_base64":original.base64EncodedString()]
        guard try draft(["request_id":rid,"draft":snapshot])==original,
              try draft(["request_id":rid,"draft":NSNull()])==nil else { throw InvalidWire.invalid }
        try missing(Components.Schemas.MessageDraftReadResponse.self,["request_id":rid],"draft")
        do {_=try draft(["request_id":rid,"draft":"invalid fallback"]);throw InvalidWire.expectationFailed}
        catch InvalidWire.invalid {}
        print("PASS actual generated draft object/null/missing; nonnull fallback rejected")
        let empty:[String:Any]=["conversation_id":"c","generation":"g","revision":1,"original_utf8_base64":""]
        let saved=try JSONDecoder().decode(Components.Schemas.MessageDraftSaveResponse.self,
                                          from:data(["request_id":rid,"draft":empty]))
        guard try raw(saved.draft.original_utf8_base64).isEmpty else { throw InvalidWire.invalid }
        for bad in ["%%%","Zh==","/w=="] {
            do {_=try raw(bad);throw InvalidWire.expectationFailed}
            catch InvalidWire.invalid {}
        }
        print("PASS exact/empty UTF8 base64, invalid encoding/noncanonical/invalid UTF8 rejected")
        let receipt:[String:Any]=["message_id":"m","conversation_id":"c","generation":"g","sequence":1,"run_id":"r","input_sha256":String(repeating:"a",count:64)]
        let history=try JSONDecoder().decode(Components.Schemas.MessageHistoryResponse.self,
            from:data(["request_id":rid,"messages":[["receipt":receipt,"original_utf8_base64":original.base64EncodedString(),"text":"e\u{301} + 中文\n"]],"next_cursor":NSNull()]))
        guard try raw(history.messages[0].original_utf8_base64)==original else { throw InvalidWire.invalid }
        print("PASS generated private history receipt/raw/text projection readable without byte reconstruction")
    }
}
