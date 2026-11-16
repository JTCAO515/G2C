import CJMessageClient
@testable import CJMessageHTTP
import Foundation
import HTTPTypes
import OpenAPIRuntime
import Testing
@testable import CJLioUser

@MainActor private final class FailureScope: MessageCredentialsProvider, SecureMessageStorage {
    var active = true
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
    func load(scope: StorageScope) throws -> Snapshot? { nil }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws {}
    func validate() throws { if !active { throw RecoveryError.inactive } }
}
private actor FailureBodyGate {
    private var arrival: Bool?
    private var arrivalWaiter: CheckedContinuation<Bool, Never>?
    private var continuation: CheckedContinuation<Void, Never>?

    func waitForBody() async -> Bool {
        if let arrival { return arrival }
        return await withCheckedContinuation { arrivalWaiter = $0 }
    }

    func wait() async {
        arrival = true
        arrivalWaiter?.resume(returning: true); arrivalWaiter = nil
        await withCheckedContinuation { continuation = $0 }
    }

    func requestFinished() {
        guard arrival == nil else { return }
        arrival = false
        arrivalWaiter?.resume(returning: false); arrivalWaiter = nil
    }

    func release() { continuation?.resume(); continuation = nil }
}

private struct DelayedFailureBody: AsyncSequence, Sendable {
    typealias Element = ArraySlice<UInt8>
    let gate: FailureBodyGate
    struct AsyncIterator: AsyncIteratorProtocol {
        let gate: FailureBodyGate
        var sent = false
        mutating func next() async throws -> ArraySlice<UInt8>? {
            guard !sent else { return nil }; sent = true
            await gate.wait()
            return Array("{}".utf8)[...]
        }
    }
    func makeAsyncIterator() -> AsyncIterator { .init(gate: gate) }
}
private actor ConcurrentFailureTransport: ClientTransport {
    let gate: FailureBodyGate
    init(gate: FailureBodyGate) { self.gate = gate }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let first = request.path?.contains("before=first") == true
        var response = HTTPResponse(status: first ? .ok : .serviceUnavailable)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = first
            ? "B95744FC-F460-4ED1-B21B-A64D5D34896C" : "C95744FC-F460-4ED1-B21B-A64D5D34896C"
        return (response, first ? HTTPBody(DelayedFailureBody(gate: gate), length: .unknown, iterationBehavior: .single) : HTTPBody("{}"))
    }
}
@MainActor struct LioConcurrentFailureTests {
    @Test func overlappingReadsKeepTheirOwnResponseReference() async throws {
        let scope = try StorageScope(environment: "synthetic-overlap", account: "synthetic-owner")
        let boundary = FailureScope(), gate = FailureBodyGate()
        let recovery = MessageRecovery(storage: boundary), lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")),
                                           maximumRequestBytes: 16384, maximumResponseBytes: 65536)
        let transport = try NoRedirectTransport(interceptedTransport: ConcurrentFailureTransport(gate: gate),
            messageEndpoint: endpoint, validateMessage: { try boundary.validate() }, lio: true)
        let client = LioTimelineHTTP(scope: scope, lease: lease, credentials: boundary, transport: transport)
        let service = LioService.signedTimeline(client)
        let earlier = try #require(service.earlier)
        let first = Task { () -> LioRequestProblem? in
            let problem: LioRequestProblem?
            do { _ = try await earlier("first"); Issue.record("Expected local revocation"); problem = nil }
            catch { problem = error as? LioRequestProblem }
            await gate.requestFinished()
            return problem
        }
        guard await gate.waitForBody() else {
            _ = await first.value
            Issue.record("First request finished before its response body arrived")
            return
        }
        do { _ = try await earlier("second"); Issue.record("Expected HTTP 503") }
        catch {
            let problem = try #require(error as? LioRequestProblem)
            #expect(problem.diagnosis.httpStatus == 503)
            #expect(problem.diagnosis.serverReference == "C95744FC-F460-4ED1-B21B-A64D5D34896C")
        }
        boundary.active = false
        await gate.release()
        let problem = try #require(await first.value)
        #expect(problem.cause == .inactiveSession)
        #expect(problem.diagnosis.httpStatus == 200)
        #expect(problem.diagnosis.serverReference == "B95744FC-F460-4ED1-B21B-A64D5D34896C")
    }
}
