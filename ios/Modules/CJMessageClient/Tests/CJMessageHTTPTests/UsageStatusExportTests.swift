import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime

private struct UsageExportNoRequest: ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        Issue.record("USAGE export codec tests must not issue requests")
        throw URLError(.unsupportedURL)
    }
}
struct UsageStatusExportTests {
    let trace="beca070b-684f-48c7-af4b-53967d9f52c5"
    private func object(status:String="unknown",confirmed:Any=NSNull())->[String:Any] {
        ["request_id":trace,"attempt":["attempt_id":"synthetic-attempt","operation_id":"synthetic-operation","run_id":"synthetic-run","status":status,"unit":"opaque-test-unit","reserved_units":"999999999999999999999999999999999999999999999999999999","confirmed_units":confirmed,"confirmed_output":confirmed,"receipt_id":NSNull(),"cancelled":false,"exceeded":false,"message_en":"Synthetic status","message_zh":"合成状态"]]
    }
    private func decode(_ value:[String:Any]) throws -> Components.Schemas.UsageAttemptStatusResponse {
        try JSONDecoder().decode(Components.Schemas.UsageAttemptStatusResponse.self,from:JSONSerialization.data(withJSONObject:value))
    }
    @Test func actualOfficialUsageGETCompilesWithoutRequest() throws {
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:UsageExportNoRequest())
        _ = client.getUsageAttemptStatus
        _ = Operations.getUsageAttemptStatus.Input.Query(attempt_id:"synthetic-original-attempt")
        #expect(Operations.getUsageAttemptStatus.id=="getUsageAttemptStatus")
    }
    @Test func hugeCountsStayStringsAndUnknownIsNotConfirmedZero() throws {
        for status in ["reserved","unknown","released","settled"] {
            let value=try decode(object(status:status))
            #expect(value.attempt.status.rawValue==status)
            #expect(value.attempt.reserved_units=="999999999999999999999999999999999999999999999999999999")
            if case .case2(let v)=value.attempt.confirmed_units {#expect(v.value==nil)} else {Issue.record("unknown confirmed count must remain null")}
        }
        let zero=try decode(object(status:"settled",confirmed:"0"))
        if case .case1(let v)=zero.attempt.confirmed_units {#expect(v=="0")} else {Issue.record("actual zero must remain a string, not null")}
    }
    @Test func missingAttemptMissingConfirmedAndInvalidFallbackAreExplicit() throws {
        #expect(throws:DecodingError.self) {try decode(["request_id":trace])}
        #expect(throws:DecodingError.self) {try decode(["request_id":trace,"attempt":NSNull()])}
        var missing=object();var attempt=missing["attempt"] as! [String:Any];attempt.removeValue(forKey:"confirmed_units");missing["attempt"]=attempt
        #expect(throws:DecodingError.self) {try decode(missing)}
        #expect(throws:DecodingError.self) {try decode(object(status:"invented"))}
        let fallback=try decode(object(confirmed:false))
        if case .case2(let v)=fallback.attempt.confirmed_units {#expect(v.value != nil)} else {Issue.record("non-null fallback cannot represent unknown")}
    }
}
