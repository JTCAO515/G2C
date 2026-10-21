import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import SpikeClient

struct FixtureTransport: ClientTransport {
    let status: Int
    let contentType: String
    let bytes: String
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        (HTTPResponse(status: .init(code: status), headerFields: [.contentType: contentType]), HTTPBody(bytes))
    }
}
func fixture(_ bytes: String, status: Int = 200, type: String = "application/json") -> Client {
    Client(serverURL: URL(string: "https://cj004.invalid")!, transport: FixtureTransport(status: status, contentType: type, bytes: bytes))
}
@Test func completeStream() async throws {
    let client = fixture("data: 北京\n\ndata: Shanghai\n\ndata: [DONE]\n\n", type: "text/event-stream")
    #expect(try await TransportProbe.stream(client: client) == ["北京", "Shanghai"])
}
@Test func silentStreamEOFFails() async throws {
    do {
        _ = try await TransportProbe.stream(client: fixture("data: partial\n\n", type: "text/event-stream"))
        Issue.record("Interrupted stream became success")
    } catch let failure as ProbeFailure { #expect(failure == .interrupted) }
}
@Test func emptyStreamFails() async {
    await #expect(throws: ProbeFailure.interrupted) {
        _ = try await TransportProbe.stream(client: fixture("", type: "text/event-stream"))
    }
}

private struct BrokenStreamTransport: ClientTransport {
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let stream = AsyncThrowingStream<HTTPBody.ByteChunk, any Error> { continuation in
            continuation.yield(ArraySlice("data: partial\n\n".utf8))
            continuation.finish(throwing: URLError(.networkConnectionLost))
        }
        return (HTTPResponse(status: .ok, headerFields: [.contentType: "text/event-stream"]), HTTPBody(stream, length: .unknown))
    }
}
@Test func bodyTransportFailureDoesNotComplete() async {
    let client = Client(serverURL: URL(string: "https://cj004.invalid")!, transport: BrokenStreamTransport())
    await #expect(throws: (any Error).self) { _ = try await TransportProbe.stream(client: client) }
}
@Test func cancellationDoesNotComplete() async {
    let task = Task {
        try Task.checkCancellation()
        return try await TransportProbe.stream(client: fixture("data: [DONE]\n\n", type: "text/event-stream"))
    }
    task.cancel()
    do { _ = try await task.value; Issue.record("Cancellation became completion") }
    catch { #expect(error is CancellationError) }
}
