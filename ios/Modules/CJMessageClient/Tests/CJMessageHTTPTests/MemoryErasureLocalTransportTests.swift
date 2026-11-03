import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

@MainActor private final class ErasureExitLease {
    var active = true
    func validate() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
private struct ErasureExitBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let callback: @Sendable () async -> Void
    struct AsyncIterator: AsyncIteratorProtocol {
        let callback: @Sendable () async -> Void
        var sent = false
        mutating func next() async throws -> ArraySlice<UInt8>? {
            guard !sent else { return nil }; sent = true; await callback(); return Array("{}".utf8)[...]
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(callback: callback) }
}
private actor ErasureExitSpy: ClientTransport {
    var requests: [(String, Data?)] = []
    let sent: @Sendable () async -> Void
    let body: @Sendable () async -> Void
    init(sent: @escaping @Sendable () async -> Void = {}, body: @escaping @Sendable () async -> Void = {}) { self.sent = sent; self.body = body }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let raw: Data?
        if let body { raw = try await Data(collecting: body, upTo: 1024) } else { raw = nil }
        requests.append((request.path!, raw)); await sent()
        return (HTTPResponse(status: .ok), HTTPBody(ErasureExitBody(callback: self.body), length: .unknown, iterationBehavior: .single))
    }
}
@MainActor struct MemoryErasureLocalTransportTests {
    private func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9000")), maximumRequestBytes: 64, maximumResponseBytes: 64, allowLoopbackHTTP: true)
    }
    private func request(_ path: String, post: Bool = false) -> HTTPRequest {
        var result = HTTPRequest(method: post ? .post : .get, scheme: nil, authority: nil, path: path)
        if post { result.headerFields[.contentType] = "application/octet-stream" }; return result
    }
    @Test func exactTwoExitsPreserveOriginalAndDenyAccountHistoryAndArbitraryHost() async throws {
        let endpoint = try endpoint(), spy = ErasureExitSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryErasureEndpoint: endpoint, validateMemoryErasure: {})
        let raw = Data(" {\"item\":\"e\u{301} 中文\"}\n".utf8)
        _ = try await transport.send(request("/v1/memory-erasures", post: true), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "eraseMemoryV1")
        _ = try await transport.send(request("/v1/memory-erasure-progress?action_id=original"), body: nil, baseURL: endpoint.url, operationID: "readMemoryErasureProgressV1")
        #expect(await spy.requests.compactMap(\.1) == [raw])
        for path in ["/v1/account-cleanup-operations", "/v1/memories", "/v3/memory-history-actions", "/v3/memory-candidate-actions", "/v1/memory-erasures?owner=other"] {
            await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
                _ = try await transport.send(request(path, post: true), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "eraseMemoryV1")
            }
        }
        for path in ["/v1/memory-erasure-progress?action_id=x&owner=y", "/v1/memory-erasure-progress?action_id=x&action_id=y",
            "/v1/memory-erasure-progress?action_id=", "/v1/memory-erasure-progress?action_id=%00", "/v1/memory-erasure-progress?action_id=x+y",
            "/v1/memory-erasure-progress?action_id=x#fragment", "/v1/memory-erasure%2Dprogress?action_id=x"] {
            await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
                _ = try await transport.send(request(path), body: nil, baseURL: endpoint.url, operationID: "readMemoryErasureProgressV1")
            }
        }
        var host = request("/v1/memory-erasures", post: true); host.headerFields[HTTPField.Name("Host")!] = "other.invalid"
        await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            _ = try await transport.send(host, body: HTTPBody(raw), baseURL: endpoint.url, operationID: "eraseMemoryV1")
        }
        #expect(await spy.requests.count == 2)
    }
    @Test(arguments: ["before", "send", "body"], [false, true])
    func bothExitsCheckScopeBeforeDispatchAfterResponseAndCollection(phase: String, post: Bool) async throws {
        let endpoint = try endpoint(), lease = ErasureExitLease()
        let revoke: @Sendable () async -> Void = { await MainActor.run { lease.active = false } }
        let noop: @Sendable () async -> Void = {}
        let spy = ErasureExitSpy(sent: phase == "send" ? revoke : noop, body: phase == "body" ? revoke : noop)
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryErasureEndpoint: endpoint, validateMemoryErasure: { try lease.validate() })
        if phase == "before" { lease.active = false }
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request(post ? "/v1/memory-erasures" : "/v1/memory-erasure-progress?action_id=original", post: post),
                body: post ? HTTPBody("{}".utf8) : nil, baseURL: endpoint.url, operationID: post ? "eraseMemoryV1" : "readMemoryErasureProgressV1")
        }
        #expect(await spy.requests.count == (phase == "before" ? 0 : 1))
    }
    @Test func fullUnicodeOriginalQueryIsSupportedButOversizedWriteAndOrdinaryFactoryStayClosed() async throws {
        let endpoint = try endpoint(), spy = ErasureExitSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryErasureEndpoint: endpoint, validateMemoryErasure: {})
        var path = URLComponents(); path.path = "/v1/memory-erasure-progress"
        path.queryItems = [.init(name: "action_id", value: String(repeating: "😀", count: 4096))]
        _ = try await transport.send(request(try #require(path.string)), body: nil, baseURL: endpoint.url, operationID: "readMemoryErasureProgressV1")
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request("/v1/memory-erasures", post: true), body: HTTPBody(Data(repeating: 1, count: 65)), baseURL: endpoint.url, operationID: "eraseMemoryV1")
        }
        let ordinary = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            _ = try await ordinary.send(request("/v1/memory-erasures", post: true), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "eraseMemoryV1")
        }
        #expect(await spy.requests.count == 1)
        #if !DEBUG || !targetEnvironment(simulator)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentMemoryErasure(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
}
