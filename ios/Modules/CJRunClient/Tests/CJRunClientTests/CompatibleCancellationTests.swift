import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJMessageHTTP
@testable import CJRunClient

private actor CancellationWireProbe: ClientTransport {
    var calls: [(String,String)] = []
    func send(_ request: HTTPRequest,body: HTTPBody?,baseURL: URL,operationID: String) async throws -> (HTTPResponse,HTTPBody?) {
        calls.append((operationID,request.path ?? ""))
        return (HTTPResponse(status:.ok),HTTPBody("{}".utf8))
    }
}
@MainActor struct CompatibleCancellationTests {
    /// L0 transport admission only: the interceptor is non-network and its
    /// response is not interpreted as an authenticated cancellation receipt.
    @Test(arguments:["legacy","travel","compatible"])
    func onlyExplicitModesDispatchTheOriginalWire(_ mode: String) async throws {
        let endpoint = try MessageEndpoint(url:#require(URL(string:"https://synthetic.invalid")),maximumRequestBytes:65536,maximumResponseBytes:65536)
        let wire = CancellationWireProbe()
        let transport = RunCancellationTransport(interceptedTransport:wire,endpoint:endpoint,travel:mode == "travel",compatible:mode == "compatible",validate:{})
        for travel in [false,true] {
            let path = travel ? "/v2/run-cancellations" : "/v1/run-cancellations"
            let operation = travel ? "cancelOriginalTravelRun" : "cancelOriginalRun"
            var request = HTTPRequest(method:.post,scheme:nil,authority:nil,path:path)
            request.headerFields[.contentType] = "application/json"
            let bytes = Data((travel ? "{\"version\":\"RUN-cancel.2\",\"message_id\":\"original\"}" : "{\"message_id\":\"original\"}").utf8)
            let allowed = mode == "compatible" || (travel ? mode == "travel" : mode == "legacy")
            if allowed {
                _ = try await transport.sendBound(request,body:HTTPBody(bytes),baseURL:endpoint.url,operationID:operation,validateOriginal:{})
            } else {
                await #expect(throws:RunDisplayFailure.invalidReference) {
                    try await transport.sendBound(request,body:HTTPBody(bytes),baseURL:endpoint.url,operationID:operation,validateOriginal:{})
                }
            }
            var mismatched = request;mismatched.path = travel ? "/v1/run-cancellations" : "/v2/run-cancellations"
            await #expect(throws:RunDisplayFailure.invalidReference) {
                try await transport.sendBound(mismatched,body:HTTPBody(bytes),baseURL:endpoint.url,operationID:operation,validateOriginal:{})
            }
            await #expect(throws:RunDisplayFailure.invalidReference) {
                try await transport.send(request,body:HTTPBody(bytes),baseURL:endpoint.url,operationID:operation)
            }
        }
        let actual = await wire.calls.map(\.0)
        let expected = mode == "compatible" ? ["cancelOriginalRun","cancelOriginalTravelRun"] : mode == "legacy" ? ["cancelOriginalRun"] : ["cancelOriginalTravelRun"]
        #expect(actual == expected)
    }
}
