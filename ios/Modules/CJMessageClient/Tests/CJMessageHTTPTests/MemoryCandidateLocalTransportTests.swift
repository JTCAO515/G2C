import Foundation
import Testing
import HTTPTypes
import OpenAPIRuntime
@testable import CJMessageHTTP

@MainActor private final class CandidateExitLease {
    var active = true
    func validate() throws { guard active else { throw MessageHTTPFailure.credentialsUnavailable } }
}
private struct CandidateDelayedBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let beforeChunk: @Sendable () async -> Void
    struct AsyncIterator: AsyncIteratorProtocol {
        var sent = false
        let beforeChunk: @Sendable () async -> Void
        mutating func next() async throws -> ArraySlice<UInt8>? {
            guard !sent else { return nil }; sent = true; await beforeChunk()
            return Array("{}".utf8)[...]
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(beforeChunk: beforeChunk) }
}
private actor CandidateExitSpy: ClientTransport {
    var requests: [(String, Data?)] = []
    let after: @Sendable () async -> Void
    let beforeChunk: (@Sendable () async -> Void)?
    let responseBytes: Int
    init(after: @escaping @Sendable () async -> Void = {}, beforeChunk: (@Sendable () async -> Void)? = nil, responseBytes: Int = 2) {
        self.after = after; self.beforeChunk = beforeChunk; self.responseBytes = responseBytes
    }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let raw: Data?
        if let body { raw = try await Data(collecting: body, upTo: 1024) } else { raw = nil }
        requests.append((request.path!, raw)); await after()
        let result: HTTPBody
        if let beforeChunk { result = HTTPBody(CandidateDelayedBody(beforeChunk: beforeChunk), length: .unknown, iterationBehavior: .single) }
        else { result = HTTPBody(Data(repeating: 32, count: responseBytes)) }
        return (HTTPResponse(status: .ok), result)
    }
}
@MainActor struct MemoryCandidateLocalTransportTests {
    private func endpoint() throws -> MessageEndpoint {
        try MessageEndpoint(url: #require(URL(string: "http://127.0.0.1:9000")), maximumRequestBytes: 64, maximumResponseBytes: 64, allowLoopbackHTTP: true)
    }
    private func request(_ path: String, post: Bool = false) -> HTTPRequest {
        var request = HTTPRequest(method: post ? .post : .get, scheme: nil, authority: nil, path: path)
        if post { request.headerFields[.contentType] = "application/octet-stream" }
        return request
    }
    private var reads: [(String, String)] {
        [("/v5/memory-candidate-jobs?conversation_id=chat%2BA&after_job_id=", "readMemoryCandidateJobsV1"),
         ("/v3/memory-candidates?job_id=job&attempt_id=attempt", "readMemoryCandidatesV1"),
         ("/v3/memory-candidate-receipts?action_id=original", "queryMemoryCandidateReceiptV1")]
    }
    @Test func defaultAndReleaseWriteFactoriesStayClosed() async throws {
        let endpoint = try endpoint(), spy = CandidateExitSpy()
        let ordinary = try NoRedirectTransport(interceptedTransport: spy, previewEndpoint: nil, validatePreview: nil)
        await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            _ = try await ordinary.send(request("/v3/memory-candidate-actions", post: true), body: HTTPBody("{}".utf8), baseURL: endpoint.url, operationID: "applyMemoryCandidateActionV1")
        }
        #expect(await spy.requests.isEmpty)
        #if !DEBUG || !targetEnvironment(simulator)
        #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
            try NoRedirectTransport.developmentMemoryCandidates(endpoint: endpoint, requestTimeout: 1, resourceTimeout: 1, validate: {})
        }
        #endif
    }
    @Test func exactFourRoutesPreserveOriginalBytesAndDenyOtherAuthorities() async throws {
        let endpoint = try endpoint(), spy = CandidateExitSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryCandidateEndpoint: endpoint, validateMemoryCandidates: {})
        for (path, operation) in reads { _ = try await transport.send(request(path), body: nil, baseURL: endpoint.url, operationID: operation) }
        let raw = Data(" {\"text\":\"e\u{301} 中文\"}\n".utf8)
        _ = try await transport.send(request("/v3/memory-candidate-actions", post: true), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "applyMemoryCandidateActionV1")
        #expect(await spy.requests.compactMap(\.1) == [raw])
        for path in ["/v3/memory-history-actions", "/v1/messages", "/v2/memories", "/v1/account-cleanup-operations", "/internal/v1/memory-history/jobs", "/v3/memory-candidate-actions?owner=other"] {
            await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
                _ = try await transport.send(request(path, post: true), body: HTTPBody(raw), baseURL: endpoint.url, operationID: "applyMemoryCandidateActionV1")
            }
        }
        var authority = request(reads[0].0); authority.authority = "other.invalid"
        var host = request(reads[0].0); host.headerFields[HTTPField.Name("Host")!] = "other.invalid"
        var wrongMethod = request(reads[0].0); wrongMethod.method = .head
        for bad in [authority, host, wrongMethod] {
            await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
                _ = try await transport.send(bad, body: nil, baseURL: endpoint.url, operationID: reads[0].1)
            }
        }
        #expect(await spy.requests.count == 4)
    }
    @Test func exactQueryGrammarRejectsDuplicateMissingEncodedPathAndAmbiguousPlus() async throws {
        let endpoint = try endpoint(), spy = CandidateExitSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryCandidateEndpoint: endpoint, validateMemoryCandidates: {})
        for path in ["/v5/memory-candidate-jobs?conversation_id=x", "/v5/memory-candidate-jobs?conversation_id=x&after_job_id=&owner=x",
            "/v5/memory-candidate-jobs?conversation_id=x&conversation_id=y", "/v5/memory-candidate-jobs?conversation_id=chat+A&after_job_id=",
            "/v5/memory-candidate-jobs?conversation_id=%00&after_job_id=", "/v5/memory-candidate-jobs?conversation_id=x&after_job_id=%20",
            "/v5/memory-candidate%2Djobs?conversation_id=x&after_job_id=", "/v5/memory-candidate-jobs?conversation_id=x&after_job_id=#fragment",
            "/v1/message-history?conversation_id=x&after_job_id="] {
            await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) {
                _ = try await transport.send(request(path), body: nil, baseURL: endpoint.url, operationID: "readMemoryCandidateJobsV1")
            }
        }
        for (path, op) in [("/v3/memory-candidates?job_id=x&job_id=y", "readMemoryCandidatesV1"),
            ("/v3/memory-candidates?job_id=x&attempt_id=", "readMemoryCandidatesV1"),
            ("/v3/memory-candidate-receipts?action_id=x&owner=y", "queryMemoryCandidateReceiptV1")] {
            await #expect(throws: MessageHTTPFailure.productionActivationUnavailable) { _ = try await transport.send(request(path), body: nil, baseURL: endpoint.url, operationID: op) }
        }
        #expect(await spy.requests.isEmpty)
    }
    @Test(arguments: ["before", "send", "body"], ["discovery", "candidate", "receipt", "review"])
    func originalLeaseCheckedBeforeDispatchAfterResponseAndBody(phase: String, route: String) async throws {
        let endpoint = try endpoint(), lease = CandidateExitLease()
        let revoke: @Sendable () async -> Void = { await MainActor.run { lease.active = false } }
        let noop: @Sendable () async -> Void = {}
        let spy = CandidateExitSpy(after: phase == "send" ? revoke : noop, beforeChunk: phase == "body" ? revoke : nil)
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryCandidateEndpoint: endpoint, validateMemoryCandidates: { try lease.validate() })
        let post = route == "review"
        let path: String, operation: String
        if post { path = "/v3/memory-candidate-actions"; operation = "applyMemoryCandidateActionV1" }
        else { (path, operation) = reads[route == "discovery" ? 0 : route == "candidate" ? 1 : 2] }
        if phase == "before" { lease.active = false }
        await #expect(throws: MessageHTTPFailure.credentialsUnavailable) {
            _ = try await transport.send(request(path, post: post), body: post ? HTTPBody("{}".utf8) : nil, baseURL: endpoint.url, operationID: operation)
        }
        #expect(await spy.requests.count == (phase == "before" ? 0 : 1))
    }
    @Test func requestAndResponseBoundsDenyWithoutReencodingOrMoreDispatch() async throws {
        let endpoint = try endpoint(), spy = CandidateExitSpy()
        let transport = NoRedirectTransport(interceptedTransport: spy, memoryCandidateEndpoint: endpoint, validateMemoryCandidates: {})
        await #expect(throws: (any Error).self) {
            _ = try await transport.send(request("/v3/memory-candidate-actions", post: true), body: HTTPBody(Data(repeating: 1, count: 65)), baseURL: endpoint.url, operationID: "applyMemoryCandidateActionV1")
        }
        #expect(await spy.requests.isEmpty)
        let large = CandidateExitSpy(responseBytes: 65)
        let bounded = NoRedirectTransport(interceptedTransport: large, memoryCandidateEndpoint: endpoint, validateMemoryCandidates: {})
        await #expect(throws: (any Error).self) { _ = try await bounded.send(request(reads[0].0), body: nil, baseURL: endpoint.url, operationID: reads[0].1) }
        #expect(await large.requests.count == 1)
    }
}
