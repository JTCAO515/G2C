import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime

private struct FeedbackExportOnlyTransport: ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        Issue.record("Feedback export checks must not issue requests")
        throw URLError(.unsupportedURL)
    }
}
struct FeedbackConfigurationExportTests {
    let trace="c1da891d-969d-4665-86a8-20525ece0205"
    private func decoder() -> JSONDecoder {
        let value=JSONDecoder()
        value.dateDecodingStrategy = .custom { decoder in
            try Configuration.memory.dateTranscoder.decode(decoder.singleValueContainer().decode(String.self))
        }
        return value
    }
    @Test func fixedOfficialFeedbackMethodsCompileWithoutRequests() throws {
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:FeedbackExportOnlyTransport())
        _ = client.submitFeedback; _ = client.queryFeedbackAction
        #expect(Operations.submitFeedback.id=="submitFeedback")
        #expect(Operations.queryFeedbackAction.id=="queryFeedbackAction")
    }
    @Test func receiptNullMissingAndFallbackRemainDistinct() throws {
        let null=try decoder().decode(Components.Schemas.FeedbackQueryResponse.self,from:Data("{\"request_id\":\"\(trace)\",\"receipt\":null}".utf8))
        if case .case2(let value)=null.receipt {#expect(value.value==nil)} else {Issue.record("explicit null expected")}
        #expect(throws:DecodingError.self) {try decoder().decode(Components.Schemas.FeedbackQueryResponse.self,from:Data("{\"request_id\":\"\(trace)\"}".utf8))}
        let bad=try decoder().decode(Components.Schemas.FeedbackQueryResponse.self,from:Data("{\"request_id\":\"\(trace)\",\"receipt\":false}".utf8))
        if case .case2(let value)=bad.receipt {#expect(value.value != nil)} else {Issue.record("false must not become receipt/null")}
    }
    @Test func officialReceiptUTCTimestampsUseUnchangedDateHelper() throws {
        var dates:[Date]=[]
        for time in ["2026-10-22T08:09:10Z","2026-10-22T08:09:10.123Z"] {
            let bytes=try JSONSerialization.data(withJSONObject:["request_id":trace,"receipt":[
                "action_id":"synthetic_feedback","input_sha256":String(repeating:"0",count:64),
                "submitted_at":time,"status":"submitted","message_en":"Feedback submitted.","message_zh":"反馈已提交。","source":NSNull()]])
            let result=try decoder().decode(Components.Schemas.FeedbackSubmitResponse.self,from:bytes)
            #expect(result.receipt.status == .submitted)
            if case .case2(let value)=result.receipt.source {#expect(value.value==nil)} else {Issue.record("general feedback has explicit null source")}
            dates.append(result.receipt.submitted_at)
        }
        #expect(abs(dates[1].timeIntervalSince(dates[0])-0.123)<0.0001)
    }
}
