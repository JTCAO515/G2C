import Foundation
import CJAPI
import OpenAPIRuntime
import HTTPTypes
private enum Failed:Error { case check,unexpected }
private let pause=Data("{\n \"action_id\":\"original+action\",\"operation\":\"pause\",\"item_id\":\"item\",\"expected_version\":1,\"expected_source_version\":1}\n".utf8)
private let resume=Data("{\n \"action_id\":\"resume+action\",\"operation\":\"resume\",\"item_id\":\"item\",\"expected_version\":2,\"expected_source_version\":1}\n".utf8)
private struct Transport:ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        var receipt:Any=NSNull()
        if operationID=="applyMemoryManagementAction" {
            guard request.path=="/v1/memory-management-actions",request.headerFields[.contentType]=="application/octet-stream",let body else{throw Failed.check}
            let bytes=try await Data(collecting:body,upTo:32768)
            guard bytes==pause || bytes==resume else{throw Failed.check}
            receipt=["action_id":bytes==pause ? "original+action":"resume+action","item_id":"item","version":bytes==pause ? 2:3,"status":bytes==pause ? "disabled":"active","input_sha256":String(repeating:"a",count:64)]
        } else {
            guard operationID=="queryMemoryManagementReceipt",request.path=="/v1/memory-management-receipts?action_id=original%2Baction" else{throw Failed.check}
        }
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[.init("X-Request-ID")!]="00000000-0000-4000-8000-000000000001"
        return(response,HTTPBody(try JSONSerialization.data(withJSONObject:["request_id":"00000000-0000-4000-8000-000000000001","receipt":receipt])))
    }
}
@main struct MemoryManagementConsumer {
    static func main() async throws {
        guard let url=URL(string:"https://fixture.invalid") else{throw Failed.check}
        let client=Client(serverURL:url,configuration:.memory,transport:Transport())
        let paused=try await client.applyMemoryManagementAction(.init(body:.binary(HTTPBody(pause)))).ok.body.json
        let resumed=try await client.applyMemoryManagementAction(.init(body:.binary(HTTPBody(resume)))).ok.body.json
        guard paused.receipt.status == .disabled,paused.receipt.action_id=="original+action",paused.receipt.version==2,
              resumed.receipt.status == .active,resumed.receipt.version==3 else{throw Failed.check}
        let queried=try await client.queryMemoryManagementReceipt(.init(query:.init(action_id:"original+action"))).ok
        let body=try queried.body.json
        guard body.request_id==queried.headers.X_hyphen_Request_hyphen_ID,case .case2(let absent)=body.receipt,absent.value==nil else{throw Failed.check}
        for raw in [#"{"request_id":"00000000-0000-4000-8000-000000000001"}"#,#"{"request_id":"00000000-0000-4000-8000-000000000001","receipt":null}"#] {
            do{_=try JSONDecoder().decode(Components.Schemas.MemoryManagementApplyResponse.self,from:Data(raw.utf8));throw Failed.unexpected}
            catch is DecodingError {}
        }
        let malformed=try JSONDecoder().decode(Components.Schemas.MemoryManagementReceiptResponse.self,from:Data(#"{"request_id":"00000000-0000-4000-8000-000000000001","receipt":"invalid"}"#.utf8))
        guard case .case2(let invalid)=malformed.receipt,invalid.value != nil else{throw Failed.check}
        print("PASS generated pause/resume exact binary UTF8, original action query encoding, historical active/disabled receipt, required null versus missing/malformed consumer")
    }
}
