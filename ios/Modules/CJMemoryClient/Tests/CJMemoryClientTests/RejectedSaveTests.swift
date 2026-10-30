import Foundation
import Testing
import CJAPI
import OpenAPIRuntime
import HTTPTypes
@testable import CJMemoryClient

private actor RejectionTransport: ClientTransport {
    var posts: [Data] = []
    let outcome: String
    let denyQueries: Bool
    init(outcome: String = "failed", denyQueries: Bool = false) { self.outcome = outcome; self.denyQueries = denyQueries }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let status: HTTPResponse.Status
        let json: String
        if operationID == "saveMemory" {
            let originalBody = try #require(body)
            let bytes = try await Data(collecting: originalBody, upTo: 100_000)
            posts.append(bytes)
            if posts.count == 1 {
                status = .forbidden
                json = "{\"request_id\":\"\(trace)\",\"error\":{\"code\":\"MEMORY_SOURCE_DENIED\",\"category\":\"access\",\"message_en\":\"Denied\",\"message_zh\":\"拒绝\",\"outcome\":\"\(outcome)\",\"recovery\":\"do_not_retry\"}}"
            } else {
                status = .ok; json = try receipt(bytes)
            }
        } else if denyQueries {
            status = .forbidden
            json = "{\"request_id\":\"\(trace)\",\"error\":{\"code\":\"MEMORY_SOURCE_DENIED\",\"category\":\"access\",\"message_en\":\"Denied\",\"message_zh\":\"拒绝\",\"outcome\":\"failed\",\"recovery\":\"do_not_retry\"}}"
        } else {
            status = .ok; json = "{\"request_id\":\"\(trace)\",\"receipt\":null}"
        }
        var response = HTTPResponse(status: status)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response, HTTPBody(json.utf8))
    }
}

@Suite @MainActor struct RejectedSaveTests {
    private func client(_ f: Fixture, _ transport: RejectionTransport) throws -> MemoryClient {
        try MemoryClient(endpoint: f.endpoint, credentials: { _ in "test-credential" },
            currentBinding: { f.current }, pendingStore: f.store(), interceptedTransport: transport)
    }
    @Test func definiteFailureSurvivesReopenAndAllowsOnlyDistinctNewAction() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = RejectionTransport()
        let old = command("explicitly rejected original")
        let first = try client(f, transport)
        await #expect(throws: MemoryFailure.rejected(403, "MEMORY_SOURCE_DENIED")) { try await first.save(old, binding: f.binding) }
        let oldFile = f.root.appendingPathComponent(digest(Data(old.operation_id.utf8)) + ".memory")
        let ciphertext = try Data(contentsOf: oldFile)
        let reopened = try client(f, transport)
        guard case .rejected(403, "MEMORY_SOURCE_DENIED") = try await reopened.query(operationID: old.operation_id, binding: f.binding) else {
            Issue.record("definite failure became unknown or saved"); return
        }
        var next = command("distinct corrected input"); next.slot = "allowed"
        guard case .saved = try await reopened.save(next, binding: f.binding) else { Issue.record("new action blocked"); return }
        #expect(try Data(contentsOf: oldFile) == ciphertext)
        let originals = try f.store().pending()
        #expect(originals.count == 2)
        let originalBytes = try MemoryPending(old).originalUTF8
        #expect(originals.contains { $0.operationID == old.operation_id && $0.originalUTF8 == originalBytes })
        await #expect(throws: MemoryFailure.storageUnavailable) { try await reopened.save(old, binding: f.binding) }
        #expect(await transport.posts.count == 2)
    }
    @Test(arguments: ["unknown", "partial"]) func uncertainOutcomeNeverCreatesDefiniteFailure(_ outcome: String) async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = RejectionTransport(outcome: outcome)
        let original = command(); let first = try client(f, transport)
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await first.save(original, binding: f.binding) }
        let reopened = try client(f, transport)
        guard case .notObserved = try await reopened.query(operationID: original.operation_id, binding: f.binding) else { Issue.record("unknown settled"); return }
        await #expect(throws: MemoryFailure.pendingRequiresQuery) { try await reopened.save(command(), binding: f.binding) }
        #expect(await transport.posts.count == 1)
        #expect(!FileManager.default.fileExists(atPath: f.root.appendingPathExtension("CJMemoryRejections").path))
    }
    @Test func deniedReadCannotTurnUnknownWriteIntoDefiniteFailure() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = RejectionTransport(outcome: "unknown", denyQueries: true)
        let original = command(); let first = try client(f, transport)
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await first.save(original, binding: f.binding) }
        let reopened = try client(f, transport)
        await #expect(throws: MemoryFailure.exchangeUnknown) { try await reopened.query(operationID: original.operation_id, binding: f.binding) }
        await #expect(throws: MemoryFailure.pendingRequiresQuery) { try await reopened.save(command(), binding: f.binding) }
        #expect(await transport.posts.count == 1)
    }
    @Test func tamperedFailureCannotAuthorizeNewAction() async throws {
        let f = try Fixture(); defer { f.cleanup() }
        let transport = RejectionTransport(); let first = try client(f, transport)
        let original = command()
        await #expect(throws: MemoryFailure.rejected(403, "MEMORY_SOURCE_DENIED")) { try await first.save(original, binding: f.binding) }
        let path = f.root.appendingPathExtension("CJMemoryRejections").appendingPathComponent(digest(Data(original.operation_id.utf8)) + ".memory")
        var bytes = try Data(contentsOf: path); bytes[0] ^= 1; try bytes.write(to: path)
        let reopened = try client(f, transport)
        await #expect(throws: (any Error).self) { try await reopened.save(command(), binding: f.binding) }
        #expect(await transport.posts.count == 1)
    }
}
