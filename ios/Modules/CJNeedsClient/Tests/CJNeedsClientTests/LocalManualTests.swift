import Foundation
import Testing
import CJAPI
import CJMessageHTTP
@testable import CJNeedsClient

@MainActor @Suite struct LocalManualTests {
    func client(_ h: Harness, _ transport: Interceptor, store: NeedsPendingStore? = nil,
                credentials: NeedsCredentialCallback? = nil) throws -> NeedsClient {
        try NeedsClient(endpoint: h.endpoint, credentials: credentials ?? { _ in "synthetic-local-token" },
            currentBinding: { h.current }, pendingStore: store ?? h.store(), interceptedTransport: transport,
            manualWritesAvailable: true)
    }
    func failed(_ status: Int = 409) throws -> String {
        let code = status == 409 ? "NEEDS_CONFLICT" : "INVALID_INPUT"
        return String(decoding: try encoded(NeedsSchema.ErrorResponse(request_id: trace, error: .init(
            code: code, category: "input", message_en: "Request unavailable", message_zh: "请求不可用",
            outcome: .failed, recovery: .do_not_retry))), as: UTF8.self)
    }
    func rejectionFile(_ h: Harness) throws -> URL {
        let path = h.root.appendingPathExtension("CJNeedsRejections")
        return try #require(FileManager.default.contentsOfDirectory(at: path, includingPropertiesForKeys: nil).first)
    }
    func corrupt(_ path: URL) throws {
        var bytes = try Data(contentsOf: path); bytes[0] ^= 1; try bytes.write(to: path)
    }
    func clean(_ h: Harness) {
        h.clean()
        try? FileManager.default.removeItem(at: h.root.appendingPathExtension("CJNeedsRejections"))
    }
    @Test(arguments: [400, 409]) func canonicalFailedPostIsDurableAcrossReopen(status: Int) async throws {
        let h = try Harness(); defer { clean(h) }
        let a = try original(), body = try failed(status)
        let t = Interceptor { _, _, _ in Reply(body, status: status) }
        let first = try client(h, t)
        guard case .rejectedOriginal(let observed, let code, _) = try await first.perform(first.prepareManualAction(a, binding: h.binding)) else {
            Issue.record("Known failed POST lost its disposition"); return
        }
        #expect(observed.originalUTF8 == a.originalUTF8 && code == status)
        let originalCipher = try Data(contentsOf: h.root.appendingPathComponent(digest(Data(a.actionID.utf8)) + ".needs"))
        let b = try original("next", version: 1)
        let second = Interceptor { _, bytes, op in
            switch op {
            case "queryNeedsAction": return Reply(nullResponse("receipt"))
            case "actOnNeeds":
                #expect(bytes == b.originalUTF8)
                return Reply(try response("receipt", receipt(b)))
            default: return Reply(try response("revision", revision(b)))
            }
        }
        let reopened = try client(h, second)
        #expect(try !reopened.requiresOriginalReconciliation(binding: h.binding))
        guard case .rejectedOriginal = try await reopened.perform(reopened.prepareQuery(actionID: a.actionID, binding: h.binding)) else {
            Issue.record("Reopen turned known failure into unknown"); return
        }
        guard case .confirmed = try await reopened.perform(reopened.prepareManualAction(b, binding: h.binding)) else {
            Issue.record("Explicit next action was permanently blocked"); return
        }
        #expect(try Data(contentsOf: h.root.appendingPathComponent(digest(Data(a.actionID.utf8)) + ".needs")) == originalCipher)
        #expect(try reopened.pending(binding: h.binding).map(\.originalUTF8).contains(a.originalUTF8))
        #expect(await second.calls.filter { $0.operation == "actOnNeeds" }.count == 1)
    }
    @Test func unknownNullAndFailedGetNeverAuthorizeNewActionOrReplay() async throws {
        let h = try Harness(); defer { clean(h) }; let a = try original()
        let first = try client(h, Interceptor { _, _, _ in throw NeedsFailure.exchangeUnknown })
        await #expect(throws: NeedsFailure.exchangeUnknown) { try await first.perform(first.prepareManualAction(a, binding: h.binding)) }
        let t = Interceptor { _, _, _ in Reply(nullResponse("receipt")) }
        let next = try client(h, t)
        guard case .notObserved = try await next.perform(next.prepareQuery(actionID: a.actionID, binding: h.binding)) else {
            Issue.record("Null became a failed POST proof"); return
        }
        #expect(try next.requiresOriginalReconciliation(binding: h.binding))
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await next.perform(next.prepareReplay(actionID: a.actionID, binding: h.binding)) }
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await next.perform(next.prepareManualAction(try original("new"), binding: h.binding)) }
        #expect(await t.calls.map(\.operation) == ["queryNeedsAction"])
        let body = try failed(400)
        let denied = try client(h, Interceptor { _, _, _ in Reply(body, status: 400) })
        await #expect(throws: NeedsFailure.rejected(400, "INVALID_INPUT")) { try await denied.perform(denied.prepareQuery(actionID: a.actionID, binding: h.binding)) }
        #expect(try denied.requiresOriginalReconciliation(binding: h.binding))
        #expect(!FileManager.default.fileExists(atPath: h.root.appendingPathExtension("CJNeedsRejections").path))
    }
    @Test func onlyVerifiedOriginalMayBeExplicitlyReplayedWithExactBytes() async throws {
        let h = try Harness(); defer { clean(h) }; let a = try original(); let t = successfulTransport(a)
        let value = try client(h, t)
        _ = try await value.perform(value.prepareManualAction(a, binding: h.binding))
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await value.perform(value.prepareManualAction(a, binding: h.binding)) }
        _ = try await value.perform(value.prepareReplay(actionID: a.actionID, binding: h.binding))
        #expect(await t.calls.filter { $0.operation == "actOnNeeds" }.map(\.bytes) == [a.originalUTF8, a.originalUTF8])
        value.invalidate()
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await value.perform(value.prepareReplay(actionID: a.actionID, binding: h.binding)) }
        _ = try await value.perform(value.prepareQuery(actionID: a.actionID, binding: h.binding))
        _ = try await value.perform(value.prepareReplay(actionID: a.actionID, binding: h.binding))
        #expect(try value.pending(binding: h.binding).map(\.originalUTF8) == [a.originalUTF8])
    }
    @Test(arguments: ["trace", "duplicate", "outcome"]) func invalidErrorEnvelopeRemainsUnknown(mode: String) async throws {
        let h = try Harness(); defer { clean(h) }; let a = try original()
        var body = try failed()
        if mode == "trace" { body = body.replacingOccurrences(of: trace, with: UUID().uuidString) }
        if mode == "duplicate" { body = "{\"request_id\":\"" + trace + "\"," + String(body.dropFirst()) }
        if mode == "outcome" { body = body.replacingOccurrences(of: "\"failed\"", with: "\"unknown\"") }
        let reply = body
        let value = try client(h, Interceptor { _, _, _ in Reply(reply, status: 409) })
        do { _ = try await value.perform(value.prepareManualAction(a, binding: h.binding)) }
        catch { /* Exact error category is secondary; it cannot authorize another write. */ }
        #expect(try value.requiresOriginalReconciliation(binding: h.binding))
        #expect(!FileManager.default.fileExists(atPath: h.root.appendingPathExtension("CJNeedsRejections").path))
    }
    @Test func rejectionCorruptionOrLateInventoryChangePreventsNewOutflow() async throws {
        let h = try Harness(); defer { clean(h) }; let a = try original(); let body = try failed()
        let failedClient = try client(h, Interceptor { _, _, _ in Reply(body, status: 409) })
        _ = try await failedClient.perform(failedClient.prepareManualAction(a, binding: h.binding))
        let path = try rejectionFile(h), frozen = try Data(contentsOf: path)
        let t = successfulTransport(try original("new"))
        let next = try client(h, t, credentials: { _ in
            try corrupt(path)
            return "synthetic-local-token"
        })
        await #expect(throws: (any Error).self) { try await next.perform(next.prepareManualAction(try original("new"), binding: h.binding)) }
        #expect(await t.calls.isEmpty)
        #expect(try Data(contentsOf: path) != frozen)
        #expect(throws: (any Error).self) { try next.requiresOriginalReconciliation(binding: h.binding) }
    }
    @Test func unknownOriginalAddedByFinalCredentialCallbackCannotBeSkipped() async throws {
        let h = try Harness(); defer { clean(h) }; let a = try original(); let body = try failed()
        let first = try client(h, Interceptor { _, _, _ in Reply(body, status: 409) })
        _ = try await first.perform(first.prepareManualAction(a, binding: h.binding))
        let store = try h.store(), unexpected = try original("late-unknown")
        let t = successfulTransport(try original("new"))
        let next = try client(h, t, store: store, credentials: { _ in
            try store.append(unexpected)
            return "synthetic-local-token"
        })
        await #expect(throws: (any Error).self) { try await next.perform(next.prepareManualAction(try original("new"), binding: h.binding)) }
        #expect(await t.calls.isEmpty)
        #expect(try store.pending().contains { $0.originalUTF8 == unexpected.originalUTF8 })
    }
    @Test func rejectionChangedAfterQueryCaptureCannotSettle() async throws {
        let h = try Harness(); defer { clean(h) }; let a = try original(); let body = try failed()
        let first = try client(h, Interceptor { _, _, _ in Reply(body, status: 409) })
        _ = try await first.perform(first.prepareManualAction(a, binding: h.binding))
        let path = try rejectionFile(h)
        let query = try client(h, Interceptor { _, _, _ in Reply(nullResponse("receipt")) }, credentials: { _ in
            try corrupt(path)
            return "synthetic-local-token"
        })
        await #expect(throws: (any Error).self) { try await query.perform(query.prepareQuery(actionID: a.actionID, binding: h.binding)) }
    }
}
