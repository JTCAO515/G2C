import Foundation
import Testing
import CryptoKit
import CJAPI
import CJMessageKeys
import CJSession
@testable import CJTripClient

@Suite @MainActor struct LifetimeTests {
    @Test func originalCJSessionOperationInvalidationFencesAwaitEvenIfBindingUnchanged() async throws {
        let h = try Harness(); defer { h.clean() }
        let session = SessionLifecycle(persistence: SyntheticSessionPersistence(), restorePolicy: .userInitiatedOnly)
        let original = try session.beginTrustedSDKSave()
        let transport = Interceptor { _, _, _ in try response("proposal", fixture().proposal) }
        let client = TripClient(endpoint: h.endpoint, credentials: { _ in
            _ = try session.beginTrustedSDKSave()
            return "synthetic"
        }, currentBinding: { h.current }, session: session, sessionOperation: original, interceptedTransport: transport)
        await #expect(throws: TripFailure.staleBinding) { try await client.proposal(id: "proposal1", binding: h.binding) }
        #expect(await transport.calls.isEmpty)
        #expect(!session.isCurrent(original))
    }
    @Test func credentialsSwitchNeverDispatchesAndKeepsOriginalPending() async throws {
        let h = try Harness(); defer { h.clean() }
        let transport = Interceptor { _, _, _ in "{}" }
        let client = try h.client(transport, credentials: { _ in h.current = nil; return "synthetic" })
        await #expect(throws: TripFailure.staleBinding) { try await client.submitFixture(pending(), binding: h.binding, now: 1) }
        #expect(await transport.calls.isEmpty)
        #expect(try h.store().pending().count == 1)
    }
    @Test func sameAccountSelectionLateAResponseCannotReplaceB() async throws {
        let h = try Harness(); defer { h.clean() }
        let gate = Gate()
        let transport = Interceptor { request, _, _ in
            var p = try fixture().proposal
            if request.path?.contains("proposal_id=proposal1") == true { await gate.park() }
            else { p.proposal_id = "proposal2" }
            return try response("proposal", p)
        }
        let state = TripPresentation(client: try h.client(transport)); state.replace(binding: h.binding)
        let workA = try #require(state.prepareProposal(id: "proposal1"))
        let a = Task { await state.perform(workA) }
        await gate.waitForEntry()
        await state.perform(try #require(state.prepareProposal(id: "proposal2")))
        #expect(state.proposal?.proposal_id == "proposal2")
        await gate.release(); await a.value
        #expect(state.proposal?.proposal_id == "proposal2" && state.proposalState == .loaded)
    }
    @Test func oldQuerySuccessCannotOverwriteNewIdentityUIOrClearPending() async throws {
        let a = try Harness(); let b = try Harness(); defer { a.clean(); b.clean() }
        let original = try pending(); try a.store().append(original)
        let gate = Gate()
        let transport = Interceptor { _, _, op in
            if op == "queryTripAction" { await gate.park(); return try response("receipt", actionReceipt(original)) }
            var p = try fixture().proposal; p.proposal_id = "proposalB"; return try response("proposal", p)
        }
        let client = try a.client(transport)
        let state = TripPresentation(client: client); state.replace(binding: a.binding); state.selectPending(actionID: original.actionID)
        let queryWork = try #require(state.prepareReconciliation())
        let query = Task { await state.perform(queryWork) }; await gate.waitForEntry()
        a.current = b.binding; state.replace(binding: b.binding)
        await state.perform(try #require(state.prepareProposal(id: "proposalB")))
        await gate.release(); await query.value
        #expect(state.proposal?.proposal_id == "proposalB" && state.proposalState == .loaded)
        guard case .unavailable = state.decision else { Issue.record("old receipt affected B"); return }
        #expect(try a.store().pending().count == 1)
        #expect(try b.store().pending().isEmpty)
    }
    @Test func lateReadFailureCannotMarkBFailed() async throws {
        let h = try Harness(); defer { h.clean() }
        let gate = Gate()
        let transport = Interceptor { request, _, _ in
            if request.path?.contains("trip_id=A") == true { await gate.park(); throw TripFailure.exchangeUnknown }
            return try response("trip", record("B"))
        }
        let state = TripPresentation(client: try h.client(transport)); state.replace(binding: h.binding)
        let workA = try #require(state.prepareTrip(id: "A"))
        let old = Task { await state.perform(workA) }; await gate.waitForEntry()
        await state.perform(try #require(state.prepareTrip(id: "B"))); await gate.release(); await old.value
        #expect(state.trip?.trip_id == "B" && state.detailState == .loaded)
    }
    @Test func storageKeyCallbackSwitchCannotAppendDispatchOrBlockB() async throws {
        let h = try Harness(); defer { h.clean() }
        let transport = Interceptor { _, _, _ in "{}" }
        let other = TripBinding(environment: h.binding.environment, account: UUID(), generation: UUID(), selection: UUID())
        let store = try h.store(key: { h.current = other; return h.key })
        let client = try h.client(transport, store: store)
        await #expect(throws: TripFailure.staleBinding) { try await client.submitFixture(pending(), binding: h.binding, now: 1) }
        #expect(try FileManager.default.contentsOfDirectory(atPath: h.root.path).isEmpty)
        #expect(await transport.calls.isEmpty)
        #expect(h.current == other)
    }
    @Test func selectPendingCallbackCannotSelectNewBUsingOldClick() throws {
        let h = try Harness(); defer { h.clean() }
        try h.store().append(pending())
        let transport = Interceptor { _, _, _ in "{}" }
        var state: TripPresentation?
        var fired = false
        let store = try h.store(key: {
            if !fired { fired = true; h.current = nil; state?.replace(binding: nil) }
            return h.key
        })
        let presentation = TripPresentation(client: try h.client(transport, store: store)); state = presentation
        presentation.replace(binding: h.binding); presentation.selectPending(actionID: "accept1")
        #expect(presentation.binding == nil && presentation.proposal == nil && presentation.selectedActionID == nil)
    }
    @Test func canceledOriginalRemainsPendingAndCannotBeResent() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); let gate = Gate()
        let transport = Interceptor { _, _, _ in await gate.park(); return try response("receipt", actionReceipt(original)) }
        let client = try h.client(transport)
        let task = Task { try await client.submitFixture(original, binding: h.binding, now: 1) }
        await gate.waitForEntry(); task.cancel(); await gate.release()
        do { _ = try await task.value; Issue.record("canceled delivery settled") } catch { }
        #expect(try h.store().pending().count == 1)
        await #expect(throws: TripFailure.pendingRequiresQuery) { try await client.submitFixture(original, binding: h.binding, now: 1) }
        #expect(await transport.calls.count == 1)
    }
    @Test func canceledReconciliationReturnsToUnknownAndCanQueryAgain() async throws {
        let h = try Harness(); defer { h.clean() }
        try h.store().append(pending())
        let gate = Gate()
        let transport = Interceptor { _, _, _ in
            await gate.park()
            return "{\"request_id\":\"\(trace)\",\"receipt\":null}"
        }
        let state = TripPresentation(client: try h.client(transport)); state.replace(binding: h.binding)
        state.selectPending(actionID: "accept1")
        let queryWork = try #require(state.prepareReconciliation())
        let query = Task { await state.perform(queryWork) }; await gate.waitForEntry()
        query.cancel(); await gate.release(); await query.value
        guard case .unknown = state.decision else { Issue.record("canceled reconcile remained busy"); return }
        let againWork = try #require(state.prepareReconciliation())
        let again = Task { await state.perform(againWork) }; await gate.waitForEntry()
        #expect(state.prepareReconciliation() == nil) // Duplicate click is rejected synchronously.
        await gate.release(); await again.value
        guard case .unknown = state.decision else { Issue.record("null query lost unknown"); return }
        #expect(await transport.calls.map(\.operation) == ["queryTripAction", "queryTripAction"])
        #expect(try h.store().pending().count == 1)
    }
    @Test func directoryReplacementWhileAwaitingCredentialPreventsDispatch() async throws {
        let h = try Harness(); defer { h.clean() }
        let old = h.root.appendingPathExtension("old"); defer { try? FileManager.default.removeItem(at: old) }
        let transport = Interceptor { _, _, _ in "{}" }
        let client = try h.client(transport, credentials: { _ in
            try FileManager.default.moveItem(at: h.root, to: old)
            try FileManager.default.createDirectory(at: h.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            return "synthetic"
        })
        await #expect(throws: TripFailure.exchangeUnknown) { try await client.submitFixture(pending(), binding: h.binding, now: 1) }
        #expect(await transport.calls.isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: old.path).count == 1)
        #expect(try FileManager.default.contentsOfDirectory(atPath: h.root.path).isEmpty)
    }
    @Test func keyLossWrongKeyAndWrongNamespaceNeverRecoverPlaintext() throws {
        let h = try Harness(); defer { h.clean() }
        try h.store().append(pending())
        let missing = try h.store(key: { throw TripFailure.keyUnavailable })
        #expect(throws: TripFailure.keyUnavailable) { try missing.pending() }
        let wrong = try h.store(key: { SymmetricKey(size: .bits256) })
        #expect(throws: (any Error).self) { try wrong.pending() }
        let foreign = try TripPendingStore(directory: h.root, maximumBytes: 100_000, maximumRecords: 20,
            namespace: .init(environment: h.binding.environment, account: UUID(), purpose: .localTripPendingV1), keyID: h.keyID) { h.key }
        #expect(throws: (any Error).self) { try foreign.pending() }
        #expect(try h.store().pending().count == 1)
    }
    @Test func symlinkHardlinkAndTruncatedCiphertextFailClosed() throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); try h.store().append(original)
        let file = h.root.appendingPathComponent(digest(Data(original.actionID.utf8)) + ".trip")
        let bytes = try Data(contentsOf: file)
        try Data(bytes.prefix(20)).write(to: file)
        #expect(throws: TripFailure.storageUnavailable) { try h.store().pending() }
        try bytes.write(to: file)
        let link = h.root.appendingPathExtension("symlink"); defer { try? FileManager.default.removeItem(at: link) }
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: h.root)
        #expect(throws: TripFailure.storageUnavailable) {
            try TripPendingStore(directory: link, maximumBytes: 100_000, maximumRecords: 20, namespace: h.namespace, keyID: h.keyID) { h.key }
        }
        let hard = h.root.appendingPathExtension("hard"); defer { try? FileManager.default.removeItem(at: hard) }
        try FileManager.default.linkItem(at: file, to: hard)
        #expect(throws: TripFailure.storageUnavailable) { try h.store().pending() }
    }
}
