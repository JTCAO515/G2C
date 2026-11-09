import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJMessageHTTP

private actor DialogueSpy: ClientTransport {
    struct Call: Sendable {
        let path: String?
        let method: HTTPRequest.Method
        let body: Data?
    }

    private(set) var calls: [Call] = []
    let afterSend: @Sendable () async -> Void

    init(afterSend: @escaping @Sendable () async -> Void = {}) { self.afterSend = afterSend }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let data: Data?
        if let body { data = try await Data(collecting: body, upTo: 16_384) }
        else { data = nil }
        calls.append(.init(path: request.path, method: request.method, body: data))
        await afterSend()
        return (HTTPResponse(status: .ok), HTTPBody("{}".utf8))
    }
}

private actor DialogueBodyProbe {
    private(set) var reads = 0

    func next() -> ArraySlice<UInt8>? {
        guard reads < 12 else { return nil }
        reads += 1
        return Array(repeating: UInt8(32), count: 4096)[...]
    }
}

private struct DialogueProbeBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let probe: DialogueBodyProbe

    struct AsyncIterator: AsyncIteratorProtocol {
        let probe: DialogueBodyProbe
        mutating func next() async -> Element? { await probe.next() }
    }

    func makeAsyncIterator() -> AsyncIterator { .init(probe: probe) }
}

@MainActor private final class DialogueLease {
    var active = true

    func validate() throws {
        guard active else { throw MessageHTTPFailure.credentialsUnavailable }
    }
}

@MainActor struct DemoDialogueTransportTests {
    private var originalBytes: Data {
        Data(#"{"version":"DEMO-dialogue-message.1","message_id":"fixture-id","text":"  北京 / Beijing 🧳  ","locale":"zh"}"#.utf8)
    }

    private func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "https://api-beta.go2china.space")),
                            maximumRequestBytes: 16_384, maximumResponseBytes: 65_536)
    }

    private func request(_ method: HTTPRequest.Method, _ path: String) -> HTTPRequest {
        var request = HTTPRequest(method: method, scheme: nil, authority: nil, path: path)
        request.headerFields[.authorization] = "Bearer fixture-only"
        if method == .post { request.headerFields[.contentType] = "application/octet-stream" }
        return request
    }

    @Test func onlyExactBetaSubmitAndReadAreAcceptedByTheFixture() async throws {
        let endpoint = try endpoint(), spy = DialogueSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, demoDialogueEndpoint: endpoint, validateDemoDialogue: {})
        let post = request(.post, DemoDialogueRoute.path)
        let get = request(.get, DemoDialogueRoute.path + "?message_id=fixture%2Bid")
        _ = try await transport.send(post, body: HTTPBody(originalBytes), baseURL: endpoint.url, operationID: DemoDialogueRoute.submit)
        _ = try await transport.send(get, body: nil, baseURL: endpoint.url, operationID: DemoDialogueRoute.original)
        let calls = await spy.calls
        #expect(calls.count == 2)
        #expect(calls.first?.method == .post && calls.first?.body == originalBytes)
        #expect(calls.last?.method == .get && calls.last?.body == nil)
        #expect(calls.last?.path == get.path)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.demoDialogueMessages(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
    }

    @Test func legacyRoutesAndSmuggledSelectorsAreRejectedBeforeDispatch() async throws {
        let endpoint = try endpoint(), spy = DialogueSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, demoDialogueEndpoint: endpoint, validateDemoDialogue: {})
        let route = DemoDialogueRoute.path
        for path in ["/v1/message-receipts?message_id=fixture-id", route + "?message_id=a&message_id=b",
                     route + "?message_id=a&owner=other", route + "?message_id=", route + "?message_id=a#fragment",
                     route + "?message_id=a+b", "/%761/demo-dialogue/messages?message_id=fixture-id"] {
            await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
                _ = try await transport.send(request(.get, path), body: nil, baseURL: endpoint.url, operationID: DemoDialogueRoute.original)
            }
        }
        var foreignHost = request(.post, route)
        foreignHost.headerFields[HTTPField.Name("Host")!] = "foreign.example"
        await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            _ = try await transport.send(foreignHost, body: HTTPBody(originalBytes), baseURL: endpoint.url, operationID: DemoDialogueRoute.submit)
        }
        let invalid = [
            #"{"version":"DEMO-dialogue-message.1","message_id":"a","text":"hi","locale":"zh","travel_id":"x"}"#,
            #"{"version":"DEMO-dialogue-message.1","message_id":"a","text":"hi","locale":"zh-Hans"}"#,
            #"{"version":"DEMO-dialogue-message.1","message_id":"a","text":"hi","locale":"en","new_conversation":1}"#,
            #"{"version":"DEMO-dialogue-message.1","message_id":"a","text":"hi","locale":"en","new_conversation":true,"conversation_id":"demo-dialogue-00000000000000000000000000000000"}"#,
            #"{"version":"DEMO-dialogue-message.1","message_id":"a","message_id":"b","text":"hi","locale":"en"}"#
        ]
        for raw in invalid {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(request(.post, route), body: HTTPBody(raw.utf8), baseURL: endpoint.url, operationID: DemoDialogueRoute.submit)
            }
        }
        #expect(await spy.calls.isEmpty)
    }

    @Test func oversizedStreamStopsAtTheDialogueBoundBeforeDispatch() async throws {
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://api-beta.go2china.space")),
                                           maximumRequestBytes: 1_000_000, maximumResponseBytes: 65_536)
        let spy = DialogueSpy(), probe = DialogueBodyProbe()
        let transport = NoRedirectTransport(interceptedTransport: spy, demoDialogueEndpoint: endpoint, validateDemoDialogue: {})
        let body = HTTPBody(DialogueProbeBody(probe: probe), length: .unknown, iterationBehavior: .single)
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(.post, DemoDialogueRoute.path), body: body,
                                         baseURL: endpoint.url, operationID: DemoDialogueRoute.submit)
        }
        #expect(await probe.reads == 5)
        #expect(await spy.calls.isEmpty)
    }

    @Test(arguments: [false, true])
    func changedLeaseRejectsResponseOnBothRoutes(submitting: Bool) async throws {
        let endpoint = try endpoint(), lease = DialogueLease()
        let spy = DialogueSpy(afterSend: { await MainActor.run { lease.active = false } })
        let transport = NoRedirectTransport(interceptedTransport: spy, demoDialogueEndpoint: endpoint, validateDemoDialogue: { try lease.validate() })
        let request = submitting ? request(.post, DemoDialogueRoute.path) : request(.get, DemoDialogueRoute.path + "?message_id=fixture-id")
        let body = submitting ? HTTPBody(originalBytes) : nil
        let operation = submitting ? DemoDialogueRoute.submit : DemoDialogueRoute.original
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request, body: body, baseURL: endpoint.url, operationID: operation)
        }
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request, body: body, baseURL: endpoint.url, operationID: operation)
        }
        #expect(await spy.calls.count == 1)
    }
}
