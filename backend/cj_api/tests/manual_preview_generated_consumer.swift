import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes
private enum Failed:Error { case check }
private struct FixtureTransport:ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        guard operationID=="previewManualTripEdit",request.method == .post,request.path=="/v1/trip-manual-previews",let body else { throw Failed.check }
        let raw=try await Data(collecting:body,upTo:65536)
        let decoded=try JSONDecoder().decode(Components.Schemas.ManualPreviewRequest.self,from:raw)
        guard decoded.selected_ids.isEmpty,!decoded.title_selected,
              case .case2(let title)=decoded.title,title.value==nil,
              case .case2(let order)=decoded.order,order.value==nil else { throw Failed.check }
        let item:[String:Any]=["id":"a","text":"Synthetic","verification":"pending","evidence":[]]
        let doc:[String:Any]=["title":"Synthetic","items":[item]]
        let p:[String:Any]=["preview_status":"LOCAL","original":["trip_id":"t1","version":1,"content_utf8_base64":decoded.original_content_utf8_base64,"document":doc],"content_utf8_base64":decoded.original_content_utf8_base64,"document":doc,"selected_ids":[],"title_selected":false,"protection_status":"UNKNOWN","can_save":false,"diff":[]]
        let data:[String:Any]=["request_id":"00000000-0000-4000-8000-000000000001","preview":p]
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[.init("X-Request-ID")!]="00000000-0000-4000-8000-000000000001"
        return(response,HTTPBody(try JSONSerialization.data(withJSONObject:data)))
    }
}
@main struct ManualPreviewGeneratedConsumer {
    static func main() async throws {
        let original=Data(#"{"items":[{"evidence":[],"id":"a","text":"Synthetic","verification":"pending"}],"title":"Synthetic"}"#.utf8)
        let fields:[String:Any]=["trip_id":"t1","expected_version":1,"original_content_utf8_base64":original.base64EncodedString(),"selected_ids":[],"title_selected":false,"title":NSNull(),"text_updates":[],"order":NSNull()]
        let request=try JSONDecoder().decode(Components.Schemas.ManualPreviewRequest.self,from:JSONSerialization.data(withJSONObject:fields))
        guard let url=URL(string:"https://fixture.invalid") else { throw Failed.check }
        let client=Client(serverURL:url,configuration:.memory,transport:FixtureTransport())
        let result=try await client.previewManualTripEdit(.init(body:.json(request))).ok.body.json
        guard result.preview.preview_status == .LOCAL,result.preview.protection_status == .UNKNOWN,!result.preview.can_save,result.preview.diff.isEmpty else { throw Failed.check }
        print("PASS official manual preview JSON operation, explicit nullable selections and no-save/unknown-protection decoding")
    }
}
