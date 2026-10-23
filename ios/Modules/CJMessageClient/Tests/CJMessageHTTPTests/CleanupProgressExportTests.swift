import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor CleanupProgressIntercept: ClientTransport {
    let bytes:Data;let status:Int;let trace:String
    var paths:[String?]=[]
    init(bytes:Data,status:Int=200,trace:String) {self.bytes=bytes;self.status=status;self.trace=trace}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        #expect(request.method == .get && body == nil && operationID==Operations.getCurrentAccountCleanupProgress.id)
        paths.append(request.path)
        var response=HTTPResponse(status:.init(code:status));response.headerFields[.contentType]="application/json";response.headerFields[HTTPField.Name("X-Request-ID")!]=trace
        return(response,HTTPBody(bytes))
    }
}
struct CleanupProgressExportTests {
    let trace="8034ba59-3bc2-482f-be04-23bf1f1bb823"
    let originalOperation="synthetic/original-op"
    private func object(status:String="blocked")->[String:Any] {
        let unknown=status=="unknown"
        return ["request_id":trace,"progress":["operation_id":originalOperation,"revision":0,"status":status,
          "steps":[["target":"synthetic:message","state":unknown ? "unknown":"pending","reason":unknown ? "original_result_unknown":"hook_unavailable"]],
          "reasons":unknown ? ["original_result_unknown"]:["coverage_incomplete","hook_unavailable"]]]
    }
    @Test func officialCurrentAccountGETKeepsOriginalOperationAndBlockedState() async throws {
        let wire=CleanupProgressIntercept(bytes:try JSONSerialization.data(withJSONObject:object()),trace:trace)
        let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:transport)
        let output=try await client.getCurrentAccountCleanupProgress(.init(query:.init(operation_id:originalOperation)))
        let progress=try output.ok.body.json.progress
        #expect(progress.operation_id==originalOperation && progress.status == .blocked)
        #expect(progress.steps[0].state == .pending && progress.steps[0].reason == .hook_unavailable)
        let paths=await wire.paths;#expect(paths.count==1)
        let path=try #require(paths.first ?? nil)
        let query=try #require(URLComponents(string:"https://synthetic.invalid"+path)?.queryItems)
        #expect(query.count==1 && query[0].name=="operation_id" && query[0].value==originalOperation)
    }
    @Test func unknownEnumsMissingNullAndPrivateFieldsDoNotBecomeCompletion() throws {
        let bytes=try JSONSerialization.data(withJSONObject:object(status:"unknown"))
        let decoded=try JSONDecoder().decode(Components.Schemas.CurrentAccountCleanupProgressResponse.self,from:bytes)
        #expect(decoded.progress.status == .unknown && decoded.progress.steps[0].state == .unknown)
        #expect(Components.Schemas.CurrentAccountCleanupProgress.statusPayload.allCases.count==6)
        #expect(Components.Schemas.CleanupProgressStep.statePayload.allCases.count==5)
        for value:[String:Any] in [["request_id":trace],["request_id":trace,"progress":NSNull()],object(status:"deleted")] {
            #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.CurrentAccountCleanupProgressResponse.self,from:JSONSerialization.data(withJSONObject:value))}
        }
        var privateValue=object();var progress=privateValue["progress"] as! [String:Any];progress["scope"]="caller-scope";privateValue["progress"]=progress
        #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.CurrentAccountCleanupProgressResponse.self,from:JSONSerialization.data(withJSONObject:privateValue))}
    }
    @Test func unavailableRemainsBASEErrorAndDoesNotInvokeRecovery() async throws {
        let error:[String:Any]=["request_id":trace,"error":["code":"CLEANUP_PROGRESS_UNAVAILABLE","category":"dependency","outcome":"unknown","recovery":"retry_safe_read","message_en":"Synthetic unavailable","message_zh":"合成不可用"]]
        let bytes=try JSONSerialization.data(withJSONObject:error)
        let wire=CleanupProgressIntercept(bytes:bytes,status:503,trace:trace)
        let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),transport:transport)
        let output=try await client.getCurrentAccountCleanupProgress(.init(query:.init(operation_id:originalOperation)))
        if case .default(let status,let response)=output {
            let value=try response.body.json
            #expect(status==503 && value.error.outcome == .unknown && value.error.recovery == .retry_safe_read)
        } else {Issue.record("unavailable is not cleanup completion")}
        #expect(await wire.paths.count==1)
        #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.CurrentAccountCleanupProgressResponse.self,from:bytes)}
    }
}
