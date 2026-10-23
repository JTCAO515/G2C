import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes
private enum Failed:Error { case check,unexpected }
private struct FixtureTransport:ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        guard operationID=="getCurrentAccountCleanupProgress",request.path=="/v1/account-cleanup-progress?operation_id=original%2Foperation" else { throw Failed.check }
        let progress:[String:Any]=["operation_id":"original/operation","revision":2,"status":"unknown","steps":[["target":"auth_revocation","state":"unknown","reason":"original_result_unknown"],["target":"backup_retention","state":"pending","reason":"hook_unavailable"]],"reasons":["hook_unavailable","original_result_unknown"]]
        let data:[String:Any]=["request_id":"00000000-0000-4000-8000-000000000001","progress":progress]
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[.init("X-Request-ID")!]="00000000-0000-4000-8000-000000000001"
        return(response,HTTPBody(try JSONSerialization.data(withJSONObject:data)))
    }
}
@main struct CleanupProgressGeneratedConsumer {
    static func main() async throws {
        guard let url=URL(string:"https://fixture.invalid") else { throw Failed.check }
        let client=Client(serverURL:url,configuration:.memory,transport:FixtureTransport())
        let r=try await client.getCurrentAccountCleanupProgress(.init(query:.init(operation_id:"original/operation"))).ok
        let body=try r.body.json
        guard body.request_id==r.headers.X_hyphen_Request_hyphen_ID,body.progress.operation_id=="original/operation",body.progress.revision==2,
              body.progress.status == .unknown,body.progress.steps[0].state == .unknown,
              body.progress.steps[1].reason == .hook_unavailable else { throw Failed.check }
        for raw in [#"{"request_id":"00000000-0000-4000-8000-000000000001"}"#,#"{"request_id":"00000000-0000-4000-8000-000000000001","progress":null}"#] {
            do{_=try JSONDecoder().decode(Components.Schemas.CurrentAccountCleanupProgressResponse.self,from:Data(raw.utf8));throw Failed.unexpected}
            catch is DecodingError {}
        }
        print("PASS generated cleanup readonly GET/opaque original query, original unknown/missing-hook states, mandatory nonnull progress")
    }
}
