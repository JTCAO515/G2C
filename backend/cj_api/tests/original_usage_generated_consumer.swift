import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes
private enum Failed:Error { case check,unexpected }
private struct FixtureTransport:ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        guard operationID=="getOriginalUsageAssociation",request.path=="/v1/message-usage-association?message_id=m%2B1" else { throw Failed.check }
        let value:[String:Any]=["request_id":"00000000-0000-4000-8000-000000000001","association":["conversation_id":"c","generation":"g","message_id":"m+1","message_sequence":1,"run_id":"r","attempt_id":"stored-attempt","operation_id":"stored-operation"]]
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[.init("X-Request-ID")!]="00000000-0000-4000-8000-000000000001"
        return(response,HTTPBody(try JSONSerialization.data(withJSONObject:value)))
    }
}
@main struct OriginalUsageGeneratedConsumer {
    static func main() async throws {
        guard let url=URL(string:"https://fixture.invalid") else { throw Failed.check }
        let client=Client(serverURL:url,configuration:.memory,transport:FixtureTransport())
        let r=try await client.getOriginalUsageAssociation(.init(query:.init(message_id:"m+1"))).ok;let body=try r.body.json
        guard body.request_id==r.headers.X_hyphen_Request_hyphen_ID,body.association.attempt_id=="stored-attempt",
              body.association.operation_id=="stored-operation",body.association.message_sequence==1 else { throw Failed.check }
        for data:[String:Any] in [["request_id":body.request_id],["request_id":body.request_id,"association":NSNull()]] {
            do{_=try JSONDecoder().decode(Components.Schemas.OriginalUsageAssociationResponse.self,from:JSONSerialization.data(withJSONObject:data));throw Failed.unexpected}
            catch is DecodingError { }
        }
        print("PASS generated original association GET/opaque query, exact seven refs/header trace and no nullable fake association")
    }
}
