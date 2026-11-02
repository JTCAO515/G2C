import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

@MainActor private final class CleanupExitLease {
    var active = true
    func validate() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
private struct CleanupDelayedBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let beforeChunk: @Sendable () async -> Void
    struct AsyncIterator: AsyncIteratorProtocol {
        var sent = false
        let beforeChunk: @Sendable () async -> Void
        mutating func next() async throws -> ArraySlice<UInt8>? {
            guard !sent else { return nil }; sent = true
            await beforeChunk()
            return Array("{}".utf8)[...]
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(beforeChunk: beforeChunk) }
}
private actor CleanupExitSpy: ClientTransport {
    var requests: [(String, Data?)] = []
    let afterSend: @Sendable () async -> Void
    let beforeChunk: (@Sendable () async -> Void)?
    init(afterSend: @escaping @Sendable () async -> Void = {}, beforeChunk: (@Sendable () async -> Void)? = nil) {
        self.afterSend = afterSend; self.beforeChunk = beforeChunk
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 1024) } else { bytes = nil }
        requests.append((request.path!, bytes))
        await afterSend()
        let response: HTTPBody
        if let beforeChunk { response = HTTPBody(CleanupDelayedBody(beforeChunk: beforeChunk), length: .unknown, iterationBehavior: .single) }
        else { response = HTTPBody("{}".utf8) }
        return (HTTPResponse(status: .ok), response)
    }
}
@MainActor struct AccountCleanupLocalTransportTests {
    private func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9000")), maximumRequestBytes: 64,
            maximumResponseBytes: 64, allowLoopbackHTTP: true)
    }
    private func request(_ path: String, get: Bool = false) -> HTTPRequest {
        var request = HTTPRequest(method: get ? .get : .post, scheme: nil, authority: nil, path: path)
        if !get { request.headerFields[.contentType] = "application/octet-stream" }
        return request
    }
    @Test func ordinaryPostAndNonSimulatorFactoryRemainClosed() async throws {
        let spy = CleanupExitSpy(), endpoint = try endpoint()
        let ordinary = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        await #expect(throws: (any Error).self) {
            _ = try await ordinary.send(request("/v1/account-cleanup-operations"), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "prepareAccountCleanupV1")
        }
        #expect(await spy.requests.isEmpty)
        #if !DEBUG || !targetEnvironment(simulator)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentAccountCleanup(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test func exactFiveRoutesPreserveBytesAndDoNotGrantDeviceHookWrites() async throws {
        let spy = CleanupExitSpy(), endpoint = try endpoint(), lease = CleanupExitLease()
        let transport = NoRedirectTransport(interceptedTransport: spy, accountCleanupEndpoint: endpoint, validateAccountCleanup: { try lease.validate() })
        let original = Data(" {\"text\":\"e\u{301}\"}\n".utf8)
        for (path, operation) in [("/v1/cleanup-devices", "registerCleanupDeviceV1"),
            ("/v1/account-cleanup-operations", "prepareAccountCleanupV1"),
            ("/v1/account-cleanup-operations/original/confirmation", "confirmAccountCleanupV1")] {
            _ = try await transport.send(request(path), body: HTTPBody(original), baseURL: endpoint.url, operationID: operation)
        }
        for (path, operation) in [("/v1/account-cleanup-preparations?action_id=original", "queryAccountCleanupPreparationV1"),
            ("/v1/account-cleanup-operations/original", "readOriginalAccountCleanupV1")] {
            _ = try await transport.send(request(path, get: true), body: nil, baseURL: endpoint.url, operationID: operation)
        }
        #expect(await spy.requests.compactMap(\.1) == [original, original, original])
        for (path, operation) in [("/v1/cleanup-device-calls", "prepareAccountCleanupV1"),
            ("/v1/cleanup-device-receipts", "confirmAccountCleanupV1"),
            ("/v1/messages", "prepareAccountCleanupV1"),
            ("/v1/account-cleanup-operations?owner=other", "prepareAccountCleanupV1"),
            ("/v1/account-cleanup-operations/original/confirmation?owner=other", "confirmAccountCleanupV1")] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(request(path), body: HTTPBody(original), baseURL: endpoint.url, operationID: operation)
            }
        }
        for path in ["/v1/account-cleanup-operations/original?owner=other", "/v1/account-cleanup-operations/original#fragment",
            "/v1/account-cleanup-operations/unescaped/slash", "/v1/account-cleanup-progress?operation_id=original"] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(request(path, get: true), body: nil, baseURL: endpoint.url, operationID: "readOriginalAccountCleanupV1")
            }
        }
        #expect(await spy.requests.count == 5)
    }
    @Test(arguments: ["before", "send", "body"], ["read", "query", "confirm"])
    func originalLeaseIsCheckedBeforeDispatchAfterResponseAndBody(phase: String, operation: String) async throws {
        let lease = CleanupExitLease(), endpoint = try endpoint()
        let revoke: @Sendable () async -> Void = { await MainActor.run { lease.active = false } }
        let noop: @Sendable () async -> Void = {}
        let spy = CleanupExitSpy(afterSend: phase == "send" ? revoke : noop, beforeChunk: phase == "body" ? revoke : nil)
        let transport = NoRedirectTransport(interceptedTransport: spy, accountCleanupEndpoint: endpoint, validateAccountCleanup: { try lease.validate() })
        if phase == "before" { lease.active = false }
        let path: String; let id: String; let post: Bool
        switch operation {
        case "read": path = "/v1/account-cleanup-operations/original"; id = "readOriginalAccountCleanupV1"; post = false
        case "query": path = "/v1/account-cleanup-preparations?action_id=original"; id = "queryAccountCleanupPreparationV1"; post = false
        default: path = "/v1/account-cleanup-operations/original/confirmation"; id = "confirmAccountCleanupV1"; post = true
        }
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request(path, get: !post), body: post ? HTTPBody("{}".utf8) : nil, baseURL: endpoint.url, operationID: id)
        }
        #expect(await spy.requests.count == (phase == "before" ? 0 : 1))
    }
    @Test func wrongHostMethodsMediaBoundsAndRequestBodyCallbackDoNotDispatch() async throws {
        let lease = CleanupExitLease(), spy = CleanupExitSpy(), endpoint = try endpoint()
        let transport = NoRedirectTransport(interceptedTransport: spy, accountCleanupEndpoint: endpoint, validateAccountCleanup: { try lease.validate() })
        let target = "/v1/account-cleanup-operations"
        var authority = request(target); authority.authority = "other.invalid"
        var host = request(target); host.headerFields[HTTPField.Name("Host")!] = "other.invalid"
        var media = request(target); media.headerFields[.contentType] = "application/json"
        var method = request(target); method.method = .delete
        for bad in [authority, host, media, method] {
            await #expect(throws: (any Error).self) {
                _ = try await transport.send(bad, body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "prepareAccountCleanupV1")
            }
        }
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request(target), body: HTTPBody(Data(repeating: 1, count: 65)), baseURL: endpoint.url, operationID: "prepareAccountCleanupV1")
        }
        let changingBody = HTTPBody(CleanupDelayedBody(beforeChunk: { await MainActor.run { lease.active = false } }), length: .unknown, iterationBehavior: .single)
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request(target), body: changingBody, baseURL: endpoint.url, operationID: "prepareAccountCleanupV1")
        }
        #expect(await spy.requests.isEmpty)
    }
}
