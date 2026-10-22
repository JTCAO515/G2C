import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

private actor HeaderBoundaryTransport: ClientTransport {
    var calls=0
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        calls+=1
        return (HTTPResponse(status:.ok),HTTPBody("{}"))
    }
}
@MainActor private final class HeaderValidationCount {var calls=0}
@Suite @MainActor struct PreviewHostHeaderBoundaryTests {
    private func check(_ headers:[(String,String)]) async throws {
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:100,maximumResponseBytes:100)
        let wire=HeaderBoundaryTransport();let validation=HeaderValidationCount()
        let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:endpoint,validatePreview:{validation.calls+=1})
        var request=HTTPRequest(method:.post,scheme:nil,authority:nil,path:"/v1/trip-manual-previews")
        request.headerFields[.contentType]="application/json"
        for (name,value) in headers {request.headerFields.append(HTTPField(name:try #require(HTTPField.Name(name)),value:value))}
        #expect(request.authority==nil && request.scheme==nil)
        await #expect(throws:MessageHTTPFailure.self) {try await transport.send(request,body:HTTPBody("{}"),baseURL:endpoint.url,operationID:"previewManualTripEdit")}
        #expect(await wire.calls==0);#expect(validation.calls==0)
    }
    @Test func anyHostValueOrCasingRejectsBeforeOutflow() async throws {
        for item in [("Host","other.invalid"),("HOST","synthetic.invalid"),("hOsT","synthetic.invalid:443"),("host","")] {
            try await check([item])
        }
    }
    @Test func duplicateMixedCaseHostIsAlsoRejected() async throws {
        try await check([("Host","synthetic.invalid"),("host","other.invalid")])
        try await check([("HOST","synthetic.invalid"),("hOsT","synthetic.invalid")])
    }
}
