import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes
private enum Failed:Error { case check,unexpectedAcceptance }
private struct FixtureTransport:ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        let receipt:[String:Any]=["action_id":"a1","input_sha256":String(repeating:"a",count:64),"submitted_at":"2026-10-22T01:02:03.123456Z","status":"submitted","message_en":"Feedback submitted.","message_zh":"反馈已提交。","source":NSNull()]
        let value:[String:Any]=["request_id":"00000000-0000-4000-8000-000000000001","receipt":receipt]
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[.init("X-Request-ID")!]="00000000-0000-4000-8000-000000000001"
        return(response,HTTPBody(try JSONSerialization.data(withJSONObject:value)))
    }
}
@main struct FeedbackGeneratedConsumer {
    static func main() async throws {
        guard let url=URL(string:"https://fixture.invalid") else { throw Failed.check }
        let client=Client(serverURL:url,configuration:.memory,transport:FixtureTransport())
        let q=try await client.queryFeedbackAction(.init(query:.init(action_id:"a1"))).ok.body.json
        guard case .FeedbackReceipt(let receipt)=q.receipt,receipt.status == .submitted,
              case .case2(let none)=receipt.source,none.value==nil else { throw Failed.check }
        let rid="00000000-0000-4000-8000-000000000001"
        let missing=try JSONSerialization.data(withJSONObject:["request_id":rid])
        do{_=try JSONDecoder().decode(Components.Schemas.FeedbackQueryResponse.self,from:missing);throw Failed.unexpectedAcceptance}
        catch DecodingError.keyNotFound(let key,_){guard key.stringValue=="receipt" else { throw Failed.check }}
        let invalid=try JSONSerialization.data(withJSONObject:["request_id":rid,"receipt":"invalid"])
        let invalidReceipt=try JSONDecoder().decode(Components.Schemas.FeedbackQueryResponse.self,from:invalid)
        guard case .case2(let container)=invalidReceipt.receipt,container.value != nil else { throw Failed.check }
        print("PASS generated FEEDBACK UTC date via existing configuration, submitted-only receipt, required source/null/missing and invalid fallback")
    }
}
