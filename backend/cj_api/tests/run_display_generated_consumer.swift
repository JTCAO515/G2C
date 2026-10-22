import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes
private enum Failed:Error { case check,unexpectedAcceptance }
private struct FixtureTransport:ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        guard operationID=="getRunDisplaySnapshot",request.path=="/v1/run-display?message_id=m%2B1" else { throw Failed.check }
        let data:[String:Any]=["request_id":"00000000-0000-4000-8000-000000000001","snapshot":["conversation_id":"c","generation":"g","message_id":"m+1","run_id":"r","message_sequence":1,"status":"failed","event_highwater":2,"text":"partial e\u{301} 中文","text_state":"partial"]]
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[.init("X-Request-ID")!]="00000000-0000-4000-8000-000000000001"
        return(response,HTTPBody(try JSONSerialization.data(withJSONObject:data)))
    }
}
@main struct RunDisplayGeneratedConsumer {
    static func main() async throws {
        guard let url=URL(string:"https://fixture.invalid") else { throw Failed.check }
        let client=Client(serverURL:url,configuration:.memory,transport:FixtureTransport())
        let r=try await client.getRunDisplaySnapshot(.init(query:.init(message_id:"m+1"))).ok
        let body=try r.body.json
        guard body.request_id==r.headers.X_hyphen_Request_hyphen_ID,body.snapshot.status == .failed,
              body.snapshot.text_state == .partial,Data(body.snapshot.text.utf8)==Data("partial e\u{301} 中文".utf8) else { throw Failed.check }
        for value:[String:Any] in [["request_id":body.request_id],["request_id":body.request_id,"snapshot":NSNull()]] {
            do { _=try JSONDecoder().decode(Components.Schemas.RunDisplayResponse.self,from:JSONSerialization.data(withJSONObject:value));throw Failed.unexpectedAcceptance }
            catch is DecodingError { }
        }
        print("PASS generated RUN display operation/opaque query, partial failure text, mandatory snapshot and trace")
    }
}
