import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
import CJAPI
@testable import CJMessageHTTP

private actor MemoryHistoryExitSpy: ClientTransport {
    var bodies: [Data] = []
    let after: @Sendable () async -> Void
    init(after: @escaping @Sendable () async -> Void = {}) { self.after = after }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        if let body { bodies.append(try await Data(collecting: body, upTo: 1024)) }
        await after()
        return (HTTPResponse(status: .ok), HTTPBody("{}".utf8))
    }
}
@MainActor private final class MemoryHistoryExitLease {
    var active = true
    func validate() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
@MainActor struct MemoryHistoryLocalTransportTests {
    func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9000")),
                            maximumRequestBytes: 64, maximumResponseBytes: 64, allowLoopbackHTTP: true)
    }
    func request(_ path: String = "/v3/memory-history-actions") -> HTTPRequest {
        var result = HTTPRequest(method: .post, scheme: nil, authority: nil, path: path)
        result.headerFields[.contentType] = "application/octet-stream"
        return result
    }
    @Test func ordinaryAndNonSimulatorFactoriesRemainClosed() async throws {
        let spy = MemoryHistoryExitSpy(), endpoint = try endpoint()
        let transport = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "applyMemoryHistoryActionV1")
        }
        #expect(await spy.bodies.isEmpty)
        #if !DEBUG || !targetEnvironment(simulator)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentMemoryHistory(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test func exactMemoryHistoryExitPreservesBytesAndDeniesAdjacentCapabilities() async throws {
        let spy = MemoryHistoryExitSpy(), lease = MemoryHistoryExitLease(), endpoint = try endpoint()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryHistoryEndpoint: endpoint, validateHistory: { try lease.validate() })
        let bytes = Data(" {\"text\":\"e\u{301}\"}\n".utf8)
        _ = try await transport.send(request(), body: HTTPBody(bytes), baseURL: endpoint.url, operationID: "applyMemoryHistoryActionV1")
        #expect(await spy.bodies == [bytes])
        for (path, op) in [("/v1/messages", Operations.receiveMessage.id), ("/v1/memories", Operations.saveMemory.id),
                           ("/internal/v1/memory-history/jobs", "applyMemoryHistoryActionV1"), ("/v3/memory-candidate-actions", "applyMemoryHistoryActionV1"), ("/v3/memory-history-actions?owner=other", "applyMemoryHistoryActionV1"),
                           ("/v3/memory-history-actions", Operations.receiveMessage.id)] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(request(path), body: HTTPBody(bytes), baseURL: endpoint.url, operationID: op)
            }
        }
        var authority = request(); authority.authority = "other.invalid"
        var host = request(); host.headerFields[HTTPField.Name("Host")!] = "other.invalid"
        var media = request(); media.headerFields[.contentType] = "application/json"
        for bad in [authority, host, media] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(bad, body: HTTPBody(bytes), baseURL: endpoint.url, operationID: "applyMemoryHistoryActionV1")
            }
        }
        #expect(await spy.bodies.count == 1)
    }
    @Test func lateLeaseChangeAndBoundsWithholdFurtherOutflow() async throws {
        let endpoint = try endpoint(), lease = MemoryHistoryExitLease()
        let spy = MemoryHistoryExitSpy(after: { await MainActor.run { lease.active = false } })
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryHistoryEndpoint: endpoint, validateHistory: { try lease.validate() })
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "applyMemoryHistoryActionV1")
        }
        #expect(await spy.bodies.count == 1)
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "applyMemoryHistoryActionV1")
        }
        lease.active = true
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(), body: HTTPBody(Data(repeating: 1, count: 65)), baseURL: endpoint.url, operationID: "applyMemoryHistoryActionV1")
        }
        #expect(await spy.bodies.count == 1)
    }
}
