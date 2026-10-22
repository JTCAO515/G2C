import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes
private enum Failed:Error { case check,unexpected }
private struct FixtureTransport:ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        guard operationID=="getUsageAttemptStatus",request.path=="/v1/usage-attempt-status?attempt_id=a%2B1" else { throw Failed.check }
        let a:[String:Any]=["attempt_id":"a+1","operation_id":"op","run_id":"run","status":"unknown","unit":"opaque-unit","reserved_units":"184467440737095516160","confirmed_units":NSNull(),"confirmed_output":NSNull(),"receipt_id":NSNull(),"cancelled":false,"exceeded":false,"message_en":"Unknown","message_zh":"待核对"]
        let data:[String:Any]=["request_id":"00000000-0000-4000-8000-000000000001","attempt":a]
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[.init("X-Request-ID")!]="00000000-0000-4000-8000-000000000001"
        return(response,HTTPBody(try JSONSerialization.data(withJSONObject:data)))
    }
}
@main struct UsageStatusGeneratedConsumer {
    static func main() async throws {
        guard let url=URL(string:"https://fixture.invalid") else { throw Failed.check }
        let client=Client(serverURL:url,configuration:.memory,transport:FixtureTransport())
        let r=try await client.getUsageAttemptStatus(.init(query:.init(attempt_id:"a+1"))).ok;let body=try r.body.json
        guard body.request_id==r.headers.X_hyphen_Request_hyphen_ID,body.attempt.reserved_units=="184467440737095516160",
              case .case2(let nilAmount)=body.attempt.confirmed_units,nilAmount.value==nil else { throw Failed.check }
        let malformed=Data(#"{"request_id":"00000000-0000-4000-8000-000000000001"}"#.utf8)
        do{_=try JSONDecoder().decode(Components.Schemas.UsageAttemptStatusResponse.self,from:malformed);throw Failed.unexpected}
        catch DecodingError.keyNotFound(let key,_){guard key.stringValue=="attempt" else{throw Failed.check}}
        print("PASS generated usage readonly operation/opaque query, mandatory original status and lossless integer strings/null")
    }
}
