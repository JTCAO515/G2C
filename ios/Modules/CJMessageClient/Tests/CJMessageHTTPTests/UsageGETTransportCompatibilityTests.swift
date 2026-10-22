import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor UsageGETCompatibilityIntercept: ClientTransport {
    var paths:[String?]=[]
    let attempt:String
    init(attempt:String) {self.attempt=attempt}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        #expect(request.method == .get && operationID == Operations.getUsageAttemptStatus.id)
        #expect(body == nil)
        paths.append(request.path)
        let trace="0237bca3-5300-41e7-9945-a46c2b774725"
        let attempt:[String:Any]=["attempt_id":attempt,"operation_id":"synthetic-op","run_id":"synthetic-run","status":"unknown","unit":"opaque","reserved_units":"999999999999999999999999999999","confirmed_units":NSNull(),"confirmed_output":NSNull(),"receipt_id":NSNull(),"cancelled":false,"exceeded":false,"message_en":"Synthetic","message_zh":"合成"]
        let payload=try JSONSerialization.data(withJSONObject:["request_id":trace,"attempt":attempt])
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[HTTPField.Name("X-Request-ID")!]=trace
        return(response,HTTPBody(payload))
    }
}
struct UsageGETTransportCompatibilityTests {
    @Test func official9dUsageGETStillPassesRepairedDefaultReadTransport() async throws {
        let id="synthetic/+%e\u{301}"
        let intercepted=UsageGETCompatibilityIntercept(attempt:id)
        let transport=try NoRedirectTransport(interceptedTransport:intercepted,previewEndpoint:nil,validatePreview:nil)
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:transport)
        let output=try await client.getUsageAttemptStatus(.init(query:.init(attempt_id:id)))
        let body=try output.ok.body.json
        #expect(Data(body.attempt.attempt_id.utf8)==Data(id.utf8) && body.attempt.status == .unknown)
        #expect(body.attempt.reserved_units=="999999999999999999999999999999")
        if case .case2(let value)=body.attempt.confirmed_units {#expect(value.value==nil)} else {Issue.record("unknown is not confirmed zero")}
        let paths=await intercepted.paths;#expect(paths.count==1)
        let path=try #require(paths.first ?? nil)
        let query=try #require(URLComponents(string:"https://synthetic.invalid"+path)?.queryItems)
        #expect(query.count==1 && query[0].name=="attempt_id")
        #expect(Data((query[0].value ?? "").utf8)==Data(id.utf8))
    }
}
