import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

@MainActor private final class CompletionLease {
    var active = true
    func validate() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
private struct CompletionBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let beforeChunk: @Sendable () async -> Void
    struct AsyncIterator: AsyncIteratorProtocol {
        var sent = false
        let beforeChunk: @Sendable () async -> Void
        mutating func next() async throws -> ArraySlice<UInt8>? {
            guard !sent else { return nil }; sent = true
            await beforeChunk(); return Array("{}".utf8)[...]
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(beforeChunk: beforeChunk) }
}
private actor CompletionSpy: ClientTransport {
    var count = 0
    let afterSend: @Sendable () async -> Void
    let beforeChunk: @Sendable () async -> Void
    let oversized: Bool
    init(oversized: Bool = false, afterSend: @escaping @Sendable () async -> Void = {}, beforeChunk: @escaping @Sendable () async -> Void = {}) {
        self.oversized = oversized; self.afterSend = afterSend; self.beforeChunk = beforeChunk
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        count += 1; await afterSend()
        let bytes = oversized ? HTTPBody(Data(repeating: 1, count: 4097)) : HTTPBody(CompletionBody(beforeChunk: beforeChunk), length: .unknown, iterationBehavior: .single)
        return (HTTPResponse(status: .ok), bytes)
    }
}
@MainActor struct DeviceCompletionTransportTests {
    let operation = "readCleanupDeviceCompletionV1"
    var path: String { "/v1/cleanup-device-completions/original?request_digest=" + String(repeating: "a", count: 64) }
    func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9000")), maximumRequestBytes: 4096, maximumResponseBytes: 4096, allowLoopbackHTTP: true)
    }
    func request(_ path: String) -> HTTPRequest { HTTPRequest(method: .get, scheme: nil, authority: nil, path: path) }
    @Test func onlyOriginalBoundedGETHasItsOwnCapability() async throws {
        let endpoint = try endpoint(), spy = CompletionSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, deviceCompletionEndpoint: endpoint, validateDeviceCompletion: {})
        _ = try await transport.send(request(path), body: nil, baseURL: endpoint.url, operationID: operation)
        let old = NoRedirectTransport(interceptedTransport: spy, deviceCleanupEndpoint: endpoint, validateDeviceCleanup: {})
        await #expect(throws: (any Error).self) { _ = try await old.send(request(path), body: nil, baseURL: endpoint.url, operationID: operation) }
        for invalid in [path + "&owner=other", path + "&operation_id=other", path + "&request_digest=other", path + "#fragment", "/v1/cleanup-device-completions/a/b?request_digest=" + String(repeating: "a", count: 64), path.replacingOccurrences(of: "request_digest=", with: "request_digest=B"), "/v3/cleanup-device-calls/original"] {
            await #expect(throws: (any Error).self) { _ = try await transport.send(request(invalid), body: nil, baseURL: endpoint.url, operationID: operation) }
        }
        var host = request(path); host.headerFields[HTTPField.Name("Host")!] = "other.invalid"
        await #expect(throws: (any Error).self) { _ = try await transport.send(host, body: nil, baseURL: endpoint.url, operationID: operation) }
        var post = request(path); post.method = .post
        await #expect(throws: (any Error).self) { _ = try await transport.send(post, body: nil, baseURL: endpoint.url, operationID: operation) }
        await #expect(throws: (any Error).self) { _ = try await transport.send(request(path), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: operation) }
        #expect(await spy.count == 1)
        #if !DEBUG || !targetEnvironment(simulator)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentDeviceCompletion(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test(arguments: ["before", "response", "body"])
    func replacedOwnerWithholdsEveryAsyncBoundary(stage: String) async throws {
        let endpoint = try endpoint(), lease = CompletionLease()
        if stage == "before" { lease.active = false }
        let spy = CompletionSpy(afterSend: { if stage == "response" { await MainActor.run { lease.active = false } } },
            beforeChunk: { if stage == "body" { await MainActor.run { lease.active = false } } })
        let transport = NoRedirectTransport(interceptedTransport: spy, deviceCompletionEndpoint: endpoint, validateDeviceCompletion: { try lease.validate() })
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) { _ = try await transport.send(request(path), body: nil, baseURL: endpoint.url, operationID: operation) }
        #expect(await spy.count == (stage == "before" ? 0 : 1))
    }
    @Test func responseBeyondContractIsRejected() async throws {
        let endpoint = try endpoint(), spy = CompletionSpy(oversized: true)
        let transport = NoRedirectTransport(interceptedTransport: spy, deviceCompletionEndpoint: endpoint, validateDeviceCompletion: {})
        await #expect(throws: (any Error).self) { _ = try await transport.send(request(path), body: nil, baseURL: endpoint.url, operationID: operation) }
        #expect(await spy.count == 1)
    }
}
