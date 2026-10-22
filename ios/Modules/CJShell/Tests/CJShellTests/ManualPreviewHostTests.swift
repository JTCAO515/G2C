import Foundation
import Testing
import CJAPI
import CJSession
@testable import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJTripClient
@testable import CJManualPreviewClient
@testable import CJShell

private let manualTrace = "00000000-0000-4000-8000-000000000017"
@MainActor private struct ManualSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ value: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private actor ManualHostWire: ClientTransport {
    var source: Data
    var preview: Data
    var previewCode: Int
    var sourceCalls = 0
    var previewCalls: [Data] = []
    var holdNextSource = false
    var sourceHeld = false
    var sourceContinuation: CheckedContinuation<Void, Never>?
    init(source: Data, preview: Data, code: Int = 200) { self.source = source; self.preview = preview; previewCode = code }
    func holdSource() { holdNextSource = true }
    func releaseSource() { sourceContinuation?.resume(); sourceContinuation = nil }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data
        let code: Int
        if operationID == "getTrip" {
            #expect(request.method == .get && body == nil)
            sourceCalls += 1; bytes = source; code = 200
            if holdNextSource { holdNextSource = false; sourceHeld = true; await withCheckedContinuation { sourceContinuation = $0 } }
        } else {
            #expect(operationID == "previewManualTripEdit" && request.method == .post && request.path == "/v1/trip-manual-previews")
            let input = try await Data(collecting: #require(body), upTo: 100_000)
            previewCalls.append(input); bytes = preview; code = previewCode
        }
        var response = HTTPResponse(status: .init(code: code))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = manualTrace
        response.headerFields[.contentType] = "application/json"; response.headerFields[.cacheControl] = "no-store"
        return (response, HTTPBody(bytes))
    }
}
private struct OrdinaryHostInjection: ClientTransport {
    let downstream: any ClientTransport
    let value: String
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        var request = request
        request.headerFields.append(HTTPField(name: HTTPField.Name("Host")!, value: value))
        return try await downstream.send(request, body: body, baseURL: baseURL, operationID: operationID)
    }
}
@MainActor private final class ManualSourceState {
    let binding = TripBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: TripBinding?
    var callback: (() -> Void)?
    init() { current = binding }
    func observed() -> TripBinding? { let old = current; let run = callback; callback = nil; run?(); return old }
}
@MainActor private final class ManualFactoryControl {
    var sourceBytes: Data?
    var afterMake: ((PreviewEditor) -> Void)?
    var onValidation: (() throws -> Void)?
    var hostOverride: String?
}
@MainActor private final class ManualHostFixture {
    let shell: ShellState
    let state = ManualSourceState()
    let control = ManualFactoryControl()
    let session = SessionLifecycle(persistence: ManualSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let host: TripContainerHost
    let wire: ManualHostWire
    let sourceBytes: Data
    let original: Components.Schemas.TripRecord
    let resources: ManualPreviewResources
    static func encode<T: Encodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]; return try encoder.encode(value)
    }
    init(shell: ShellState, code: Int = 200, sourceNull: Bool = false, publicHost: Bool = false, legacyTransport: Bool = false) throws {
        self.shell = shell
        operation = try session.beginTrustedSDKSave()
        let document = Components.Schemas.TripDocument(title: "Original e\u{301}", items: [
            .init(id: "a", text: "Original A", verification: .verified, evidence: ["source-a"]),
            .init(id: "b", text: "Original B", verification: .pending, evidence: [])])
        original = .init(trip_id: "trip17", version: 7, content_utf8_base64: try Self.encode(document).base64EncodedString(), document: document)
        sourceBytes = sourceNull ? Data("{\"request_id\":\"\(manualTrace)\",\"trip\":null}".utf8)
            : Data(("{\n \"request_id\":\"\(manualTrace)\",\"trip\":" + String(decoding: try Self.encode(original), as: UTF8.self) + "\n}").utf8)
        var after = document; after.title = "User e\u{301} draft"
        let diff = Components.Schemas.ManualPreviewChange(path: ["title"], before_utf8_base64: try Self.encode(document.title).base64EncodedString(), after_utf8_base64: try Self.encode(after.title).base64EncodedString())
        let p = Components.Schemas.ManualPreview(preview_status: .LOCAL, original: original, content_utf8_base64: try Self.encode(after).base64EncodedString(),
            document: after, selected_ids: [], title_selected: true, protection_status: .UNKNOWN, can_save: false, diff: [diff])
        let response: Data
        if code == 200 { response = try Self.encode(Components.Schemas.ManualPreviewResponse(request_id: manualTrace, preview: p)) }
        else { response = try Self.encode(Components.Schemas.ErrorResponse(request_id: manualTrace, error: .init(code: "UNAVAILABLE", category: "base", message_en: "Unavailable", message_zh: "不可用", outcome: .unknown, recovery: .do_not_retry))) }
        wire = ManualHostWire(source: sourceBytes, preview: response, code: code)
        let endpoint = try MessageEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 100_000, maximumResponseBytes: 100_000)
        resources = try ManualPreviewResources(endpoint: endpoint, credentials: { _ in "SYNTHETIC" }, previewRequestTimeout: 1, previewResourceTimeout: 1)
        let wire = wire, control = control
        host = publicHost ? TripContainerHost(shell: shell) : TripContainerHost(shell: shell, makeManualEditor: { trip, source, session, operation, resources in
            let received = try trip.withCurrentDetailSnapshot(source) { bytes, _, _, _ in bytes }
            control.sourceBytes = received
            let editor: PreviewEditor
            if legacyTransport {
                editor = try PreviewEditor(trip: trip, source: source, endpoint: resources.endpoint, session: session, operation: operation,
                    credentials: resources.credentials, liveTransport: NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1))
            } else {
                editor = try PreviewEditor(trip: trip, source: source, endpoint: resources.endpoint, session: session, operation: operation,
                    credentials: resources.credentials, transportFactory: { validate in
                        let transport = try NoRedirectTransport(interceptedTransport: wire, previewEndpoint: resources.endpoint, validatePreview: {
                            let callback = control.onValidation; control.onValidation = nil
                            try callback?(); try validate()
                        })
                        if let host = control.hostOverride { return OrdinaryHostInjection(downstream: transport, value: host) }
                        return transport
                    })
            }
            let callback = control.afterMake; control.afterMake = nil
            callback?(editor)
            return editor
        })
    }
    func bind(resources provided: Bool = true) throws {
        let state = state
        let client = TripClient(endpoint: resources.endpoint, credentials: resources.credentials, currentBinding: { state.observed() },
            session: session, sessionOperation: operation, interceptedTransport: wire)
        let value = TripContainerBinding(client: client, trip: state.binding, shellGeneration: shell.generation, session: session, sessionOperation: operation,
            pageSize: 2, currentTripID: original.trip_id, synthetic: true, manualPreviewResources: provided ? resources : nil,
            currentBinding: { state.observed() })
        #expect(host.bind(value)); host.setManualForeground(true)
        #expect(host.selectTrip(original.trip_id, context: host.captureAction()))
    }
    func open() async throws -> (ManualPreviewEntry, PreviewEditor) {
        let work = try #require(host.prepareManualEditor(context: host.captureAction()))
        let entry = try #require(await host.performManualEditor(work))
        return (entry, try #require(host.manualEditor(for: entry)))
    }
}
@Suite @MainActor struct ManualPreviewHostTests {
    private func shell() throws -> ShellState { ShellState(preferences: try #require(UserDefaults(suiteName: UUID().uuidString))) }
    private func wait(_ wire: ManualHostWire) async {
        for _ in 0..<10000 { if await wire.sourceHeld { return }; await Task.yield() }; Issue.record("Original read not held")
    }
    @Test(arguments: [1, 2])
    func nestedPreparationThroughHostDoesNotNeedOlderCaller(trigger: Int) async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind()
        let (entry, editor) = try await f.open()
        try editor.selectTitle(true); try editor.setTitle("User e\u{301} draft")
        var checks = 0
        var newer: PreviewWork?
        func prepareOnCheck() {
            checks += 1
            if checks < trigger { f.state.callback = prepareOnCheck }
            else { newer = try? editor.preparePreview() }
        }
        f.state.callback = prepareOnCheck
        let older = try? editor.preparePreview() // permitted caller discard; never perform/cancel it
        #expect(older == nil)
        let work = try #require(newer)
        await editor.perform(work)
        #expect(editor.display()?.status == .local && editor.display()?.title == "User e\u{301} draft")
        #expect(await f.wire.previewCalls == [work.bytes])
        #expect(f.host.manualEditor(for: entry) === editor && !f.host.busy)
    }
    @Test func nestedWorkCancelAndOldCloseCannotRetireRenewedEntry() async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind()
        let (oldEntry, oldEditor) = try await f.open()
        try oldEditor.selectTitle(true); try oldEditor.setTitle("User e\u{301} draft")
        var newer: PreviewWork?
        f.state.callback = { newer = try? oldEditor.preparePreview() }
        let older = try? oldEditor.preparePreview()
        #expect(older == nil)
        let oldWork = try #require(newer)
        oldEditor.cancelPreview()
        #expect(oldEditor.display()?.status == .unknown && oldEditor.display()?.title == "User e\u{301} draft")
        #expect(f.host.selectTrip(f.original.trip_id, context: f.host.captureAction()))
        let (entry, editor) = try await f.open()
        try editor.selectTitle(true); try editor.setTitle("User e\u{301} draft")
        f.host.retireManualPreview(oldEntry)
        await oldEditor.perform(oldWork)
        #expect(f.host.manualEditor(for: entry) === editor && oldEditor.display() == nil)
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.status == .local && editor.display()?.preview?.can_save == false)
        #expect(await f.wire.previewCalls == [work.bytes])
    }
    @Test(arguments: ["synthetic.invalid", "other.invalid"])
    func ordinaryHostIsRejectedByActualSharedCapabilityAndKeepsDraft(hostValue: String) async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind()
        let (_, editor) = try await f.open()
        try editor.selectTitle(true); try editor.setTitle("User e\u{301} draft")
        f.control.hostOverride = hostValue
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(await f.wire.previewCalls.isEmpty, "Ordinary Host must not reach underlying transport, even when same-origin")
        #expect(editor.display()?.status == .unavailable && editor.display()?.preview == nil)
        #expect(editor.display()?.title == "User e\u{301} draft" && editor.display()?.original.version == 7)
    }
    @Test func defaultAndMissingResourcesCannotInventEditor() async throws {
        let host = TripContainerHost(shell: try shell())
        #expect(host.prepareManualEditor(context: host.captureAction()) == nil && !host.canPrepareManualEditor)
        let f = try ManualHostFixture(shell: shell()); try f.bind(resources: false)
        #expect(f.host.prepareManualEditor(context: f.host.captureAction()) == nil)
        #expect(f.host.manualEditorState == .unavailable)
        #expect(await f.wire.sourceCalls == 0 && f.host.manualPreviewIdentity == nil)
    }
    @Test func closedFormalGetOpensDraftAndUsesServerDiffOnly() async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind()
        let (entry, editor) = try await f.open()
        #expect(f.control.sourceBytes == f.sourceBytes && f.host.manualEditorState == .ready)
        #expect(editor.display()?.original.version == 7 && editor.display()?.original.content_utf8_base64 == f.original.content_utf8_base64)
        try editor.selectTitle(true); try editor.setTitle("User e\u{301} draft")
        let work = try editor.preparePreview(); await editor.perform(work)
        let display = try #require(editor.display())
        #expect(display.status == .local && display.preview?.can_save == false && display.preview?.protection_status == .UNKNOWN)
        #expect(display.preview?.diff.first?.path == ["title"] && display.preview?.diff.count == 1)
        #expect(await f.wire.previewCalls == [work.bytes])
        #expect(await f.wire.sourceCalls == 1)
        #expect(f.host.manualEditor(for: entry) === editor)
    }
    @Test(arguments: [409, 503]) func conflictAndUnknownKeepOriginalDraftWithoutRebase(code: Int) async throws {
        let f = try ManualHostFixture(shell: shell(), code: code); try f.bind()
        let (_, editor) = try await f.open()
        try editor.selectTitle(true); try editor.setTitle("Keep original intent")
        let work = try editor.preparePreview(); await editor.perform(work)
        let display = try #require(editor.display())
        #expect(display.title == "Keep original intent" && display.original.version == 7 && display.preview == nil)
        #expect(display.status == (code == 409 ? .conflict : .unknown))
        let next = try editor.preparePreview(); #expect(next.bytes == work.bytes)
        #expect(await f.wire.sourceCalls == 1); #expect(await f.wire.previewCalls.count == 1)
    }
    @Test func legacyPublicTransportGateRetainsDraft() async throws {
        let f = try ManualHostFixture(shell: shell(), legacyTransport: true); try f.bind()
        let (_, editor) = try await f.open()
        try editor.selectTitle(true); try editor.setTitle("Retain at default gate")
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.status == .unavailable && editor.display()?.title == "Retain at default gate")
        #expect(editor.display()?.preview == nil)
        #expect(await f.wire.previewCalls.isEmpty)
    }
    @Test func publicFactoryCanRetirePreparedPreviewBeforeAnyNetworking() async throws {
        let f = try ManualHostFixture(shell: shell(), publicHost: true); try f.bind()
        let (entry, editor) = try await f.open()
        try editor.selectTitle(true); try editor.setTitle("Retire before networking")
        let work = try editor.preparePreview()
        f.host.retireManualPreview(entry); await editor.perform(work)
        #expect(editor.display() == nil && f.host.manualPreviewIdentity == nil)
        #expect(await f.wire.sourceCalls == 1); #expect(await f.wire.previewCalls.isEmpty)
    }
    @Test func nullFormalGetCannotBecomeAcceptedEditor() async throws {
        let f = try ManualHostFixture(shell: shell(), sourceNull: true); try f.bind()
        let work = f.host.prepareManualEditor(context: f.host.captureAction())
        #expect(await f.host.performManualEditor(work) == nil)
        #expect(f.host.manualEditorState == .missing && !f.host.busy && f.host.manualPreviewIdentity == nil)
    }
    @Test func sourceSelectionABAAndOldCloseDoNotRetireNewEditor() async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind()
        let (oldEntry, oldEditor) = try await f.open()
        let oldWork = try oldEditor.preparePreview()
        #expect(f.host.selectTrip(f.original.trip_id, context: f.host.captureAction()))
        let (newEntry, newEditor) = try await f.open()
        try newEditor.selectTitle(true); try newEditor.setTitle("New selection")
        f.host.retireManualPreview(oldEntry); await oldEditor.perform(oldWork)
        #expect(oldEditor.display() == nil && f.host.manualEditor(for: oldEntry) == nil)
        #expect(f.host.manualEditor(for: newEntry) === newEditor && newEditor.display()?.title == "New selection")
        #expect(await f.wire.previewCalls.isEmpty)
    }
    @Test func backgroundCancelsOldSourceReadWithoutStrandingOrClearingNewWork() async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind(); await f.wire.holdSource()
        let old = f.host.prepareManualEditor(context: f.host.captureAction())
        let task = Task { await f.host.performManualEditor(old) }; await wait(f.wire)
        f.host.setManualForeground(false); #expect(!f.host.busy && f.host.manualPreviewIdentity == nil)
        f.host.setManualForeground(true)
        let (entry, editor) = try await f.open()
        try editor.selectTitle(true); try editor.setTitle("Foreground renewed")
        await f.wire.releaseSource(); #expect(await task.value == nil)
        #expect(f.host.manualEditor(for: entry) === editor && editor.display()?.title == "Foreground renewed" && !f.host.busy)
    }
    @Test func finalSourceCallbackSessionRetirementWithholdsEditorAndSettlesOldLoad() async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind()
        f.control.afterMake = { _ in f.state.callback = { try! f.session.clear() } }
        let work = f.host.prepareManualEditor(context: f.host.captureAction())
        #expect(await f.host.performManualEditor(work) == nil)
        #expect(!f.host.busy && f.host.manualPreviewIdentity == nil)
    }
    @Test(arguments: ["background", "edit-aba"])
    func lastSharedValidationRejectsRetiredForegroundOrRevision(change: String) async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind()
        let (entry, editor) = try await f.open()
        let work = try editor.preparePreview()
        f.control.onValidation = {
            if change == "background" { f.host.setManualForeground(false) }
            else {
                try editor.selectTitle(true); try editor.setTitle("New callback input"); try editor.setTitle(f.original.document.title)
            }
        }
        await editor.perform(work)
        #expect(await f.wire.previewCalls.isEmpty)
        if change == "background" {
            #expect(editor.display() == nil && f.host.manualEditor(for: entry) == nil)
        } else {
            #expect(editor.display()?.title == f.original.document.title && editor.display()?.status == .editing)
            #expect(editor.display()?.preview == nil && f.host.manualEditor(for: entry) === editor)
        }
    }
    @Test func currentEditorRevisionABARejectsQueuedPreviewWithoutLosingNewIntent() async throws {
        let f = try ManualHostFixture(shell: shell()); try f.bind()
        let (_, editor) = try await f.open()
        let old = try editor.preparePreview()
        try editor.selectTitle(true); try editor.setTitle("Temporary"); try editor.setTitle(f.original.document.title)
        await editor.perform(old)
        #expect(editor.display()?.status == .editing && editor.display()?.title == f.original.document.title)
        #expect(await f.wire.previewCalls.isEmpty)
    }
}
