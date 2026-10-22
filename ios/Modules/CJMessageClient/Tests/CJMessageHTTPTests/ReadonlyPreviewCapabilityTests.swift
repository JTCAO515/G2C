import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor CapabilityInterceptor: ClientTransport {
    var calls=0;var bytes:[Data]=[]
    let response:HTTPResponse
    let payload:Data
    let hook:(@Sendable () async -> Void)?
    init(status:HTTPResponse.Status = .ok,payload:Data=Data("{}".utf8),hook:(@Sendable () async -> Void)?=nil) {
        response=HTTPResponse(status:status);self.payload=payload;self.hook=hook
    }
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        calls+=1
        if let body {bytes.append(try await Data(collecting:body,upTo:1000))}
        await hook?();return (response,HTTPBody(payload))
    }
}
@MainActor private final class CapabilityLifetime {
    var current=true;var checks=0
    func validate() throws {checks+=1;if !current {throw MessageHTTPFailure.productionActivationUnavailable}}
}
@Suite @MainActor struct ReadonlyPreviewCapabilityTests {
    private func endpoint(request:Int=100,response:Int=100) throws -> MessageEndpoint {
        try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:request,maximumResponseBytes:response)
    }
    private func request(_ path:String="/v1/trip-manual-previews",method:HTTPRequest.Method = .post)->HTTPRequest {
        var r=HTTPRequest(method:method,scheme:nil,authority:nil,path:path);r.headerFields[.contentType]="application/json";return r
    }
    @Test func exactCapabilityForwardsReadonlyBytesAndRevalidates() async throws {
        let intercepted=CapabilityInterceptor();let life=CapabilityLifetime();let e=try endpoint()
        let t=try NoRedirectTransport(interceptedTransport:intercepted,previewEndpoint:e,validatePreview:{try life.validate()})
        let raw=Data(" {\"fixture\":true} \n".utf8)
        _=try await t.send(request(),body:HTTPBody(raw),baseURL:e.url,operationID:Operations.previewManualTripEdit.id)
        #expect(await intercepted.bytes == [raw]);#expect(life.checks==3)
    }
    @Test func defaultAndEveryOtherWriteOrClaimAreClosed() async throws {
        let intercepted=CapabilityInterceptor();let e=try endpoint()
        let defaults=try NoRedirectTransport(interceptedTransport:intercepted,previewEndpoint:nil,validatePreview:nil)
        await #expect(throws:MessageHTTPFailure.self) {try await defaults.send(request(),body:HTTPBody("{}"),baseURL:e.url,operationID:"previewManualTripEdit")}
        let t=try NoRedirectTransport(interceptedTransport:intercepted,previewEndpoint:e,validatePreview:{})
        for (path,method,op) in [("/v1/messages",HTTPRequest.Method.post,"receiveMessage"),("/v1/memory-actions",.post,"manualMemoryAction"),("/v1/trip-actions",.post,"actOnTripProposal"),("/v1/message-drafts",.put,"saveMessageDraft"),("/v1/trip-manual-previews",.delete,"previewManualTripEdit"),("/v1/trip-manual-previews",.post,"caller-readonly"),("/v1/trip-manual-previews?fake=1",.post,"previewManualTripEdit")] {
            await #expect(throws:MessageHTTPFailure.self) {try await t.send(request(path,method:method),body:HTTPBody("{}"),baseURL:e.url,operationID:op)}
        }
        #expect(await intercepted.calls==0)
    }
    @Test func hostAuthorityAndByteLimitsCannotEscape() async throws {
        let intercepted=CapabilityInterceptor();let e=try endpoint(request:2)
        let t=try NoRedirectTransport(interceptedTransport:intercepted,previewEndpoint:e,validatePreview:{})
        await #expect(throws:(any Error).self) {try await t.send(request(),body:HTTPBody("too long"),baseURL:e.url,operationID:"previewManualTripEdit")}
        await #expect(throws:(any Error).self) {try await t.send(request(),body:HTTPBody("{}"),baseURL:#require(URL(string:"https://other.invalid")),operationID:"previewManualTripEdit")}
        var override=request();override.authority="other.invalid"
        await #expect(throws:(any Error).self) {try await t.send(override,body:HTTPBody("{}"),baseURL:e.url,operationID:"previewManualTripEdit")}
        #expect(await intercepted.calls==0)
    }
    @Test func retiredIdentityRedirectAndOversizedResponseDoNotReturn() async throws {
        let e=try endpoint(response:2);let life=CapabilityLifetime();life.current=false
        let never=CapabilityInterceptor();let retired=try NoRedirectTransport(interceptedTransport:never,previewEndpoint:e,validatePreview:{try life.validate()})
        await #expect(throws:(any Error).self) {try await retired.send(request(),body:HTTPBody("{}"),baseURL:e.url,operationID:"previewManualTripEdit")}
        #expect(await never.calls==0)
        for source in [CapabilityInterceptor(status:.found),CapabilityInterceptor(payload:Data("oversized".utf8)),CapabilityInterceptor(hook:{await MainActor.run {life.current=false}})] {
            life.current=true
            let t=try NoRedirectTransport(interceptedTransport:source,previewEndpoint:e,validatePreview:{try life.validate()})
            await #expect(throws:(any Error).self) {try await t.send(request(),body:HTTPBody("{}"),baseURL:e.url,operationID:"previewManualTripEdit")}
            #expect(await source.calls==1)
        }
    }
    @Test func actualOfficialPreviewOperationPassesOnlyTheNarrowEntry() async throws {
        let original=Data(#"{"items":[{"evidence":[],"id":"a","text":"Synthetic","verification":"pending"}],"title":"Synthetic"}"#.utf8)
        let input:[String:Any]=["trip_id":"t1","expected_version":1,"original_content_utf8_base64":original.base64EncodedString(),"selected_ids":[],"title_selected":false,"title":NSNull(),"text_updates":[],"order":NSNull()]
        let requestModel=try JSONDecoder().decode(Components.Schemas.ManualPreviewRequest.self,from:JSONSerialization.data(withJSONObject:input))
        let reply=OfficialManualCapabilityReply(original:original)
        let e=try endpoint(request:4000,response:4000);let life=CapabilityLifetime()
        let transport=try NoRedirectTransport(interceptedTransport:reply,previewEndpoint:e,validatePreview:{try life.validate()})
        let client=Client(serverURL:e.url,configuration:.memory,transport:transport)
        let result=try await client.previewManualTripEdit(.init(body:.json(requestModel)))
        let model=try result.ok.body.json.preview
        #expect(model.protection_status == .UNKNOWN && !model.can_save && model.preview_status == .LOCAL)
        #expect(await reply.calls==1 && life.checks==3)
    }

    @Test func productionFactoryRequiresExplicitFiniteTimeouts() throws {
        #expect(throws:MessageHTTPFailure.self) {try NoRedirectTransport.readOnlyManualPreview(endpoint:endpoint(),requestTimeout:.infinity,resourceTimeout:1,validate:{})}
        #expect(throws:MessageHTTPFailure.self) {try NoRedirectTransport.readOnlyManualPreview(endpoint:endpoint(),requestTimeout:1,resourceTimeout:0,validate:{})}
        _=try NoRedirectTransport.readOnlyManualPreview(endpoint:endpoint(),requestTimeout:1,resourceTimeout:2,validate:{})
    }
}

private actor OfficialManualCapabilityReply: ClientTransport {
    let original:Data
    var calls=0
    init(original:Data) {self.original=original}
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        calls+=1
        #expect(request.path=="/v1/trip-manual-previews" && request.method == .post)
        #expect(operationID==Operations.previewManualTripEdit.id)
        guard let body else {throw MessageHTTPFailure.invalidResponse}
        let decoded=try JSONDecoder().decode(Components.Schemas.ManualPreviewRequest.self,from:try await Data(collecting:body,upTo:4000))
        #expect(Data(base64Encoded:decoded.original_content_utf8_base64)==original)
        let document:[String:Any]=["title":"Synthetic","items":[["id":"a","text":"Synthetic","verification":"pending","evidence":[]]]]
        let preview:[String:Any]=["preview_status":"LOCAL","original":["trip_id":"t1","version":1,"content_utf8_base64":original.base64EncodedString(),"document":document],"content_utf8_base64":original.base64EncodedString(),"document":document,"selected_ids":[],"title_selected":false,"protection_status":"UNKNOWN","can_save":false,"diff":[]]
        let trace="ac1647a8-50cb-4856-b52d-d1253bba266b"
        let bytes=try JSONSerialization.data(withJSONObject:["request_id":trace,"preview":preview])
        var response=HTTPResponse(status:.ok);response.headerFields[.contentType]="application/json";response.headerFields[HTTPField.Name("X-Request-ID")!]=trace
        return(response,HTTPBody(bytes))
    }
}
