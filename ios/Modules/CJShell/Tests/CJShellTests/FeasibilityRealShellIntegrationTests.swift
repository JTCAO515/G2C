import Foundation
import CryptoKit
import Observation
import Testing
import CJSession
import CJMessageHTTP
import CJFeasibilityClient
import OpenAPIRuntime
import HTTPTypes
@testable import CJNeedsClient
@testable import CJShell

// Only canonical NEEDS reads use a local intercepted fixture. No FEAS endpoint,
// credential, transport, issuer or internal FEAS test constructor is supplied.
private actor RealShellNeedsWire: ClientTransport {
    var replies: [Data] = []
    var calls = 0
    var holdNext = false
    var held = false
    var continuation: CheckedContinuation<Void, Never>?
    func add(_ bytes: Data) { replies.append(bytes) }
    func hold() { holdNext = true }
    func release() { continuation?.resume(); continuation = nil }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(operationID == "getNeeds" && request.method == .get && body == nil)
        calls += 1
        let reply = try #require(replies.isEmpty ? nil : replies.removeFirst())
        if holdNext { holdNext = false; held = true; await withCheckedContinuation { continuation = $0 } }
        var response = HTTPResponse(status: .ok)
        response.headerFields[HTTPField.Name("X-Request-ID")!] = "00000000-0000-4000-8000-000000000001"
        response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(reply))
    }
}
@MainActor private struct RealShellSessionStore: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ value: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
@MainActor private final class RealShellFeasFixture {
    let shell: ShellState
    let host: NeedsContainerHost
    let session = SessionLifecycle(persistence: RealShellSessionStore(), restorePolicy: .userInitiatedOnly)
    let operation: SessionOperation
    let wire = RealShellNeedsWire()
    var needs = NeedsBinding(environment: UUID(), account: UUID(), generation: UUID(), selection: UUID())
    var current: NeedsBinding?
    var callback: (() -> Void)?
    var selectedID = "needs-A"
    let originalBytes = Data("{ \"pace\": {\"state\":\"known\",\"value\":\"e\u{301}\"}, \"budget_paid\": {\"state\":\"known\",\"value\":\"12.3400\"} }".utf8)
    init() throws {
        shell = ShellState(preferences: try #require(UserDefaults(suiteName: "cj006.feas.real.\(UUID().uuidString)")))
        host = NeedsContainerHost(shell: shell)
        operation = try session.beginTrustedSDKSave(); current = needs
        try bind()
    }
    func observed() -> NeedsBinding? {
        let value = current, run = callback; callback = nil; run?(); return value
    }
    func bind() throws {
        let client = NeedsClient(endpoint: try NeedsEndpoint(url: #require(URL(string: "https://synthetic.invalid")), maximumRequestBytes: 131072, maximumResponseBytes: 1048576),
            credentials: { _ in "SYNTHETIC-NEEDS-ONLY" }, currentBinding: { [self] in observed() },
            pendingStore: nil, interceptedTransport: wire)
        let binding = NeedsContainerBinding(client: client, needs: needs, selectedNeedsID: selectedID,
            shellGeneration: shell.generation, session: session, sessionOperation: operation, synthetic: true,
            currentBinding: { [self] in observed() })
        #expect(host.bind(binding))
    }
    func enqueue() async throws {
        let snapshot = NeedsSchema.NeedsSnapshot(needs_id: selectedID, version: 2, source_kind: .user_provided,
            content_utf8_base64: originalBytes.base64EncodedString(),
            fields: try JSONDecoder().decode(NeedsSchema.NeedsFields.self, from: originalBytes))
        let body = try JSONEncoder().encode(snapshot)
        await wire.add(Data("{\"request_id\":\"00000000-0000-4000-8000-000000000001\",\"needs\":\(String(decoding: body, as: UTF8.self))}".utf8))
    }
    func load() async throws {
        try await enqueue(); await host.perform(host.prepareDetail(context: host.captureAction()))
        #expect(host.presentation?.state == .loaded)
    }
    func open() throws -> FeasibilityHostPresentation {
        #expect(host.openFeasibility(context: host.captureAction()))
        return try #require(host.feasibilityPresentation)
    }
    func select(_ id: String) async throws {
        host.invalidate(); selectedID = id
        needs = .init(environment: needs.environment, account: needs.account, generation: needs.generation, selection: UUID())
        current = needs; try bind(); try await load()
    }
}
@MainActor private final class RealShellObservationBox {
    var fired = false
    var replacement: FeasibilityHostPresentation?
}

@Suite @MainActor struct FeasibilityRealShellIntegrationTests {
    @Test func actualShellAcceptsCanonicalSourceButPublicFeasibilityStaysClosed() async throws {
        let f = try RealShellFeasFixture()
        #expect(f.shell.needsContainerHost === f.host)
        #expect(!f.host.openFeasibility(context: f.host.captureAction()))
        try await f.load(); let entry = try f.open()
        #expect(entry.binding.acceptedContentSHA256 == SHA256.hash(data: f.originalBytes).map { String(format: "%02x", $0) }.joined())
        #expect(entry.binding.needsID == "needs-A" && entry.binding.acceptedRevision == 2)
        #expect(entry.binding.selection == f.needs.selection)
        #expect(throws: FeasibilityFailure.unavailable) { _ = try entry.model.prepare(entry.binding) }
        if case .unavailable = entry.model.state {} else { Issue.record("Public FEAS factory must stay closed") }
        #expect(!f.host.canSave)
        #expect(await f.wire.calls == 1)
    }
    @Test func actualRootIdentityInvalidationClearsPrivateStateAndRejectsOldGeneration() async throws {
        let f = try RealShellFeasFixture(); try await f.load(); let entry = try f.open()
        let generation = f.shell.generation
        f.shell.draft = "SYNTHETIC unsent"; f.shell.memoryPath = [.help]; f.shell.tripPath = [.detail]
        #expect(f.shell.apply(ShellPresentation(assistantBody: "SYNTHETIC private"), for: generation))
        f.shell.invalidateIdentity()
        #expect(f.shell.generation != generation && f.shell.messageBindingBlocked)
        #expect(f.shell.draft.isEmpty && f.shell.memoryPath.isEmpty && f.shell.tripPath.isEmpty)
        #expect(f.shell.assistantBody == nil && !f.shell.apply(ShellPresentation(assistantBody: "late"), for: generation))
        #expect(f.host.presentation == nil && f.host.feasibilityPresentation == nil && f.host.captureAction() == nil)
        #expect(throws: FeasibilityFailure.stale) { _ = try entry.model.prepare(entry.binding) }
    }
    @Test(arguments: ["account", "environment", "selection", "operation", "clear"])
    func currentIdentityAndSessionChangesWithholdAcceptedSource(event: String) async throws {
        let f = try RealShellFeasFixture(); try await f.load(); let entry = try f.open()
        let old = f.needs
        switch event {
        case "operation": _ = try f.session.beginTrustedSDKSave()
        case "clear": try f.session.clear()
        default:
            f.current = .init(environment: event == "environment" ? UUID() : old.environment,
                account: event == "account" ? UUID() : old.account, generation: old.generation,
                selection: event == "selection" ? UUID() : old.selection)
        }
        #expect(f.host.captureAction() == nil && f.host.feasibilityPresentation == nil)
        #expect(throws: FeasibilityFailure.stale) { _ = try entry.model.prepare(entry.binding) }
    }
    @Test func actualLanguageAndNavigationPreserveSourceWithoutSecondRead() async throws {
        let f = try RealShellFeasFixture(); try await f.load(); let entry = try f.open()
        f.shell.draft = "SYNTHETIC 你好"; f.shell.memoryPath = [.help]
        for language in [ShellLanguage.chinese, .english] {
            f.shell.selectLanguage(language)
            for tab in ShellTab.allCases { f.shell.selectedTab = tab }
            #expect(f.shell.memoryPath == [.help] && f.shell.draft == "SYNTHETIC 你好")
            #expect(f.host.feasibilityPresentation === entry)
        }
        #expect(await f.wire.calls == 1)
    }
    @Test func selectionABAAndLateExitCannotClearCurrentAcceptedSelection() async throws {
        let f = try RealShellFeasFixture(); try await f.load(); let a = try f.open()
        let oldContainer = try #require(f.host.viewIdentity)
        try await f.select("needs-B"); let b = try f.open()
        f.host.leaveContainer(id: oldContainer); f.host.dismissFeasibility(id: a.id)
        #expect(f.host.feasibilityPresentation === b && b.binding.needsID == "needs-B")
        try await f.select("needs-A"); let newA = try f.open()
        f.host.dismissFeasibility(id: a.id); f.host.dismissFeasibility(id: b.id)
        #expect(f.host.feasibilityPresentation === newA && newA.binding.selection != a.binding.selection)
        #expect(throws: FeasibilityFailure.stale) { _ = try a.model.prepare(a.binding) }
    }
    @Test(arguments: ["dismiss", "leave", "background"])
    func actualHostExitRetiresEvaluationWithoutCreatingAuthority(event: String) async throws {
        let f = try RealShellFeasFixture(); try await f.load(); let entry = try f.open()
        let id = try #require(f.host.viewIdentity)
        switch event {
        case "dismiss": f.host.dismissFeasibility(id: entry.id)
        case "leave": f.host.leaveContainer(id: id)
        default: f.host.suspendForBackground()
        }
        #expect(f.host.feasibilityPresentation == nil)
        if event != "background" { #expect(f.host.presentation?.state == .loaded) }
        #expect(throws: FeasibilityFailure.stale) { _ = try entry.model.prepare(entry.binding) }
        #expect(await f.wire.calls == 1)
    }
    @Test(arguments: ["replace", "dismiss", "leave"])
    func realObservationReentryPreservesNewestPresentation(event: String) async throws {
        let f = try RealShellFeasFixture(); try await f.load(); let original = try f.open()
        let id = try #require(f.host.viewIdentity), box = RealShellObservationBox()
        withObservationTracking { _ = f.host.feasibilityPresentation } onChange: {
            MainActor.assumeIsolated {
                guard !box.fired else { return }; box.fired = true
                box.replacement = try? f.open()
            }
        }
        switch event {
        case "dismiss": f.host.dismissFeasibility(id: original.id)
        case "leave": f.host.leaveContainer(id: id)
        default: #expect(f.host.openFeasibility(context: f.host.captureAction()))
        }
        let replacement = try #require(box.replacement)
        #expect(box.fired && replacement.id != original.id && f.host.feasibilityPresentation === replacement)
        f.host.dismissFeasibility(id: original.id)
        #expect(f.host.feasibilityPresentation === replacement)
    }
    @Test func realObservationReentryCannotSurviveCompletedRootIdentityFence() async throws {
        let f = try RealShellFeasFixture(); try await f.load(); let entry = try f.open()
        let box = RealShellObservationBox()
        withObservationTracking { _ = f.host.feasibilityPresentation } onChange: {
            MainActor.assumeIsolated {
                // Actual ShellState is observable too: willSet may fire BEFORE
                // the root fence assignment commits. Bound synchronous reentry
                // and require every retained token to retire after completion.
                guard !box.fired else { return }; box.fired = true
                box.replacement = try? f.open()
            }
        }
        f.shell.invalidateIdentity()
        #expect(box.fired && f.host.feasibilityPresentation == nil && f.shell.messageBindingBlocked)
        #expect(throws: FeasibilityFailure.stale) { _ = try entry.model.prepare(entry.binding) }
        if let replacement = box.replacement {
            #expect(throws: FeasibilityFailure.stale) { _ = try replacement.model.prepare(replacement.binding) }
        }
    }
    @Test func sourceCallbackInvalidatingActualRootCannotPublishOuterOpen() async throws {
        let f = try RealShellFeasFixture(); try await f.load()
        f.callback = { f.shell.invalidateIdentity() }
        #expect(!f.host.openFeasibility(context: f.host.captureAction()))
        #expect(f.host.feasibilityPresentation == nil && f.shell.messageBindingBlocked)
    }
    @Test func lateAcceptedNeedsReadAfterActualRootExitCannotRestoreSource() async throws {
        let f = try RealShellFeasFixture(); try await f.enqueue(); await f.wire.hold()
        let work = try #require(f.host.prepareDetail(context: f.host.captureAction()))
        let task = Task { await f.host.perform(work) }
        var held = false
        for _ in 0..<10000 { if await f.wire.held { held = true; break }; await Task.yield() }
        #expect(held); f.shell.invalidateIdentity()
        await f.wire.release(); await task.value
        #expect(f.host.presentation == nil && f.host.feasibilityPresentation == nil)
        #expect(f.shell.messageBindingBlocked && f.host.captureAction() == nil)
    }
}
