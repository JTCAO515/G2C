import Foundation
import CryptoKit
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJTripClient
@testable import CJShell

private let tripTrace = "00000000-0000-4000-8000-000000000001"
private actor TripHostTransport: ClientTransport {
    var replies: [Data]
    var calls: [(String, HTTPRequest.Method, String)] = []
    let holdFirst: Bool
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    init(_ replies: [Data], holdFirst: Bool = false) { self.replies = replies; self.holdFirst = holdFirst }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls.append((operationID, request.method, request.path ?? ""))
        guard !replies.isEmpty else { throw TripFailure.exchangeUnknown }
        let bytes = replies.removeFirst()
        if holdFirst && calls.count == 1 { held = true; await withCheckedContinuation { continuation = $0 } }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = tripTrace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
    func release() { continuation?.resume(); continuation = nil }
}
@MainActor private struct TripHostSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ value: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class TripHostFixture {
    let binding = TripBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    let session = SessionLifecycle(persistence: TripHostSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    var current: TripBinding?
    var callback: (() -> Void)?
    var credentials = 0
    init() throws { operation = try session.beginTrustedSDKSave(); current = binding }
    func observed() -> TripBinding? { let old = current; let call = callback; callback = nil; call?(); return old }
    func client(_ transport: TripHostTransport, store: TripPendingStore? = nil) throws -> TripClient {
        TripClient(endpoint: try TripEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 100_000, maximumResponseBytes: 100_000),
            credentials: { [self] _ in credentials += 1; return "SYNTHETIC" }, currentBinding: { [self] in observed() },
            pendingStore: store, session: session, sessionOperation: operation, interceptedTransport: transport)
    }
    func bind(_ host: TripContainerHost, shell: ShellState, transport: TripHostTransport, store: TripPendingStore? = nil,
              tripID: String? = nil, proposalID: String? = nil) throws {
        let value = TripContainerBinding(client: try client(transport, store: store), trip: binding, shellGeneration: shell.generation,
            session: session, sessionOperation: operation, pageSize: 2, currentTripID: tripID, proposalID: proposalID,
            synthetic: true, currentBinding: { [self] in observed() })
        #expect(host.bind(value))
    }
}
@Suite @MainActor struct TripContainerHostTests {
    private struct ProducerFixture: Decodable { let proposal: Components.Schemas.TripProposalSnapshot }
    private func proposal() throws -> Components.Schemas.TripProposalSnapshot {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<4 { root.deleteLastPathComponent() }
        let url = root.appendingPathComponent("CJTripClient/Tests/CJTripClientTests/Fixtures/action.json")
        return try JSONDecoder().decode(ProducerFixture.self, from: Data(contentsOf: url)).proposal
    }
    private func record(_ id: String = "trip1", version: Int = 7) throws -> Components.Schemas.TripRecord {
        let p = try proposal()
        return .init(trip_id: id, version: version, content_utf8_base64: p.content_utf8_base64, document: p.document)
    }
    private func json(_ fields: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: fields.merging(["request_id": tripTrace]) { a, _ in a })
    }
    private func object<T: Encodable>(_ value: T) throws -> Any { try JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) }
    private func response<T: Encodable>(_ key: String, _ value: T) throws -> Data { try json([key: object(value)]) }
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func wait(_ t: TripHostTransport) async {
        for _ in 0..<10000 { if await t.held { return }; await Task.yield() }; Issue.record("Request did not reach hold")
    }
    private func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]); return url
    }
    private func store(_ f: TripHostFixture, directory: URL, key: @escaping () throws -> SymmetricKey) throws -> TripPendingStore {
        try TripPendingStore(directory: directory, maximumBytes: 100_000, maximumRecords: 10,
            namespace: .init(environment: f.binding.environment, account: f.binding.account, purpose: .localTripPendingV1), keyID: UUID(), key: key)
    }
    private func original(_ id: String = "accept1", kind: TripActionKind = .accept) throws -> TripPending {
        try TripPending(actionID: id, kind: kind, proposal: proposal(), confirmationReference: "server-held-synthetic-proof")
    }
    private func receipt(_ original: TripPending) -> Components.Schemas.TripActionReceipt {
        .init(action_id: original.actionID, kind: original.kind, proposal_id: original.proposal.proposal_id,
              candidate_hash: original.proposal.candidate_hash, trip_id: original.proposal.trip_id,
              committed_version: original.kind == .accept ? .case1(original.proposal.expected_version + 1) : .case2(nil))
    }
    @Test func defaultUnavailableAndNoInventedContext() async throws {
        let s = try shell(), h = TripContainerHost(shell: s)
        await h.perform(h.prepareTrips(context: h.captureAction())); await h.perform(h.prepareProposal(context: h.captureAction()))
        #expect(h.presentation == nil && !h.canSubmitDecision && h.contextTripID == nil && h.contextProposalID == nil)
        let f = try TripHostFixture(), t = TripHostTransport([])
        try f.bind(h, shell: s, transport: t)
        await h.perform(h.prepareProposal(context: h.captureAction())); await h.perform(h.prepareTrip(context: h.captureAction()))
        #expect(!h.selectTrip("invented", context: h.captureAction()))
        #expect(await t.calls.isEmpty); #expect(f.credentials == 0)
    }
    @Test func anotherContextProposalRequiresOriginalSettlementThenBecomesReadable() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture()
        let dir = try directory(); defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256)
        let storage = try store(f, directory: dir, key: { key })
        let old = try original(); try storage.append(old)
        var next = try proposal(); next.proposal_id = "p-next"; next.trip_id = "t-next"
        let transport = TripHostTransport([try json(["receipt": NSNull()]),
            try response("receipt", receipt(old)), try response("proposal", next)])
        try f.bind(h, shell: s, transport: transport, store: storage, proposalID: next.proposal_id)
        h.loadPending(context: h.captureAction())
        #expect(h.selectPending(old.actionID, context: h.captureAction()))
        #expect(!h.canReadContextProposal && h.prepareProposal(context: h.captureAction()) == nil)
        await h.perform(h.prepareReconciliation(context: h.captureAction()))
        #expect(!h.canReadContextProposal) // null remains unknown, not permission to replace it
        await h.perform(h.prepareReconciliation(context: h.captureAction()))
        #expect(h.canReadContextProposal)
        await h.perform(h.prepareProposal(context: h.captureAction()))
        #expect(h.presentation?.selectedProposalID == next.proposal_id)
        #expect(h.presentation?.selectedActionID == nil)
        #expect(try storage.pending().map(\.actionID) == [old.actionID])
        #expect(await transport.calls.allSatisfy { $0.1 == .get })
    }
    @Test func canonicalListPagesDetailAndProposalStayReadOnly() async throws {
        let p = try proposal()
        let t = TripHostTransport([try json(["trips": [object(record())], "next_after": "trip1"]),
            try json(["trips": [], "next_after": NSNull()]), try response("trip", record()), try response("proposal", p)])
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture()
        try f.bind(h, shell: s, transport: t, proposalID: p.proposal_id)
        await h.perform(h.prepareTrips(context: h.captureAction()))
        let view = try #require(h.presentation)
        #expect(view.trips.count == 1 && view.next != nil)
        let generation = s.generation; s.selectLanguage(.chinese)
        #expect(h.presentation === view && s.generation == generation)
        await h.perform(h.prepareTrips(context: h.captureAction(), more: true))
        #expect(view.trips.count == 1 && view.next == nil)
        #expect(h.selectTrip("trip1", context: h.captureAction()))
        await h.perform(h.prepareTrip(context: h.captureAction()))
        #expect(h.showsSelectedDetail && view.trip?.version == 7)
        await h.perform(h.prepareProposal(context: h.captureAction()))
        #expect(view.proposal?.content_utf8_base64 == p.content_utf8_base64)
        #expect(view.proposal?.candidate_hash == p.candidate_hash && view.proposal?.document.items.first?.verification == .pending)
        view.choose(.accept); #expect(!h.canSubmitDecision)
        #expect(await t.calls.allSatisfy { $0.1 == .get })
    }
    @Test func emptyMissingAndMalformedReadsAreDistinct() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture()
        let t = TripHostTransport([try json(["trips": [], "next_after": NSNull()]), try json(["trip": NSNull()]), Data("{}".utf8)])
        try f.bind(h, shell: s, transport: t, tripID: "trip1")
        await h.perform(h.prepareTrips(context: h.captureAction())); #expect(h.presentation?.listState == .loaded && h.presentation?.trips.isEmpty == true)
        #expect(h.selectTrip("trip1", context: h.captureAction()))
        await h.perform(h.prepareTrip(context: h.captureAction())); #expect(h.presentation?.detailState == .missing)
        await h.perform(h.prepareTrips(context: h.captureAction())); #expect(h.presentation?.listState == .failed)
    }
    @Test func queuedOldActionCannotRetargetNewBindingOrSelection() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), a = try TripHostFixture(), b = try TripHostFixture()
        let ta = TripHostTransport([]), tb = TripHostTransport([try response("trip", record("tripB"))])
        try a.bind(h, shell: s, transport: ta, tripID: "tripA")
        let oldPresentation = h.presentation
        #expect(h.selectTrip("tripA", context: h.captureAction())); let old = h.prepareTrip(context: h.captureAction())
        h.invalidate(); try b.bind(h, shell: s, transport: tb, tripID: "tripB")
        #expect(h.selectTrip("tripB", context: h.captureAction()))
        await h.perform(old)
        #expect(await ta.calls.isEmpty); #expect(await tb.calls.isEmpty)
        #expect(oldPresentation?.binding == nil && oldPresentation?.trip == nil)
        await h.perform(h.prepareTrip(context: h.captureAction())); #expect(h.presentation?.trip?.trip_id == "tripB")
    }
    @Test(arguments: [false, true]) func oldReadCannotReviveAfterAccountOrBackground(background: Bool) async throws {
        let s = try shell(), h = TripContainerHost(shell: s), a = try TripHostFixture(), b = try TripHostFixture()
        let ta = TripHostTransport([try json(["trips": [object(record("old"))], "next_after": "old"])], holdFirst: true)
        try a.bind(h, shell: s, transport: ta)
        let previous = h.presentation, work = h.prepareTrips(context: h.captureAction())
        let task = Task { await h.perform(work) }; await wait(ta)
        if background { h.suspendForBackground() } else { s.invalidateIdentity() }
        #expect(h.presentation == nil && !h.busy && previous?.trips.isEmpty == true)
        s.messageBindingBlocked = false // explicit synthetic root re-verification, not product authorization
        let tb = TripHostTransport([try json(["trips": [object(record("new"))], "next_after": "new"])])
        try b.bind(h, shell: s, transport: tb); await h.perform(h.prepareTrips(context: h.captureAction()))
        await ta.release(); await task.value
        #expect(h.presentation?.trips.map(\.trip_id) == ["new"] && !h.busy)
    }
    @Test func currentCallbackReentryPreservesReplacementAndDoesNotDispatch() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), a = try TripHostFixture(), b = try TripHostFixture()
        let ta = TripHostTransport([]), tb = TripHostTransport([])
        try a.bind(h, shell: s, transport: ta)
        a.callback = { h.invalidate(); try! b.bind(h, shell: s, transport: tb) }
        let action = h.captureAction(); #expect(action == nil)
        await h.perform(h.prepareTrips(context: action))
        #expect(h.presentation?.binding == b.binding)
        #expect(await ta.calls.isEmpty); #expect(await tb.calls.isEmpty)
    }
    @Test func originalSessionRetirementHidesPrivatePresentation() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture()
        let t = TripHostTransport([try json(["trips": [object(record())], "next_after": "trip1"])])
        try f.bind(h, shell: s, transport: t); await h.perform(h.prepareTrips(context: h.captureAction()))
        let old = h.prepareTrips(context: h.captureAction()); try f.session.clear()
        #expect(!h.isConfigured && h.presentation == nil)
        await h.perform(old); #expect(await t.calls.count == 1)
    }
    @Test(arguments: [TripActionKind.accept, .reject]) func originalReceiptNeverBecomesLatestVersion(kind: TripActionKind) async throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture(), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), original = try original(kind: kind)
        let store = try store(f, directory: dir) { key }; try store.append(original)
        let t = TripHostTransport([try response("receipt", receipt(original)), try response("trip", record(version: 7))])
        try f.bind(h, shell: s, transport: t, store: store, tripID: "trip1")
        h.loadPending(context: h.captureAction()); #expect(h.selectPending(original.actionID, context: h.captureAction()))
        await h.perform(h.prepareReconciliation(context: h.captureAction()))
        #expect(h.selectTrip("trip1", context: h.captureAction())); await h.perform(h.prepareTrip(context: h.captureAction()))
        let view = try #require(h.presentation)
        guard case .confirmed(let receipt) = view.decision else { Issue.record("Missing original receipt"); return }
        if kind == .accept { guard case .case1(1) = receipt.committed_version else { Issue.record("Receipt replaced with latest"); return } }
        else { guard case .case2 = receipt.committed_version else { Issue.record("Reject acquired version"); return } }
        #expect(view.trip?.version == 7 && view.proposal?.expected_version == 0)
        #expect(try store.pending().first?.originalUTF8 == original.originalUTF8)
        #expect(await t.calls.map(\.0) == ["queryTripAction", "getTrip"])
        #expect(await t.calls.allSatisfy { $0.1 == .get })
    }
    @Test(arguments: ["null", "malformed", "cancel"])
    func uncertainOriginalQueryStaysUnknownWithoutResend(outcome: String) async throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture(), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), original = try original()
        let store = try store(f, directory: dir) { key }; try store.append(original)
        let t = TripHostTransport([try json(["receipt": outcome == "malformed" ? [:] : NSNull()])], holdFirst: outcome == "cancel")
        try f.bind(h, shell: s, transport: t, store: store)
        h.loadPending(context: h.captureAction()); #expect(h.selectPending(original.actionID, context: h.captureAction()))
        let work = h.prepareReconciliation(context: h.captureAction()); let task = Task { await h.perform(work) }
        if outcome == "cancel" { await wait(t); task.cancel(); await t.release() }
        await task.value
        guard case .unknown = h.presentation?.decision else { Issue.record("Unknown query failed to settle"); return }
        #expect(!h.busy && !h.canSubmitDecision)
        #expect(try store.pending().first?.originalUTF8 == original.originalUTF8)
        #expect(await t.calls.map(\.0) == ["queryTripAction"])
    }
    @Test func queuedQueryCannotSwitchToAnotherOriginal() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture(), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), first = try original("actionA"), second = try original("actionB")
        let store = try store(f, directory: dir) { key }; try store.append(first); try store.append(second)
        let t = TripHostTransport([try response("receipt", receipt(second))])
        try f.bind(h, shell: s, transport: t, store: store)
        h.loadPending(context: h.captureAction()); #expect(h.selectPending(first.actionID, context: h.captureAction()))
        let view = try #require(h.presentation)
        let old = h.prepareReconciliation(context: h.captureAction())
        view.selectPending(actionID: second.actionID) // same-binding canonical selection changes before queued perform
        await h.perform(old); #expect(await t.calls.isEmpty)
        await h.perform(h.prepareReconciliation(context: h.captureAction()))
        #expect(await t.calls.first?.2.contains("action_id=actionB") == true)
    }
    @Test func pendingKeyCallbackReplacementCannotNavigateOrOverwriteB() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), a = try TripHostFixture(), b = try TripHostFixture()
        let dir = try directory(); defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), original = try original()
        var callback: (() -> Void)?
        let store = try store(a, directory: dir) {
            let run = callback; callback = nil; run?(); return key
        }
        try store.append(original)
        let ta = TripHostTransport([]), tb = TripHostTransport([try json(["trips": [], "next_after": NSNull()])])
        try a.bind(h, shell: s, transport: ta, store: store)
        h.loadPending(context: h.captureAction())
        let oldPresentation = h.presentation
        callback = { h.invalidate(); try! b.bind(h, shell: s, transport: tb) }
        #expect(!h.selectPending(original.actionID, context: h.captureAction()))
        #expect(h.presentation?.binding == b.binding && h.presentation?.selectedActionID == nil)
        #expect(oldPresentation?.binding == nil && !h.busy)
        await h.perform(h.prepareTrips(context: h.captureAction()))
        #expect(h.presentation?.listState == .loaded)
        #expect(await ta.calls.isEmpty); #expect(await tb.calls.map(\.0) == ["listTrips"])
    }
    @Test func sameBindingKeyCallbackSelectionWinsOverOldHostSelection() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture(), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), a = try original("actionA"), b = try original("actionB", kind: .reject)
        var callback: (() -> Void)?
        let store = try store(f, directory: dir) { let run = callback; callback = nil; run?(); return key }
        try store.append(a); try store.append(b)
        let t = TripHostTransport([try response("receipt", receipt(b))])
        try f.bind(h, shell: s, transport: t, store: store)
        h.loadPending(context: h.captureAction())
        let view = try #require(h.presentation)
        callback = { view.selectPending(actionID: b.actionID) }
        #expect(!h.selectPending(a.actionID, context: h.captureAction()))
        #expect(view.selectedActionID == b.actionID && !h.busy)
        let work = h.prepareReconciliation(context: h.captureAction())
        await h.perform(work)
        #expect(await t.calls.first?.2.contains("action_id=actionB") == true)
        #expect(await t.calls.count == 1)
        #expect(try store.pending().map(\.originalUTF8).contains(a.originalUTF8))
    }
    @Test func duplicatePreparedWorkCannotReleaseBusyOrDispatchTwice() async throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture()
        let t = TripHostTransport([try json(["trips": [], "next_after": NSNull()])], holdFirst: true)
        try f.bind(h, shell: s, transport: t)
        let work = h.prepareTrips(context: h.captureAction())
        #expect(h.busy && h.presentation?.listState == .loading)
        let first = Task { await h.perform(work) }; await wait(t)
        await h.perform(work)
        #expect(h.busy && h.captureAction() == nil)
        #expect(await t.calls.count == 1)
        await t.release(); await first.value
        await h.perform(work)
        #expect(!h.busy && h.presentation?.listState == .loaded)
        #expect(await t.calls.count == 1)
    }
    @Test func missingStoreAndExistingKeyFailClosed() throws {
        let s = try shell(), h = TripContainerHost(shell: s), f = try TripHostFixture(), t = TripHostTransport([])
        try f.bind(h, shell: s, transport: t); h.loadPending(context: h.captureAction())
        #expect(h.presentation?.pendingState == .failed)
        h.invalidate()
        let dir = try directory(); defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256); var available = true
        let store = try store(f, directory: dir) { guard available else { throw TripFailure.keyUnavailable }; return key }
        let pending = try original(); try store.append(pending)
        try f.bind(h, shell: s, transport: t, store: store); h.loadPending(context: h.captureAction())
        #expect(h.selectPending(pending.actionID, context: h.captureAction()))
        available = false
        // The canonical selection rereads storage. Its failure must not reuse the prior selected ID as success.
        #expect(!h.selectPending(pending.actionID, context: h.captureAction()))
        #expect(h.presentation?.pendingState == .failed && f.credentials == 0)
    }
}
