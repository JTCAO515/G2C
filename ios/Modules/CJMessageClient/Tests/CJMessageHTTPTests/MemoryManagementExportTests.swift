import Foundation
import CryptoKit
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor ManagementIntercept: ClientTransport {
    let bytes:Data;let status:Int;let trace:String
    var calls=0;var bodies:[Data]=[];var paths:[String?]=[];var media:[String?]=[]
    init(bytes:Data,status:Int=200,trace:String) {self.bytes=bytes;self.status=status;self.trace=trace}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        calls+=1;paths.append(request.path);media.append(request.headerFields[.contentType])
        if let body {bodies.append(try await Data(collecting:body,upTo:32768))}
        var response=HTTPResponse(status:.init(code:status));response.headerFields[.contentType]="application/json";response.headerFields[HTTPField.Name("X-Request-ID")!]=trace
        return(response,HTTPBody(bytes))
    }
}
struct MemoryManagementExportTests {
    let trace="cfcf16c5-cc7f-4620-a7b7-14ef01d259a6"
    private func raw(_ operation:String)->Data {
        Data(" {\"action_id\":\"original/+e\\u0301\",\"operation\":\"\(operation)\",\"item_id\":\"synthetic-item\",\"expected_version\":1,\"expected_source_version\":1} \n".utf8)
    }
    private func receipt(_ operation:String)->[String:Any] {
        ["action_id":"original/+e\u{301}","item_id":"synthetic-item","version":2,"status":operation=="pause" ? "disabled":"active","input_sha256":SHA256.hash(data:raw(operation)).map{String(format:"%02x",$0)}.joined()]
    }
    @Test func officialBinaryPauseResumeBytesAndHistoricalReceiptFields() async throws {
        for operation in ["pause","resume"] {
            let bytes=try JSONSerialization.data(withJSONObject:["request_id":trace,"receipt":receipt(operation)])
            let wire=ManagementIntercept(bytes:bytes,trace:trace)
            let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:wire)
            let output=try await client.applyMemoryManagementAction(.init(body:.binary(HTTPBody(raw(operation)))))
            let body=try output.ok.body.json
            #expect(body.receipt.status.rawValue == (operation=="pause" ? "disabled":"active"))
            #expect(body.receipt.input_sha256 == receipt(operation)["input_sha256"] as? String)
            #expect(await wire.bodies == [raw(operation)])
            #expect(await wire.media == ["application/octet-stream"])
            #expect(await wire.paths == ["/v1/memory-management-actions"])
        }
    }
    @Test func originalReceiptGETNullMissingAndNonNullFallbackStayDistinct() async throws {
        let nullBytes=try JSONSerialization.data(withJSONObject:["request_id":trace,"receipt":NSNull()])
        let wire=ManagementIntercept(bytes:nullBytes,trace:trace)
        let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
        let client=Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),transport:transport)
        let id="original/+e\u{301}"
        let output=try await client.queryMemoryManagementReceipt(.init(query:.init(action_id:id)))
        let value=try output.ok.body.json
        if case .case2(let v)=value.receipt {#expect(v.value==nil)} else {Issue.record("actual null expected")}
        let paths=await wire.paths;let path=try #require(paths.first ?? nil)
        let query=try #require(URLComponents(string:"https://synthetic.invalid"+path)?.queryItems)
        #expect(query.count==1 && query[0].name=="action_id" && Data((query[0].value ?? "").utf8)==Data(id.utf8))
        #expect(throws:DecodingError.self) {try JSONDecoder().decode(Components.Schemas.MemoryManagementReceiptResponse.self,from:JSONSerialization.data(withJSONObject:["request_id":trace]))}
        let bad=try JSONDecoder().decode(Components.Schemas.MemoryManagementReceiptResponse.self,from:JSONSerialization.data(withJSONObject:["request_id":trace,"receipt":false]))
        if case .case2(let v)=bad.receipt {#expect(v.value != nil)} else {Issue.record("non-null fallback is not absence")}
        #expect(await wire.calls==1)
    }
    @Test func strictFiveFieldsAndUnknownErrorDoNotBecomeAppliedReceipt() throws {
        let decoder=JSONDecoder()
        for operation in ["pause","resume"] {
            let model=try decoder.decode(Components.Schemas.MemoryManagementAction.self,from:raw(operation))
            #expect(model.operation.rawValue==operation && model.expected_version==1 && model.expected_source_version==1)
        }
        var extra=try JSONSerialization.jsonObject(with:raw("pause")) as! [String:Any];extra["owner"]="caller"
        #expect(throws:DecodingError.self) {try decoder.decode(Components.Schemas.MemoryManagementAction.self,from:JSONSerialization.data(withJSONObject:extra))}
        #expect(throws:DecodingError.self) {try decoder.decode(Components.Schemas.MemoryManagementAction.self,from:raw("delete"))}
        let failure=try JSONSerialization.data(withJSONObject:["request_id":trace,"error":["code":"SYNTHETIC_UNAVAILABLE","category":"dependency","outcome":"unknown","recovery":"reconcile_original","message_en":"Synthetic unknown","message_zh":"合成未知"]])
        let error=try decoder.decode(Components.Schemas.ErrorResponse.self,from:failure)
        #expect(error.error.outcome == .unknown && error.error.recovery == .reconcile_original)
        #expect(throws:DecodingError.self) {try decoder.decode(Components.Schemas.MemoryManagementApplyResponse.self,from:failure)}
    }
    @Test func defaultAndReadonlyPreviewTransportsDoNotEnableMemoryWrite() async throws {
        let wire=ManagementIntercept(bytes:Data("{}".utf8),trace:trace)
        let e=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:32768,maximumResponseBytes:65536)
        let closed=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:nil,validatePreview:nil)
        let preview=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:e,validatePreview:{})
        for transport in [closed,preview] {
            let client=Client(serverURL:e.url,transport:transport)
            await #expect(throws:(any Error).self) {try await client.applyMemoryManagementAction(.init(body:.binary(HTTPBody(raw("pause")))))}
        }
        #expect(await wire.calls==0)
    }
}
