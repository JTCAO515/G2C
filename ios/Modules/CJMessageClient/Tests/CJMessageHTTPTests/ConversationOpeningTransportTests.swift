import Foundation
import Testing
import OpenAPIRuntime
import HTTPTypes
import CJAPI
@testable import CJMessageHTTP

private actor OpeningExitSpy:ClientTransport {
    var calls=0
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        calls+=1
        #expect(request.method == .put && operationID==Operations.openConversation.id && body==nil)
        return (HTTPResponse(status:.ok),HTTPBody("{}".utf8))
    }
}
@MainActor private final class OpeningExitLifetime {
    var active=true
    func check() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
@MainActor struct ConversationOpeningTransportTests {
    private func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url:#require(URL(string:"http://127.0.0.1:9062")),maximumRequestBytes:16384,maximumResponseBytes:65536,allowLoopbackHTTP:true)
    }
    private func request() -> HTTPRequest {
        HTTPRequest(method:.put,scheme:nil,authority:nil,path:"/v1/conversations?conversation_id=discussion."+UUID().uuidString)
    }
    @Test func existingAndOrdinaryEntrypointsCannotCreateConversations() async throws {
        let spy=OpeningExitSpy(),endpoint=try endpoint(),request=request()
        let closed=try NoRedirectTransport(interceptedTransport:spy,previewEndpoint:nil,validatePreview:nil)
        let legacy=try NoRedirectTransport(interceptedTransport:spy,messageEndpoint:endpoint,validateMessage:{})
        let travel=NoRedirectTransport(interceptedTransport:spy,travelMessageEndpoint:endpoint,validateMessage:{})
        for transport in [closed,legacy,travel] {
            await #expect(throws:(any Error).self) { try await transport.sendConversationOpening(request,body:nil,baseURL:endpoint.url,operationID:Operations.openConversation.id,validateOriginal:{}) }
        }
        let discussion=NoRedirectTransport(interceptedTransport:spy,tripDiscussionEndpoint:endpoint,validateDiscussion:{})
        await #expect(throws:(any Error).self) { try await discussion.send(request,body:nil,baseURL:endpoint.url,operationID:Operations.openConversation.id) }
        #expect(await spy.calls==0)
    }
    @Test func sealedExitKeepsExactMethodPathIDHostAndEmptyBody() async throws {
        let spy=OpeningExitSpy(),endpoint=try endpoint(),transport=NoRedirectTransport(interceptedTransport:spy,tripDiscussionEndpoint:endpoint,validateDiscussion:{})
        let original=request()
        _=try await transport.sendConversationOpening(original,body:nil,baseURL:endpoint.url,operationID:Operations.openConversation.id,validateOriginal:{})
        for path in ["/v1/conversations?conversation_id=existing-chat",original.path!+"&owner=caller",original.path!+"#fragment","https://other.invalid"+original.path!,"/v2/conversations?conversation_id=x"] {
            var changed=original;changed.path=path
            await #expect(throws:(any Error).self) { try await transport.sendConversationOpening(changed,body:nil,baseURL:endpoint.url,operationID:Operations.openConversation.id,validateOriginal:{}) }
        }
        var host=original;host.headerFields[.init("host")!]="other.invalid"
        var post=original;post.method = .post
        var authority=original;authority.authority="other.invalid"
        for changed in [host,post,authority] {
            await #expect(throws:(any Error).self) { try await transport.sendConversationOpening(changed,body:nil,baseURL:endpoint.url,operationID:Operations.openConversation.id,validateOriginal:{}) }
        }
        await #expect(throws:(any Error).self) { try await transport.sendConversationOpening(original,body:HTTPBody("{}".utf8),baseURL:endpoint.url,operationID:Operations.openConversation.id,validateOriginal:{}) }
        #expect(await spy.calls==1)
    }
    @Test func scopeCallbackCannotBypassOriginalOperationCheckAtLastExit() async throws {
        let spy=OpeningExitSpy(),endpoint=try endpoint(),lifetime=OpeningExitLifetime()
        let transport=NoRedirectTransport(interceptedTransport:spy,tripDiscussionEndpoint:endpoint,validateDiscussion:{ lifetime.active=false })
        await #expect(throws:MessageHTTPFailure.credentialsUnavailable) {
            try await transport.sendConversationOpening(request(),body:nil,baseURL:endpoint.url,operationID:Operations.openConversation.id,validateOriginal:{ try lifetime.check() })
        }
        #expect(await spy.calls==0)
    }
}
