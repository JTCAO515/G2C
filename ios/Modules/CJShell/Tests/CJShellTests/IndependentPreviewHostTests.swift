import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP
private actor HostProbeTransport: ClientTransport {
    var calls=0
    var host:String?
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        calls+=1;host=request.headerFields[HTTPField.Name("Host")!]
        return (HTTPResponse(status:.ok),HTTPBody("{}"))
    }
}
@Suite @MainActor struct IndependentPreviewHostTests {
    @Test func ordinaryHostHeaderCannotOverrideNarrowPreviewAuthority() async throws {
        let endpoint=try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:128,maximumResponseBytes:128)
        let wire=HostProbeTransport()
        let transport=try NoRedirectTransport(interceptedTransport:wire,previewEndpoint:endpoint,validatePreview:{})
        var request=HTTPRequest(method:.post,scheme:nil,authority:nil,path:"/v1/trip-manual-previews")
        request.headerFields[.contentType]="application/json"
        request.headerFields[HTTPField.Name("Host")!]="other.invalid"
        #expect(request.authority==nil)
        await #expect(throws:(any Error).self) {try await transport.send(request,body:HTTPBody("{}"),baseURL:endpoint.url,operationID:Operations.previewManualTripEdit.id)}
        #expect(await wire.calls==0,"Conflicting ordinary Host header reached the underlying transport")
    }
}
