import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime

private struct NeedsExportOnlyTransport: ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        Issue.record("NEEDS export checks must not issue requests")
        throw URLError(.unsupportedURL)
    }
}
struct NeedsConfigurationExportTests {
    let trace="389334ea-e082-48c6-ae39-7df003c2280b"
    @Test func fixedOfficialNeedsMethodsCompileWithoutRequests() throws {
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:NeedsExportOnlyTransport())
        _ = client.actOnNeeds; _ = client.queryNeedsAction; _ = client.getNeeds; _ = client.getNeedsRevision
        #expect(Operations.actOnNeeds.id=="actOnNeeds")
        #expect(Operations.queryNeedsAction.id=="queryNeedsAction")
        #expect(Operations.getNeeds.id=="getNeeds")
        #expect(Operations.getNeedsRevision.id=="getNeedsRevision")
    }
    @Test func officialNullableFieldsRequirePresenceAndActualNull() throws {
        let decoder=JSONDecoder()
        let receipt=try decoder.decode(Components.Schemas.NeedsActionQueryResponse.self,from:Data("{\"request_id\":\"\(trace)\",\"receipt\":null}".utf8))
        if case .case2(let value)=receipt.receipt { #expect(value.value==nil) } else { Issue.record("expected explicit null") }
        let needs=try decoder.decode(Components.Schemas.NeedsDetailResponse.self,from:Data("{\"request_id\":\"\(trace)\",\"needs\":null}".utf8))
        if case .case2(let value)=needs.needs { #expect(value.value==nil) } else { Issue.record("expected explicit null") }
        let revision=try decoder.decode(Components.Schemas.NeedsRevisionResponse.self,from:Data("{\"request_id\":\"\(trace)\",\"revision\":null}".utf8))
        if case .case2(let value)=revision.revision { #expect(value.value==nil) } else { Issue.record("expected explicit null") }
        let missing=Data("{\"request_id\":\"\(trace)\"}".utf8)
        #expect(throws:DecodingError.self) {try decoder.decode(Components.Schemas.NeedsActionQueryResponse.self,from:missing)}
        #expect(throws:DecodingError.self) {try decoder.decode(Components.Schemas.NeedsDetailResponse.self,from:missing)}
        #expect(throws:DecodingError.self) {try decoder.decode(Components.Schemas.NeedsRevisionResponse.self,from:missing)}
        let fallback=try decoder.decode(Components.Schemas.NeedsActionQueryResponse.self,from:Data("{\"request_id\":\"\(trace)\",\"receipt\":false}".utf8))
        if case .case2(let value)=fallback.receipt { #expect(value.value != nil) } else { Issue.record("false must not become receipt/null") }
    }
    @Test func validReceiptUsesOfficialTypedBranch() throws {
        let bytes=Data("{\"request_id\":\"\(trace)\",\"receipt\":{\"action_id\":\"synthetic-action\",\"needs_id\":\"synthetic-needs\",\"version\":1,\"operation\":\"manual_patch\"}}".utf8)
        let result=try JSONDecoder().decode(Components.Schemas.NeedsActionQueryResponse.self,from:bytes)
        if case .NeedsReceipt(let receipt)=result.receipt {
            #expect(receipt.version==1 && receipt.operation == .manual_patch)
        } else { Issue.record("valid receipt must use official typed branch") }
    }
}
