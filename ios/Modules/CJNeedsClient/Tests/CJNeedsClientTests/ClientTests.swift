import Testing
import Foundation
import CJAPI
import CryptoKit
import CJMessageKeys
import CJMessageHTTP
import CJSession
@testable import CJNeedsClient

@MainActor @Suite struct ClientTests {
    @Test func actualOfficialClientUsesFourOperationsAndExactBytes() async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); let t = successfulTransport(a); let client = try h.client(t)
        let submitted = try await client.perform(client.prepareManualAction(a, binding: h.binding))
        guard case .confirmed(let r, let v) = submitted else { Issue.record("unconfirmed"); return }
        #expect(r.version == 1 && v.action_id == a.actionID)
        _ = try await client.perform(client.prepareDetail(id: a.needsID, binding: h.binding))
        _ = try await client.perform(client.prepareRevision(id: a.needsID, version: 1, binding: h.binding))
        _ = try await client.perform(client.prepareQuery(actionID: a.actionID, binding: h.binding))
        let calls = await t.calls
        #expect(calls.map(\.operation) == ["actOnNeeds", "getNeedsRevision", "getNeeds", "getNeedsRevision", "queryNeedsAction", "getNeedsRevision"])
        #expect(calls.first?.bytes == a.originalUTF8)
        #expect(calls[1].path?.contains("version=1") == true)
        #expect(calls[1].path?.contains("needs_id=visit") == true)
        #expect(try client.pending(binding: h.binding).first?.originalUTF8 == a.originalUTF8)
    }
    @Test func lostACKReopenQueriesOriginalThenHistoricalRevision() async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original()
        let lost = Interceptor { _, _, _ in throw NeedsFailure.exchangeUnknown }
        let first = try h.client(lost)
        await #expect(throws: NeedsFailure.exchangeUnknown) { try await first.perform(first.prepareManualAction(a, binding: h.binding)) }
        let t = successfulTransport(a); let reopened = try h.client(t, store: h.store())
        let records = try reopened.pending(binding: h.binding); #expect(records.count == 1 && records[0].originalUTF8 == a.originalUTF8)
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await reopened.perform(reopened.prepareManualAction(try original("different"), binding: h.binding)) }
        let result = try await reopened.perform(reopened.prepareQuery(actionID: a.actionID, binding: h.binding))
        guard case .confirmed = result else { Issue.record("not reconciled"); return }
        #expect(await t.calls.map(\.operation) == ["queryNeedsAction", "getNeedsRevision"])
        #expect(try reopened.pending(binding: h.binding).count == 1) // Append-only; no cleanup on success.
    }
    @Test(arguments: ["query-null", "revision-null", "invalid-oneOf", "error", "revision-error", "revision-invalid"])
    func unknownNeverAllowsNewAction(mode: String) async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); let store = try h.store(); try store.append(a)
        let t = Interceptor { _, _, operation in
            if mode == "error" || (mode == "revision-error" && operation == "getNeedsRevision") { throw NeedsFailure.exchangeUnknown }
            if operation == "queryNeedsAction" {
                if mode == "query-null" { return Reply(nullResponse("receipt")) }
                if mode == "invalid-oneOf" { return Reply("{\"request_id\":\"\(trace)\",\"receipt\":{\"not_receipt\":true}}") }
                return Reply(try response("receipt", receipt(a)))
            }
            if mode == "revision-invalid" { return Reply("{\"request_id\":\"\(trace)\",\"revision\":123}") }
            return Reply(nullResponse("revision"))
        }
        let client = try h.client(t, store: store)
        do {
            let result = try await client.perform(client.prepareQuery(actionID: a.actionID, binding: h.binding))
            guard case .notObserved = result else { Issue.record("unknown became success"); return }
        } catch { #expect(["invalid-oneOf", "error", "revision-error", "revision-invalid"].contains(mode)) }
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await client.perform(client.prepareManualAction(try original("next"), binding: h.binding)) }
        #expect(await t.calls.allSatisfy { $0.operation != "actOnNeeds" })
    }
    @Test(arguments: ["action", "needs", "version", "whitespace", "unicode", "revisionID", "revisionBody"])
    func receiptRevisionMismatchCannotSettle(mode: String) async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); let store = try h.store(); try store.append(a)
        let t = Interceptor { _, _, operation in
            if operation == "queryNeedsAction" {
                var r = receipt(a)
                if mode == "action" { r.action_id = "different" }
                if mode == "needs" { r.needs_id = "different" }
                if mode == "version" { r.version = 2 }
                return Reply(try response("receipt", r))
            }
            var r = try revision(a)
            if mode == "whitespace" { r.original_input_utf8_base64 = (Data(" ".utf8) + a.originalUTF8).base64EncodedString() }
            if mode == "unicode" { r.original_input_utf8_base64 = try original(text: "日期未定。 Dates undecided. é").originalUTF8.base64EncodedString() }
            if mode == "revisionID" { r.action_id = "wrong" }
            if mode == "revisionBody" { r.fields.party_size = .NeedsPartySizeObservationKnown(.init(state: .known, value: 9)) }
            return Reply(try response("revision", r))
        }
        let client = try h.client(t, store: store)
        await #expect(throws: (any Error).self) { try await client.perform(client.prepareQuery(actionID: a.actionID, binding: h.binding)) }
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await client.perform(client.prepareManualAction(try original("next"), binding: h.binding)) }
    }
    @Test func latestDetailNeverReconcilesOriginal() async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); let store = try h.store(); try store.append(a)
        let t = successfulTransport(a); let client = try h.client(t, store: store)
        _ = try await client.perform(client.prepareDetail(id: a.needsID, binding: h.binding))
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await client.perform(client.prepareManualAction(try original("new"), binding: h.binding)) }
        #expect(await t.calls.map(\.operation) == ["getNeeds"])
    }
    @Test func publicConstructionCannotWrite() async throws {
        let h = try Harness(); defer { h.clean() }
        let session = SessionLifecycle(persistence: SyntheticPersistence(), restorePolicy: .userInitiatedOnly)
        let operation = try session.beginTrustedSDKSave()
        try session.save(SessionMaterial(trustedSDKBytes: Data("synthetic-session".utf8)), for: operation)
        var credentialsCalled = false
        let store = try h.store()
        let client = NeedsClient(endpoint: h.endpoint, credentials: { _ in credentialsCalled = true; return "synthetic" },
                                 currentBinding: { h.current }, session: session, sessionOperation: operation,
                                 pendingStore: store, liveReadTransport: try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1))
        #expect(!client.acceptsUserActions)
        await #expect(throws: NeedsFailure.liveWriteUnavailable) {
            try await client.perform(client.prepareManualAction(try original(), binding: h.binding))
        }
        #expect(!credentialsCalled)
        #expect(try store.pending().isEmpty)
    }
    @Test func encryptedRecordsRejectWrongKeyPurposeAccountAndCorruption() throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); let store = try h.store(); try store.append(a)
        let paths = try FileManager.default.contentsOfDirectory(at: h.root, includingPropertiesForKeys: nil)
        let file = try #require(paths.first); let ciphertext = try Data(contentsOf: file)
        #expect(ciphertext.range(of: Data("日期".utf8)) == nil)
        #expect(throws: (any Error).self) { try h.store(key: { SymmetricKey(size: .bits256) }).pending() }
        #expect(throws: (any Error).self) { try h.store(keyID: UUID()).pending() }
        #expect(throws: (any Error).self) { try h.store(namespace: .init(environment: h.binding.environment, account: UUID(), purpose: .localNeedsPendingV1)).pending() }
        #expect(throws: (any Error).self) { try h.store(namespace: .init(environment: h.binding.environment, account: h.binding.account, purpose: .localTripPendingV1)).pending() }
        #expect(try Data(contentsOf: file) == ciphertext)
        var corrupt = ciphertext; corrupt[0] ^= 1; try corrupt.write(to: file)
        #expect(throws: (any Error).self) { try store.pending() }
        #expect(try Data(contentsOf: file) == corrupt)
    }
    @Test func actionIDsHaveOneDispatchEvenAfterConfirmed() async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); let t = successfulTransport(a); let client = try h.client(t)
        _ = try await client.perform(client.prepareManualAction(a, binding: h.binding))
        await #expect(throws: NeedsFailure.pendingRequiresQuery) { try await client.perform(client.prepareManualAction(a, binding: h.binding)) }
        #expect(await t.calls.filter { $0.operation == "actOnNeeds" }.count == 1)
    }
}
@MainActor struct SyntheticPersistence: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
