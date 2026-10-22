import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor AssociationIntercept: ClientTransport {
    let bytes:Data;let status:Int;let trace:String
    var paths:[String?]=[]
    init(bytes:Data,status:Int=200,trace:String) {self.bytes=bytes;self.status=status;self.trace=trace}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        #expect(request.method == .get && operationID == "getOriginalUsageAssociation" && body == nil)
        paths.append(request.path)
        var response=HTTPResponse(status:.init(code:status));response.headerFields[.contentType]="application/json";response.headerFields[HTTPField.Name("X-Request-ID")!]=trace
        return(response,HTTPBody(bytes))
    }
}
struct OriginalUsageAssociationExportTests {
    let trace="ee47419a-77ec-435f-8495-e867d7a2bc63"
    let message="original/+%e\u{301}"
    private func association()->[String:Any] {
        ["conversation_id":"synthetic-chat","generation":"e\u{301}","message_id":message,"run_id":"synthetic-run","message_sequence":1,"attempt_id":"synthetic-original-attempt","operation_id":"synthetic-original-operation"]
    }
    @Test func officialGETTakesOnlyOriginalMessageAndPreservesReferences() async throws {
        let bytes=try JSONSerialization.data(withJSONObject:["request_id":trace,"association":association()])
        let wire=AssociationIntercept(bytes:bytes,trace:trace)
        let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:transport)
        let output=try await client.getOriginalUsageAssociation(.init(query:.init(message_id:message)))
        let body=try output.ok.body.json
        #expect(Data(body.association.message_id.utf8)==Data(message.utf8))
        #expect(Data(body.association.generation.utf8)==Data("e\u{301}".utf8))
        #expect(body.association.attempt_id=="synthetic-original-attempt" && body.association.operation_id=="synthetic-original-operation")
        let paths=await wire.paths;#expect(paths.count==1)
        let path=try #require(paths.first ?? nil)
        let query=try #require(URLComponents(string:"https://synthetic.invalid"+path)?.queryItems)
        #expect(query.count==1 && query[0].name=="message_id")
        #expect(Data((query[0].value ?? "").utf8)==Data(message.utf8))
    }
    @Test func missingNullOrExtraSourceFieldsAreNotEmptySuccess() throws {
        for value:[String:Any] in [["request_id":trace],["request_id":trace,"association":NSNull()]] {
            #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.OriginalUsageAssociationResponse.self,from:JSONSerialization.data(withJSONObject:value))}
        }
        var missing=association();missing.removeValue(forKey:"attempt_id")
        var extra=association();extra["scope"]="caller-scope"
        for value in [missing,extra] {
            #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.OriginalUsageAssociationResponse.self,from:JSONSerialization.data(withJSONObject:["request_id":trace,"association":value]))}
        }
    }
    @Test func unavailable503RemainsBASEErrorWithoutRetryOrAssociation() async throws {
        let bytes=try JSONSerialization.data(withJSONObject:["request_id":trace,"error":["code":"ORIGINAL_USAGE_UNAVAILABLE","category":"dependency","outcome":"unknown","recovery":"retry_safe_read","message_en":"Synthetic unavailable","message_zh":"合成不可用"]])
        let wire=AssociationIntercept(bytes:bytes,status:503,trace:trace)
        let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),transport:transport)
        let output=try await client.getOriginalUsageAssociation(.init(query:.init(message_id:message)))
        if case .default(let status,let response)=output {
            let body=try response.body.json
            #expect(status==503 && body.error.code=="ORIGINAL_USAGE_UNAVAILABLE" && body.error.outcome == .unknown && body.error.recovery == .retry_safe_read)
        } else {Issue.record("unavailable must not become a successful association")}
        #expect(await wire.paths.count==1)
        #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.OriginalUsageAssociationResponse.self,from:bytes)}
    }
}
