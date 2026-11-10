import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJMessageHTTP

@MainActor
struct LioTimelineTransportTests {
    @Test func scopedTransportPreservesTheWriteAndEscapesTheReadCursor() async throws {
        let endpoint = try endpoint()
        let exit = LioExit()
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint,
                                                validateMessage: {}, lio: true)
        let original = try LioTimelineWire.Send(messageID: "one", text: "你好", locale: .chinese)

        _ = try await transport.sendLio(original, bearer: "fixture")
        _ = try await transport.readLio(conversationID: nil, before: "one+a&b", bearer: "fixture")

        let calls = await exit.calls
        #expect(calls.map(\.method) == [.post, .get])
        #expect(calls.map(\.path) == ["/v1/lio/messages", "/v1/lio/timeline?before=one%2Ba%26b"])
        #expect(calls.map(\.body) == [original.originalUTF8, nil])
        #expect(calls.map(\.contentType) == ["application/octet-stream", nil])
    }

    @Test func refusesUnscopedRoutesAndARevokedLease() async throws {
        let endpoint = try endpoint()
        let exit = LioExit()
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.lioTimeline(endpoint: endpoint, validate: {})
        }
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint,
            validateMessage: { throw MessageHTTPFailure.credentialsUnavailable }, lio: true)
        await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            _ = try await transport.send(HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/v1/lio/timeline"),
                                         body: nil, baseURL: endpoint.url, operationID: "readLioTimelineV1")
        }
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.readLio(conversationID: nil, before: nil, bearer: "fixture")
        }
        #expect(await exit.calls.isEmpty)
    }

    private func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                            maximumRequestBytes: 16_384, maximumResponseBytes: 4_500_000)
    }
}

private actor LioExit: ClientTransport {
    struct Call: Sendable {
        let method: HTTPRequest.Method
        let path: String?
        let body: Data?
        let contentType: String?
    }

    private(set) var calls: [Call] = []

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes = if let body { try await Data(collecting: body, upTo: 16_384) } else { nil as Data? }
        calls.append(Call(method: request.method, path: request.path, body: bytes,
                          contentType: request.headerFields[.contentType]))
        return (HTTPResponse(status: .ok), HTTPBody("{}"))
    }
}
