import Foundation
import CryptoKit
import Testing
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJNeedsClient
@testable import CJShell

private let needsTrace = "00000000-0000-4000-8000-000000000001"
private actor NeedsHostTransport: ClientTransport {
    var replies: [Data]
    var bodies: [Data] = []
    var calls: [(String, HTTPRequest.Method, String)] = []
    let holdFirst: Bool
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    init(_ replies: [Data], holdFirst: Bool = false) { self.replies = replies; self.holdFirst = holdFirst }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls.append((operationID, request.method, request.path ?? ""))
        if let body { bodies.append(try await Data(collecting: body, upTo: 131072)) }
        guard !replies.isEmpty else { throw NeedsFailure.exchangeUnknown }
        let bytes = replies.removeFirst()
        if holdFirst && calls.count == 1 { held = true; await withCheckedContinuation { continuation = $0 } }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = needsTrace
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
    func add(_ value: Data) { replies.append(value) }
    func release() { continuation?.resume(); continuation = nil }
}
@MainActor private struct NeedsHostSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ value: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class NeedsHostFixture {
    let binding = NeedsBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    let session = SessionLifecycle(persistence: NeedsHostSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    var current: NeedsBinding?
    var callback: (() -> Void)?
    var credentials = 0
    init() throws { operation = try session.beginTrustedSDKSave(); current = binding }
    func observed() -> NeedsBinding? { let old = current; let run = callback; callback = nil; run?(); return old }
    func bind(_ host: NeedsContainerHost, shell: ShellState, transport: NeedsHostTransport, id: String = "needs-A", store: NeedsPendingStore? = nil, manual: Bool = false) throws {
        let client = NeedsClient(endpoint: try NeedsEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 131_072, maximumResponseBytes: 1_048_576),
            credentials: { [self] _ in credentials += 1; return "SYNTHETIC" }, currentBinding: { [self] in observed() },
            pendingStore: store, interceptedTransport: transport, manualWritesAvailable: manual)
        let value = NeedsContainerBinding(client: client, needs: binding, selectedNeedsID: id, shellGeneration: shell.generation,
            session: session, sessionOperation: operation, synthetic: true, currentBinding: { [self] in observed() })
        #expect(host.bind(value))
    }
}
@Suite @MainActor struct NeedsContainerHostTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func response<T: Encodable>(_ key: String, _ value: T) throws -> Data {
        Data(("{\"request_id\":\"" + needsTrace + "\",\"" + key + "\":" + String(decoding: try JSONEncoder().encode(value), as: UTF8.self) + "}").utf8)
    }
    private func null(_ key: String) -> Data { Data("{\"request_id\":\"\(needsTrace)\",\"\(key)\":null}".utf8) }
    private func fields() throws -> NeedsSchema.NeedsFields {
        try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: Data(#"{"budget_total":{"state":"unknown"},"budget_paid":{"state":"known","value":"12.3400"},"party_size":{"state":"missing"},"pace":{"state":"uncertain","note":"unsure / 未定"}}"#.utf8))
    }
    private func snapshot(_ id: String = "needs-A", version: Int = 2) throws -> NeedsSchema.NeedsSnapshot {
        let fields = try fields()
        return .init(needs_id: id, version: version, source_kind: .user_provided,
                     content_utf8_base64: try JSONEncoder().encode(fields).base64EncodedString(), fields: fields)
    }
    private func original(_ id: String = "actionA", needsID: String = "needs-A") throws -> NeedsPending {
        try NeedsPending(command: .init(action_id: id, needs_id: needsID, expected_version: 1,
            source: .init(kind: .manual, text: "Original e\u{301}; dates undecided / 日期未定"),
            changes: .init(budget_total: .NeedsUnknownObservation(.init(state: .unknown)))))
    }
    private func receipt(_ action: NeedsPending) -> NeedsSchema.NeedsReceipt {
        .init(action_id: action.actionID, needs_id: action.needsID, version: action.command.expected_version + 1, operation: .manual_patch)
    }
    private func revision(_ action: NeedsPending) throws -> NeedsSchema.NeedsRevision {
        let fields = try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: JSONEncoder().encode(action.command.changes))
        return .init(needs_id: action.needsID, version: action.command.expected_version + 1, action_id: action.actionID, source_kind: .user_provided,
            original_input_utf8_base64: action.originalUTF8.base64EncodedString(), content_utf8_base64: try JSONEncoder().encode(fields).base64EncodedString(), fields: fields)
    }
    private func directory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]); return url
    }
    private func store(_ f: NeedsHostFixture, directory: URL, key: @escaping () throws -> SymmetricKey) throws -> NeedsPendingStore {
        try NeedsPendingStore(directory: directory, maximumBytes: 524_288, maximumRecords: 20,
            namespace: .init(environment: f.binding.environment, account: f.binding.account, purpose: .localNeedsPendingV1), keyID: UUID(), key: key)
    }
    private func wait(_ t: NeedsHostTransport) async {
        for _ in 0..<10000 { if await t.held { return }; await Task.yield() }; Issue.record("No held request")
    }
    @Test(arguments: ["Etc/UTC", "US/Eastern", "PRC"])
    func legalTimezoneAliasSurvivesHostReadEditAndRevision(alias: String) async throws {
        let zone = NeedsSchema.NeedsTimezoneObservation.NeedsTimezoneObservationKnown(.init(state: .known, value: alias))
        let event = NeedsSchema.NeedsEvent(date: .NeedsLocalDateObservationKnown(.init(state: .known, value: "2026-11-01")),
            time: .NeedsLocalTimeObservationKnown(.init(state: .known, value: "01:30:00")), timezone: zone,
            place: .NeedsUnknownObservation(.init(state: .unknown)))
        let changes = NeedsSchema.NeedsChanges(destination_timezone: zone, overseas_timezone: zone, arrival: event)
        let command = NeedsSchema.NeedsCommand(action_id: "alias-original", needs_id: "needs-A", expected_version: 1,
            source: .init(kind: .manual, text: "Original alias / 原样时区"), changes: changes)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let originalBytes = try encoder.encode(command)
        let fields = try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: encoder.encode(changes))
        let content = try encoder.encode(fields).base64EncodedString()
        let snapshot = NeedsSchema.NeedsSnapshot(needs_id: command.needs_id, version: 2, source_kind: .user_provided,
            content_utf8_base64: content, fields: fields)
        let revision = NeedsSchema.NeedsRevision(needs_id: command.needs_id, version: 2, action_id: command.action_id, source_kind: .user_provided,
            original_input_utf8_base64: originalBytes.base64EncodedString(), content_utf8_base64: content, fields: fields)
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture()
        let t = NeedsHostTransport([try response("needs", snapshot), try response("revision", revision)])
        try f.bind(h, shell: s, transport: t)
        let detailWork = h.prepareDetail(context: h.captureAction()); await h.perform(detailWork)
        #expect(h.presentation?.state == .loaded)
        var draft = try #require(h.presentation?.draft)
        #expect(draft.observations[.destinationTimezone]?.value == alias && draft.observations[.overseasTimezone]?.value == alias)
        #expect(draft.events[.arrival]?.timezone.value == alias && draft.events[.arrival]?.date.value == "2026-11-01")
        #expect(draft.events[.arrival]?.time.value == "01:30:00" && draft.changedFields.isEmpty)
        draft.sourceText = "Keep the original alias / 保留原样时区"
        draft.set(.destinationTimezone, .init(state: .known, value: alias))
        draft.set(.arrival, try #require(draft.events[.arrival]))
        #expect(h.updateDraft(draft, context: h.captureAction()))
        s.selectLanguage(.chinese)
        let frozen = try #require(h.presentation?.draft).freeze(actionID: "SYNTHETIC-LOCAL-ONLY")
        #expect(NeedsObservationInput(frozen.command.changes.destination_timezone).value == alias)
        #expect(NeedsObservationInput(frozen.command.changes.arrival?.timezone).value == alias)
        #expect(frozen.command.expected_version == 2 && frozen.command.changes.budget_total == nil)
        let revisionWork = h.prepareRevision(2, context: h.captureAction()); await h.perform(revisionWork)
        #expect(h.presentation?.state == .loaded && h.presentation?.revision?.original_input_utf8_base64 == originalBytes.base64EncodedString())
        #expect(h.presentation?.draft?.editorID == draft.editorID && h.presentation?.draft?.events[.arrival]?.time.value == "01:30:00")
        #expect(!h.canSave && h.presentation?.canSave == false)
        #expect(await t.calls.map(\.0) == ["getNeeds", "getNeedsRevision"])
        #expect(await t.calls.allSatisfy { $0.1 == .get })
    }
    @Test(arguments: ["accepted-aba", "rejected-editor", "sequential"])
    func localEditRevisionTracksOnlyAcceptedWrites(mode: String) async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture()
        let t = NeedsHostTransport([try response("needs", snapshot())])
        try f.bind(h, shell: s, transport: t); await h.perform(h.prepareDetail(context: h.captureAction()))
        let model = try #require(h.presentation), base = try #require(model.draft), context = try #require(h.captureAction())
        var outer = base; outer.sourceText = "Outer edit"; outer.set(.pace, .init(state: .known, value: "outer pace"))
        if mode == "sequential" {
            #expect(h.updateDraft(outer, context: context))
            var next = outer; next.sourceText = "Next ordinary edit"; next.set(.pace, .init(state: .known, value: "next pace"))
            #expect(h.updateDraft(next, context: context))
            #expect(model.draft?.sourceText == next.sourceText && model.draft?.observations[.pace]?.value == "next pace")
        } else {
            var callbackAccepted = false
            f.callback = {
                if mode == "accepted-aba" {
                    var intermediate = base; intermediate.sourceText = "Intermediate"; intermediate.set(.pace, .init(state: .known, value: "intermediate pace"))
                    let first = h.updateDraft(intermediate, context: h.captureAction())
                    let restored = h.updateDraft(base, context: h.captureAction())
                    callbackAccepted = first && restored
                } else {
                    let unrelatedEditor = NeedsDraft(needsID: base.needsID, expectedVersion: base.expectedVersion)
                    callbackAccepted = h.updateDraft(unrelatedEditor, context: h.captureAction())
                }
            }
            let accepted = h.updateDraft(outer, context: context)
            if mode == "accepted-aba" {
                #expect(callbackAccepted && !accepted)
                #expect(model.draft?.sourceText == base.sourceText && model.draft?.observations[.pace] == base.observations[.pace])
            } else {
                #expect(!callbackAccepted && accepted)
                #expect(model.draft?.sourceText == outer.sourceText && model.draft?.observations[.pace]?.value == "outer pace")
            }
        }
        #expect(model.draft?.editorID == base.editorID && model.draft?.expectedVersion == base.expectedVersion)
        #expect(model.draft?.needsID == base.needsID && !h.canSave)
        #expect(await t.calls.map(\.0) == ["getNeeds"])
    }
    @Test func defaultUnavailableAndBindingDoesNotFetchOrSave() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s)
        #expect(h.presentation == nil && h.prepareDetail(context: h.captureAction()) == nil && !h.canSave)
        let f = try NeedsHostFixture(), t = NeedsHostTransport([])
        try f.bind(h, shell: s, transport: t)
        #expect(h.presentation?.draft == nil && h.presentation?.canSave == false && f.credentials == 0)
        #expect(h.prepareRevision(0, context: h.captureAction()) == nil)
        #expect(h.prepareQuery("invented", context: h.captureAction()) == nil)
        #expect(await t.calls.isEmpty)
    }
    @Test func partialEditorPreservesUnknownDecimalAndOriginalRevision() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture()
        let t = NeedsHostTransport([try response("needs", snapshot()), try response("needs", snapshot(version: 9))])
        try f.bind(h, shell: s, transport: t); await h.perform(h.prepareDetail(context: h.captureAction()))
        let model = try #require(h.presentation)
        var draft = try #require(model.draft)
        #expect(draft.observations[.total]?.state == .unknown && draft.observations[.paid]?.value == "12.3400")
        #expect(draft.events[.arrival] == nil && draft.changedFields.isEmpty && draft.fixedItems.isEmpty)
        draft.sourceText = "Only update pace / 只改节奏"; draft.set(.pace, .init(state: .known, value: "slow / 慢"))
        #expect(h.updateDraft(draft, context: h.captureAction()))
        let identity = h.viewIdentity; s.selectLanguage(.chinese)
        #expect(h.presentation === model && h.viewIdentity == identity)
        await h.perform(h.prepareDetail(context: h.captureAction()))
        #expect(model.snapshot?.version == 9 && model.draft?.expectedVersion == 2)
        #expect(model.draft?.sourceText == draft.sourceText && model.draft?.changedFields == [.pace])
        let original = try #require(model.draft).freeze(actionID: "SYNTHETIC-LOCAL-ENCODING")
        #expect(original.command.changes.budget_total == nil && original.command.changes.arrival == nil)
        #expect(original.command.changes.party_size == nil && !h.canSave)
        #expect(await t.calls.map(\.0) == ["getNeeds", "getNeeds"])
    }
    @Test func missingAndInvalidReadsRemainDifferent() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture(), t = NeedsHostTransport([null("needs"), Data("{}".utf8)])
        try f.bind(h, shell: s, transport: t)
        await h.perform(h.prepareDetail(context: h.captureAction())); #expect(h.presentation?.state == .missing && h.presentation?.draft == nil)
        await h.perform(h.prepareDetail(context: h.captureAction())); #expect(h.presentation?.state == .failed)
    }
    @Test func originalQueryUsesExactHistoricalRevisionAndFiltersOtherNeeds() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture(), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), a = try original(), other = try original("other-action", needsID: "needs-B")
        let store = try store(f, directory: dir) { key }; try store.append(a); try store.append(other)
        let t = NeedsHostTransport([try response("receipt", receipt(a)), try response("revision", revision(a)), try response("needs", snapshot(version: 9))])
        try f.bind(h, shell: s, transport: t, store: store); h.loadPending(context: h.captureAction())
        #expect(h.pendingActions.map(\.actionID) == [a.actionID])
        #expect(h.prepareQuery(other.actionID, context: h.captureAction()) == nil)
        let work = h.prepareQuery(a.actionID, context: h.captureAction()); await h.perform(work)
        let model = try #require(h.presentation)
        #expect(model.state == .confirmed && model.receipt?.version == 2 && model.revision?.version == 2)
        #expect(model.revision?.original_input_utf8_base64 == a.originalUTF8.base64EncodedString())
        #expect(await t.calls.map(\.0) == ["queryNeedsAction", "getNeedsRevision"])
        #expect(await t.calls.last?.2.contains("version=2") == true)
        await h.perform(h.prepareDetail(context: h.captureAction()))
        #expect(model.snapshot?.version == 9 && model.receipt == nil) // latest is a separate read, not a receipt proof
        #expect(try store.pending().first(where: { $0.actionID == a.actionID })?.originalUTF8 == a.originalUTF8)
        #expect(await t.calls.allSatisfy { $0.1 == .get })
    }
    @Test(arguments: ["null", "revision-mismatch", "cancel"])
    func uncertainQueryNeverClaimsSavedOrResends(mode: String) async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture(), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256), a = try original(), store = try store(f, directory: dir) { key }
        try store.append(a)
        var altered = try revision(a); altered.original_input_utf8_base64 = Data("{}".utf8).base64EncodedString()
        let replies = mode == "revision-mismatch" ? [try response("receipt", receipt(a)), try response("revision", altered)] : [null("receipt")]
        let t = NeedsHostTransport(replies, holdFirst: mode == "cancel")
        try f.bind(h, shell: s, transport: t, store: store); h.loadPending(context: h.captureAction())
        let work = h.prepareQuery(a.actionID, context: h.captureAction()); let task = Task { await h.perform(work) }
        if mode == "cancel" { await wait(t); task.cancel(); await t.release() }
        await task.value
        #expect(h.presentation?.state == .unknown && h.presentation?.receipt == nil && !h.busy && !h.canSave)
        #expect(try store.pending().first?.originalUTF8 == a.originalUTF8)
        #expect(await t.calls.allSatisfy { $0.1 == .get })
    }
    @Test func queuedWorkAndEditorCannotRetargetNewSelection() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), a = try NeedsHostFixture(), b = try NeedsHostFixture()
        let ta = NeedsHostTransport([try response("needs", snapshot())]), tb = NeedsHostTransport([try response("needs", snapshot("needs-B"))])
        try a.bind(h, shell: s, transport: ta); await h.perform(h.prepareDetail(context: h.captureAction()))
        let oldContext = h.captureAction(), oldModel = h.presentation, oldDraft = try #require(h.presentation?.draft)
        let oldWork = h.prepareRevision(2, context: h.captureAction())
        h.invalidate(); try b.bind(h, shell: s, transport: tb, id: "needs-B")
        await h.perform(oldWork)
        #expect(!h.updateDraft(oldDraft, context: oldContext))
        #expect(oldModel?.draft == nil && oldModel?.snapshot == nil)
        #expect(await ta.calls.count == 1); #expect(await tb.calls.isEmpty)
        await h.perform(h.prepareDetail(context: h.captureAction()))
        #expect(h.presentation?.snapshot?.needs_id == "needs-B")
    }
    @Test(arguments: [false, true]) func lateReadAfterIdentityOrBackgroundCannotOverwriteB(background: Bool) async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), a = try NeedsHostFixture(), b = try NeedsHostFixture()
        let ta = NeedsHostTransport([try response("needs", snapshot())], holdFirst: true)
        try a.bind(h, shell: s, transport: ta)
        let old = h.presentation, work = h.prepareDetail(context: h.captureAction())
        let task = Task { await h.perform(work) }; await wait(ta)
        if background { h.suspendForBackground() } else { s.invalidateIdentity() }
        #expect(h.presentation == nil && old?.draft == nil && !h.busy)
        s.messageBindingBlocked = false // synthetic trusted-root renewal only
        let tb = NeedsHostTransport([try response("needs", snapshot("needs-B"))])
        try b.bind(h, shell: s, transport: tb, id: "needs-B"); await h.perform(h.prepareDetail(context: h.captureAction()))
        await ta.release(); await task.value
        #expect(h.presentation?.snapshot?.needs_id == "needs-B" && !h.busy)
    }
    @Test func callbackReentryAndRetiredSessionDoNotCreateWork() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), a = try NeedsHostFixture(), b = try NeedsHostFixture()
        let ta = NeedsHostTransport([]), tb = NeedsHostTransport([])
        try a.bind(h, shell: s, transport: ta)
        let old = h.captureAction()
        a.callback = { h.invalidate(); try! b.bind(h, shell: s, transport: tb, id: "needs-B") }
        #expect(h.prepareDetail(context: old) == nil && h.presentation?.binding == b.binding)
        try b.session.clear(); #expect(h.presentation == nil && h.captureAction() == nil)
        #expect(await ta.calls.isEmpty); #expect(await tb.calls.isEmpty)
    }
    @Test func duplicateWorkCannotClearInFlightBusy() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture(), t = NeedsHostTransport([null("needs")], holdFirst: true)
        try f.bind(h, shell: s, transport: t)
        let work = h.prepareDetail(context: h.captureAction()); let task = Task { await h.perform(work) }; await wait(t)
        await h.perform(work); #expect(h.busy)
        await t.release(); await task.value; await h.perform(work)
        #expect(!h.busy && h.presentation?.state == .missing); #expect(await t.calls.count == 1)
    }
    @Test func pendingKeyCallbackCannotPublishIntoReplacementSelection() async throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), a = try NeedsHostFixture(), b = try NeedsHostFixture(), dir = try directory()
        defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256); var callback: (() -> Void)?
        let store = try store(a, directory: dir) { let run = callback; callback = nil; run?(); return key }
        try store.append(original())
        let ta = NeedsHostTransport([]), tb = NeedsHostTransport([try response("needs", snapshot("needs-B"))])
        try a.bind(h, shell: s, transport: ta, store: store)
        let previous = h.presentation
        callback = { h.invalidate(); try! b.bind(h, shell: s, transport: tb, id: "needs-B") }
        h.loadPending(context: h.captureAction())
        #expect(previous?.binding == nil && previous?.pendingActions.isEmpty == true)
        #expect(h.presentation?.binding == b.binding && h.pendingActions.isEmpty && !h.busy)
        await h.perform(h.prepareDetail(context: h.captureAction()))
        #expect(h.presentation?.snapshot?.needs_id == "needs-B")
        #expect(await ta.calls.isEmpty); #expect(await tb.calls.map(\.0) == ["getNeeds"])
    }
    @Test func missingStoreOrOriginalKeyIsNotEmptySuccess() throws {
        let s = try shell(), h = NeedsContainerHost(shell: s), f = try NeedsHostFixture(), t = NeedsHostTransport([])
        try f.bind(h, shell: s, transport: t); h.loadPending(context: h.captureAction())
        #expect(h.presentation?.pendingState == .failed && h.pendingActions.isEmpty)
        h.invalidate()
        let dir = try directory(); defer { try? FileManager.default.removeItem(at: dir) }
        let key = SymmetricKey(size: .bits256); var available = true
        let store = try store(f, directory: dir) { guard available else { throw NeedsFailure.keyUnavailable }; return key }
        let a = try original(); try store.append(a); available = false
        try f.bind(h, shell: s, transport: t, store: store); h.loadPending(context: h.captureAction())
        #expect(h.presentation?.pendingState == .failed && h.prepareQuery(a.actionID, context: h.captureAction()) == nil)
        #expect(f.credentials == 0)
    }
}

extension NeedsContainerHostTests {
    @Test func localWriterFreezesOneOriginalBeforeAsyncDispatch() async throws {
        let s = try shell(), host = NeedsContainerHost(shell:s), f = try NeedsHostFixture()
        let root = try directory(); defer { try? FileManager.default.removeItem(at:root) }
        let store = try store(f,directory:root,key:{SymmetricKey(data:Data(repeating:7,count:32))})
        let wire = NeedsHostTransport([]); try f.bind(host,shell:s,transport:wire,store:store,manual:true)
        #expect(host.beginNew(context:host.captureAction()))
        var draft = try #require(host.presentation?.draft)
        draft.sourceText = "SYNTHETIC explicit manual input"; draft.set(.partySize,.init(state:.known,value:"3"))
        #expect(host.updateDraft(draft,context:host.captureAction()))
        let work = try #require(host.prepareSave(context:host.captureAction()))
        let id = try #require(host.presentation?.selectedActionID), original = try draft.freeze(actionID:id)
        #expect(try store.pending().isEmpty && host.busy)
        #expect(!host.beginNew(context:host.captureAction()))
        await wire.add(try response("receipt",receipt(original)))
        await wire.add(try response("revision",revision(original)))
        await host.perform(work)
        #expect(host.presentation?.state == .confirmed && !host.busy)
        #expect(await wire.bodies == [original.originalUTF8])
        #expect(try store.pending().map(\.originalUTF8) == [original.originalUTF8])
    }
    @Test func unknownPrefixBlocksBeforeMintingAnotherActionID() throws {
        let s = try shell(), host = NeedsContainerHost(shell:s), f = try NeedsHostFixture()
        let root = try directory(); defer { try? FileManager.default.removeItem(at:root) }
        let store = try store(f,directory:root,key:{SymmetricKey(data:Data(repeating:8,count:32))})
        let unknown = try original(); try store.append(unknown)
        let wire = NeedsHostTransport([]); try f.bind(host,shell:s,transport:wire,store:store,manual:true)
        #expect(host.beginNew(context:host.captureAction()))
        var draft = try #require(host.presentation?.draft)
        draft.sourceText = "A new local edit"; draft.set(.partySize,.init(state:.known,value:"4"))
        #expect(host.updateDraft(draft,context:host.captureAction()))
        #expect(host.prepareSave(context:host.captureAction()) == nil)
        #expect(host.presentation?.selectedActionID == nil && host.manualIssue == .reconcileOriginals)
        #expect(try store.pending().map(\.originalUTF8) == [unknown.originalUTF8])
    }
    @Test func cancellingPossibleSaveKeepsOriginalQueryOnly() async throws {
        let s = try shell(), host = NeedsContainerHost(shell:s), f = try NeedsHostFixture()
        let root = try directory(); defer { try? FileManager.default.removeItem(at:root) }
        let store = try store(f,directory:root,key:{SymmetricKey(data:Data(repeating:9,count:32))})
        let wire = NeedsHostTransport([],holdFirst:true); try f.bind(host,shell:s,transport:wire,store:store,manual:true)
        #expect(host.beginNew(context:host.captureAction()))
        var draft = try #require(host.presentation?.draft)
        draft.sourceText = "SYNTHETIC cancellable save"; draft.set(.partySize,.init(state:.known,value:"3"))
        #expect(host.updateDraft(draft,context:host.captureAction()))
        let work = try #require(host.prepareSave(context:host.captureAction()))
        let id = try #require(host.presentation?.selectedActionID), original = try draft.freeze(actionID:id)
        await wire.add(try response("receipt",receipt(original)))
        let task = Task { await host.perform(work) }; await wait(wire)
        host.cancel(host.captureCancellation()); await wire.release(); await task.value
        #expect(host.presentation?.state == .unknown && !host.busy)
        #expect(try store.pending().map(\.originalUTF8) == [original.originalUTF8])
        #expect(host.prepareSave(context:host.captureAction()) == nil)
        #expect(host.presentation?.selectedActionID == id && host.manualIssue == .reconcileOriginals)
    }
}
