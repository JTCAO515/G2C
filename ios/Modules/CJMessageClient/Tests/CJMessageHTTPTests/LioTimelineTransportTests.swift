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

    @Test func v2UsesOnlyTheSignedConversationRoutes() async throws {
        let endpoint = try endpoint()
        let exit = LioExit()
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint,
                                                validateMessage: {}, lio: true)
        let original = try LioTimelineWire.Send(messageID: "one", text: "你好", locale: .chinese, destination: .newChat)
        let conversation = "lio-dialogue-0123456789abcdef0123456789abcdef"
        await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            _ = try await transport.send(HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/v2/lio/timeline"),
                                         body: nil, baseURL: endpoint.url, operationID: "readLioTimelineV2")
        }
        _ = try await transport.sendLio(original, bearer: "fixture")
        _ = try await transport.readLio(conversationID: conversation, before: "one+a&b", bearer: "fixture", version: .v2)
        let calls = await exit.calls
        #expect(calls.map(\.method) == [.post, .get])
        #expect(calls.map(\.path) == ["/v2/lio/messages", "/v2/lio/timeline?conversation_id=\(conversation)&before=one%2Ba%26b"])
        #expect(calls.map(\.body) == [original.originalUTF8, nil])
    }

    @Test func tripHistoryAndUndoUseOnlyTheirSignedRoutes() async throws {
        let endpoint = try endpoint()
        let exit = LioExit()
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: endpoint,
                                                validateMessage: {}, lio: true)
        let page = try LioTripHistoryWire.decodePage(Data("""
            {"version":"LIO-trip-history.1","current":{"trip_id":"trip","title":"Trip","days":[]},
             "history":[{"trip_id":"trip","title":"Earlier trip","days":[]}],
             "undo_target":"fixture_target","next_before":null}
            """.utf8))
        let undo = try LioTripHistoryWire.Undo(target: #require(page.undoTarget))

        _ = try await transport.readLioTrip(before: "2", bearer: "fixture")
        _ = try await transport.sendLioUndo(undo, bearer: "fixture")
        _ = try await transport.readLioUndo(undo, bearer: "fixture")

        let calls = await exit.calls
        #expect(calls.map(\.method) == [.get, .post, .get])
        #expect(calls.map(\.path) == ["/v1/lio/trip?before=2", "/v1/lio/trip/undo",
                                    "/v1/lio/trip/undo?action_id=\(undo.actionID)&target=fixture_target"])
        #expect(calls.map(\.body) == [nil, undo.originalUTF8, nil])
    }

    @Test func memoryDecisionAndReadbackKeepTheSameBodyAndNeverUseTheURLForTheTarget() async throws {
        let exit = LioExit()
        let memoryEndpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
            maximumRequestBytes: LioMemoryWire.maximumRequestBytes, maximumResponseBytes: 4_500_000)
        let transport = try NoRedirectTransport(interceptedTransport: exit, messageEndpoint: memoryEndpoint,
                                                validateMessage: {}, lio: true)
        let tag = try JSONDecoder().decode(LioMemoryWire.Tag.self, from: Data("""
            {"id":"fixture","kind":"preference","text":"Likes museums","target":"fixture_target"}
            """.utf8))
        let action = try LioMemoryWire.Action(choice: .remember, tag: tag)

        _ = try await transport.sendLioMemoryChoice(action, bearer: "fixture")
        _ = try await transport.readLioMemoryChoice(action, bearer: "fixture")

        let calls = await exit.calls
        #expect(calls.map(\.method) == [.post, .post])
        #expect(calls.map(\.path) == ["/v1/lio/memory/actions", "/v1/lio/memory/receipt"])
        #expect(calls.map(\.body) == [action.originalUTF8, action.originalUTF8])
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
