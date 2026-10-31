import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor EditExitSpy: ClientTransport {
    var calls=0
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls += 1
        if let body { _=try await Data(collecting:body,upTo:65536) }
        return (HTTPResponse(status:.ok),HTTPBody(Data("{}".utf8)))
    }
}
@MainActor struct TripEditTransportTests {
    private func endpoint() throws -> MessageEndpoint {
        try .init(url:#require(URL(string:"http://127.0.0.1:58001")),maximumRequestBytes:16384,maximumResponseBytes:16384,allowLoopbackHTTP:true)
    }
    private func body() throws -> Data {
        var root=URL(fileURLWithPath:#filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let examples=try #require(JSONSerialization.jsonObject(with:Data(contentsOf:root.appendingPathComponent("contracts/message/edit-examples.1.json"))) as? [String:Any])
        let values=try #require(examples["positive"] as? [[String:Any]])
        return try JSONSerialization.data(withJSONObject:values[1],options:[.sortedKeys])
    }
    private func request() -> HTTPRequest {
        var headers=HTTPFields();headers[.contentType]="application/octet-stream"
        return HTTPRequest(method:.post,scheme:nil,authority:nil,path:"/v4/messages",headerFields:headers)
    }
    @Test func onlyTheExplicitFourthCapabilityCanSendFourthBytes() async throws {
        let endpoint=try endpoint(),spy=EditExitSpy(),bytes=try body()
        let readonly=try NoRedirectTransport(interceptedTransport:spy,previewEndpoint:nil,validatePreview:nil)
        let old=NoRedirectTransport(interceptedTransport:spy,tripDiscussionEndpoint:endpoint,validateDiscussion:{})
        await #expect(throws:(any Error).self) { try await readonly.send(request(),body:HTTPBody(bytes),baseURL:endpoint.url,operationID:"receiveTripEditV4") }
        await #expect(throws:(any Error).self) { try await old.send(request(),body:HTTPBody(bytes),baseURL:endpoint.url,operationID:"receiveTripEditV4") }
        #expect(await spy.calls == 0)
        let current=NoRedirectTransport(interceptedTransport:spy,tripEditEndpoint:endpoint,validateEdit:{})
        _=try await current.send(request(),body:HTTPBody(bytes),baseURL:endpoint.url,operationID:"receiveTripEditV4")
        #expect(await spy.calls == 1)
    }
    @Test(arguments:["path","operation","host","body","put"])
    func changedShapeCannotUseTheExit(kind: String) async throws {
        let endpoint=try endpoint(),spy=EditExitSpy(),live=NoRedirectTransport(interceptedTransport:spy,tripEditEndpoint:endpoint,validateEdit:{})
        var req=request(),operation="receiveTripEditV4",base=endpoint.url,bytes=try body()
        switch kind {
        case "path":req.path="/v3/messages"
        case "operation":operation="receiveTripDiscussionV3"
        case "host":base=try #require(URL(string:"http://127.0.0.1:58002"))
        case "body":bytes=Data(String(decoding:bytes,as:UTF8.self).replacingOccurrences(of:"MESSAGE-send.4",with:"MESSAGE-send.3").utf8)
        default:req.method = .put;req.path="/v1/conversations?conversation_id=discussion."+UUID().uuidString;operation="openConversation"
        }
        await #expect(throws:(any Error).self) { try await live.send(req,body:HTTPBody(bytes),baseURL:base,operationID:operation) }
        #expect(await spy.calls == 0)
    }
    @Test func callbackBeforeDispatchAndAfterResponseIsCurrent() async throws {
        let endpoint=try endpoint(),spy=EditExitSpy(),bytes=try body()
        var validations=0
        let before=NoRedirectTransport(interceptedTransport:spy,tripEditEndpoint:endpoint,validateEdit:{throw MessageHTTPFailure.credentialsUnavailable})
        await #expect(throws:(any Error).self) { try await before.send(request(),body:HTTPBody(bytes),baseURL:endpoint.url,operationID:"receiveTripEditV4") }
        #expect(await spy.calls == 0)
        let after=NoRedirectTransport(interceptedTransport:spy,tripEditEndpoint:endpoint,validateEdit:{validations += 1;if validations==2 {throw MessageHTTPFailure.credentialsUnavailable}})
        await #expect(throws:(any Error).self) { try await after.send(request(),body:HTTPBody(bytes),baseURL:endpoint.url,operationID:"receiveTripEditV4") }
        #expect(await spy.calls == 1 && validations == 2)
    }
    @Test func normalHostCannotActivateTheSimulatorExit() throws {
        #if !targetEnvironment(simulator)
        #expect(throws:MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentTripEdits(endpoint:endpoint(),requestTimeout:1,resourceTimeout:2,validate:{})
        }
        #endif
    }
}
