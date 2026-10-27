import Foundation
import CryptoKit
import Testing
import CJSession
import CJFeasibilityClient
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJNeedsClient
@testable import CJShell

private actor Transport: ClientTransport {
    let bytes: Data
    var calls = 0
    init(_ bytes: Data) { self.bytes = bytes }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        calls += 1
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = "00000000-0000-4000-8000-000000000001"
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(bytes))
    }
}
@MainActor private struct Store: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class Fixture {
    let shell = ShellState()
    let host: NeedsContainerHost
    let session = SessionLifecycle(persistence: Store(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    var needs = NeedsBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: NeedsBinding?
    var callback: (() -> Void)?
    let snapshot: NeedsSchema.NeedsSnapshot
    let bytes: Data
    let transport: Transport
    init() throws {
        host = NeedsContainerHost(shell: shell)
        operation = try session.beginTrustedSDKSave()
        // Deliberate whitespace/order and decomposed unicode: hashing re-encoded fields would fail.
        bytes = Data("{ \"pace\": {\"state\":\"known\",\"value\":\"e\u{301}\"}, \"budget_paid\": {\"state\":\"known\",\"value\":\"12.3400\"} }".utf8)
        snapshot = .init(needs_id: "needs-A", version: 2, source_kind: .user_provided,
            content_utf8_base64: bytes.base64EncodedString(), fields: try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: bytes))
        let value = String(decoding: try JSONEncoder().encode(snapshot), as: UTF8.self)
        transport = Transport(Data("{\"request_id\":\"00000000-0000-4000-8000-000000000001\",\"needs\":\(value)}".utf8))
        current = needs
        try bind()
    }
    func observed() -> NeedsBinding? {
        let original = current, run = callback
        callback = nil; run?()
        return original
    }
    func bind() throws {
        let client = NeedsClient(endpoint: try NeedsEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 131072, maximumResponseBytes: 1048576),
            credentials: { _ in "SYNTHETIC" }, currentBinding: { [self] in observed() }, pendingStore: nil, interceptedTransport: transport)
        let binding = NeedsContainerBinding(client: client, needs: needs, selectedNeedsID: "needs-A", shellGeneration: shell.generation,
            session: session, sessionOperation: operation, synthetic: true, currentBinding: { [self] in observed() })
        #expect(host.bind(binding))
    }
    func load() async { await host.perform(host.prepareDetail(context: host.captureAction())) }
    func open() throws -> FeasibilityHostPresentation {
        #expect(host.openFeasibility(context: host.captureAction()))
        return try #require(host.feasibilityPresentation)
    }
}
@Suite @MainActor struct FeasibilityHostTests {
    @Test func exactSourceAndClosedPublicModel() async throws {
        let f = try Fixture()
        #expect(!f.host.openFeasibility(context: f.host.captureAction()))
        await f.load()
        let entry = try f.open()
        #expect(entry.snapshot == f.snapshot)
        #expect(entry.binding.needsID == "needs-A" && entry.binding.acceptedRevision == 2)
        #expect(entry.binding.acceptedContentSHA256 == SHA256.hash(data: f.bytes).map { String(format: "%02x", $0) }.joined())
        #expect(entry.binding.selection == f.needs.selection)
        #expect(entry.binding.account == f.needs.account && entry.binding.environment == f.needs.environment)
        #expect(throws: FeasibilityFailure.unavailable) { _ = try entry.model.prepare(entry.binding) }
        if case .unavailable = entry.model.state {} else { Issue.record("Public model must remain closed") }
        #expect(await f.transport.calls == 1) // NEEDS fixture only; no FEAS call exists.
        #expect(!f.host.canSave)
    }
    @Test(arguments: ["refresh", "revision", "query", "background", "container-exit", "identity"])
    func synchronousInvalidation(event: String) async throws {
        let f = try Fixture(); await f.load(); let entry = try f.open()
        switch event {
        case "refresh": _ = f.host.prepareDetail(context: f.host.captureAction())
        case "revision": _ = f.host.prepareRevision(1, context: f.host.captureAction())
        case "query":
            // A rejected action does not change the accepted source.
            #expect(f.host.prepareQuery("missing", context: f.host.captureAction()) == nil)
            #expect(f.host.feasibilityPresentation === entry)
            f.host.invalidate()
        case "background": f.host.suspendForBackground()
        case "container-exit": f.host.leaveContainer(id: try #require(f.host.viewIdentity))
        default: f.host.invalidate()
        }
        #expect(f.host.feasibilityPresentation == nil)
        if event == "container-exit" { #expect(f.host.presentation?.snapshot == f.snapshot) }
        #expect(throws: FeasibilityFailure.stale) { _ = try entry.model.prepare(entry.binding) }
    }
    @Test(arguments: ["account", "environment", "selection", "session", "shell"])
    func currentIdentityChangesHideOldSource(event: String) async throws {
        let f = try Fixture(); await f.load(); let entry = try f.open()
        switch event {
        case "session": _ = try f.session.beginTrustedSDKSave()
        case "shell": f.shell.invalidateIdentity()
        default:
            let old = f.needs
            f.current = .init(environment: event == "environment" ? UUID() : old.environment,
                account: event == "account" ? UUID() : old.account, generation: old.generation,
                selection: event == "selection" ? UUID() : old.selection)
        }
        #expect(f.host.feasibilityPresentation == nil)
        #expect(throws: FeasibilityFailure.stale) { _ = try entry.model.prepare(entry.binding) }
    }
    @Test func oldExitAndCancellationCannotClearNewPresentationOrABA() async throws {
        let f = try Fixture(); await f.load(); let a = try f.open()
        let oldContainer = try #require(f.host.viewIdentity)
        f.host.invalidate()
        f.needs = .init(environment: f.needs.environment, account: f.needs.account, generation: f.needs.generation, selection: UUID())
        f.current = f.needs; try f.bind(); await f.load(); let b = try f.open()
        f.host.dismissFeasibility(id: a.id)
        f.host.leaveContainer(id: oldContainer)
        #expect(f.host.feasibilityPresentation === b)
        let late = Task { @MainActor in f.host.dismissFeasibility(id: a.id) }
        late.cancel(); await late.value
        #expect(f.host.feasibilityPresentation === b)
        let c = try f.open() // same accepted A source, fresh presentation ID
        f.host.dismissFeasibility(id: b.id)
        #expect(c.id != a.id && c.id != b.id && f.host.feasibilityPresentation === c)
    }
    @Test func reentrantOpenAndRefreshDoNotReplaceNewerResult() async throws {
        let f = try Fixture(); await f.load(); let action = f.host.captureAction()
        var newer: FeasibilityHostPresentation?
        f.callback = { newer = try? f.open() }
        #expect(!f.host.openFeasibility(context: action))
        #expect(f.host.feasibilityPresentation === newer)
        var refresh: NeedsContainerWork?
        f.callback = { refresh = f.host.prepareDetail(context: f.host.captureAction()) }
        #expect(f.host.feasibilityPresentation == nil)
        await f.host.perform(refresh)
        #expect(f.host.feasibilityPresentation == nil) // refresh cannot auto-evaluate
        _ = try f.open()
    }
    @Test func draftDoesNotBecomeSourceAndLanguageDoesNotChangeIdentity() async throws {
        let f = try Fixture(); await f.load(); let entry = try f.open()
        var draft = try #require(f.host.presentation?.draft)
        draft.sourceText = "Unsaved correction / 未保存"
        #expect(f.host.updateDraft(draft, context: f.host.captureAction()))
        #expect(f.host.feasibilityPresentation === entry && entry.snapshot == f.snapshot)
        #expect(ShellLanguage.english.text("Unknown", "待核实") == "Unknown")
        #expect(ShellLanguage.chinese.text("Unknown", "待核实") == "待核实")
    }
    @Test func removedCurrentSourceCannotUseDraftOrRetainedSnapshot() async throws {
        let f = try Fixture(); await f.load(); let entry = try f.open()
        f.host.presentation?.beginNew(id: "needs-B")
        #expect(f.host.feasibilityPresentation == nil)
        #expect(!f.host.openFeasibility(context: f.host.captureAction()))
        #expect(throws: FeasibilityFailure.stale) { _ = try entry.model.prepare(entry.binding) }
    }

}

import Observation
@MainActor private final class HostObservationProbeBox { var fired = false; var replacement: UUID? }
extension FeasibilityHostTests {
 @Test func testingObservedOpenMustNotOverwriteReentrantPresentation() async throws {
  let f = try Fixture(); await f.load()
  let box = HostObservationProbeBox()
  withObservationTracking {
   _ = f.host.feasibilityPresentation
  } onChange: {
   MainActor.assumeIsolated {
    guard !box.fired else { return }; box.fired = true
    #expect(f.host.openFeasibility(context: f.host.captureAction()))
    box.replacement = f.host.feasibilityPresentation?.id
   }
  }
  #expect(f.host.openFeasibility(context: f.host.captureAction()))
  #expect(box.fired && box.replacement != nil)
  #expect(f.host.feasibilityPresentation?.id == box.replacement)
 }
}

extension FeasibilityHostTests {
    @Test(arguments: ["replace", "dismiss", "leave"])
    func observationMutationKeepsNewestPresentation(event: String) async throws {
        let f = try Fixture(); await f.load(); let original = try f.open()
        let containerID = try #require(f.host.viewIdentity)
        let box = HostObservationProbeBox()
        withObservationTracking {
            _ = f.host.feasibilityPresentation
        } onChange: {
            MainActor.assumeIsolated {
                guard !box.fired else { return }; box.fired = true
                #expect(f.host.openFeasibility(context: f.host.captureAction()))
                box.replacement = f.host.feasibilityPresentation?.id
            }
        }
        switch event {
        case "dismiss": f.host.dismissFeasibility(id: original.id)
        case "leave": f.host.leaveContainer(id: containerID)
        default: #expect(f.host.openFeasibility(context: f.host.captureAction()))
        }
        #expect(box.fired && box.replacement != nil)
        #expect(f.host.feasibilityPresentation?.id == box.replacement)
        #expect(f.host.feasibilityPresentation?.id != original.id)
        f.host.dismissFeasibility(id: original.id)
        #expect(f.host.feasibilityPresentation?.id == box.replacement)
    }
    @Test func observationStillNotifiesForRealPublishAndClear() async throws {
        let f = try Fixture(); await f.load()
        let published = HostObservationProbeBox()
        withObservationTracking {
            _ = f.host.feasibilityPresentation
        } onChange: {
            MainActor.assumeIsolated { published.fired = true }
        }
        let entry = try f.open()
        #expect(published.fired)
        #expect(f.host.feasibilityPresentation === entry)
        let cleared = HostObservationProbeBox()
        withObservationTracking {
            _ = f.host.feasibilityPresentation
        } onChange: {
            MainActor.assumeIsolated { cleared.fired = true }
        }
        f.host.dismissFeasibility(id: entry.id)
        #expect(cleared.fired)
        #expect(f.host.feasibilityPresentation == nil)
        #expect(f.host.presentation?.snapshot == f.snapshot)
    }
}
