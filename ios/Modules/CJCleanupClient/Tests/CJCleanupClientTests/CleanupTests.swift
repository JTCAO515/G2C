import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJCleanupClient

@MainActor private final class Store: SessionPersistence {
    func load() throws -> SessionMaterial? { nil }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws {}
}
private struct FixtureTransport: ClientTransport {
    let handler: @MainActor @Sendable (HTTPRequest) async throws -> (HTTPResponse, HTTPBody?)
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(body == nil)
        #expect(operationID == Operations.getCurrentAccountCleanupProgress.id)
        return try await handler(request)
    }
}
@MainActor private final class Harness {
    let session = SessionLifecycle(persistence: Store(), restorePolicy: .userInitiatedOnly)
    let environment = UUID()
    var binding: CleanupBinding?
    var model: CleanupViewModel!
    var calls = 0
    var currentCallback: (() -> Void)?
    init(response: @escaping @MainActor (Harness, HTTPRequest) async throws -> (HTTPResponse, HTTPBody?),
         credentials: (@MainActor (Harness) async throws -> String?)? = nil,
         maximumResponseBytes: Int = 65536, maximumSteps: Int = 128) throws {
        binding = CleanupBinding(environment: environment, actorIdentity: "account-A",
            sessionOperation: try session.beginTrustedSDKSave(), trustedOriginalOperationID: "original-A")
        let endpoint = try MessageEndpoint(url: URL(string: "https://example.invalid")!,
            maximumRequestBytes: 4096, maximumResponseBytes: maximumResponseBytes)
        model = CleanupViewModel(session: session, environment: environment, maximumSteps: maximumSteps,
            endpoint: endpoint, credentials: { [unowned self] _ in
                if let credentials { return try await credentials(self) }; return "fixture-only"
            }, currentBinding: { [unowned self] in
                let old = binding; currentCallback?(); return old
            }, interceptedTransport: FixtureTransport(handler: { [unowned self] request in
                calls += 1; return try await response(self, request)
            }))
    }
    func read() async throws { let prepared = try model.prepare(binding!); await model.read(prepared) }
    func switchAccount(environment: UUID? = nil) throws {
        binding = CleanupBinding(environment: environment ?? self.environment, actorIdentity: "account-B",
            sessionOperation: try session.beginTrustedSDKSave(), trustedOriginalOperationID: "original-B")
    }
}
private let trace = "11111111-1111-4111-8111-111111111111"
private func payload(operation: String = "original-A", status: String = "blocked", state: String = "pending",
                     reason: String = "hook_unavailable", revision: String = "0", reasons: String = "[\"hook_unavailable\"]") -> String {
    """
    {"request_id":"\(trace)","progress":{"operation_id":"\(operation)","revision":\(revision),"status":"\(status)","steps":[{"target":"backup_retention","state":"\(state)","reason":"\(reason)"}],"reasons":\(reasons)}}
    """
}
private func response(_ text: String, status: Int = 200, cache: String = "no-store") -> (HTTPResponse, HTTPBody?) {
    var headers = HTTPFields()
    headers[.contentType] = "application/json"; headers[.cacheControl] = cache
    headers[HTTPField.Name("X-Request-ID")!] = trace
    return (HTTPResponse(status: .init(code: status), headerFields: headers), HTTPBody(Data(text.utf8)))
}
@MainActor @Test func explicitReadUsesOriginalGETOnceAndPreservesBlocked() async throws {
    let h = try Harness { _, request in
        #expect(request.method == .get)
        #expect(request.path == "/v1/account-cleanup-progress?operation_id=original-A")
        #expect(request.headerFields[.authorization] == "Bearer fixture-only")
        return response(payload())
    }
    #expect(h.model.state == .unavailable); #expect(h.calls == 0)
    let prepared = try h.model.prepare(h.binding!)
    await h.model.read(prepared); await h.model.read(prepared)
    #expect(h.calls == 1)
    guard case .loaded(let progress) = h.model.state else { Issue.record("missing blocked projection"); return }
    #expect(progress.status == .blocked); #expect(progress.revision == 0)
    #expect(progress.steps.first?.target == "backup_retention")
    #expect(progress.steps.first?.state == .pending)
}
@MainActor @Test func unknownInProgressFailedAndLimitedCompleteRemainDistinct() async throws {
    for (status, state, reason, reasons) in [
        ("unknown", "unknown", "original_result_unknown", "[\"original_result_unknown\"]"),
        ("in_progress", "in_progress", "original_call_in_progress", "[]"),
        ("failed", "failed", "original_result_failed", "[\"original_result_failed\"]"),
        ("complete", "confirmed", "original_result_confirmed", "[]")
    ] {
        let h = try Harness { _, _ in response(payload(status: status, state: state, reason: reason, reasons: reasons)) }
        try await h.read()
        guard case .loaded(let p) = h.model.state else { Issue.record("lost \(status)"); continue }
        #expect(p.status.rawValue == status); #expect(p.steps[0].state.rawValue == state)
    }
}
@MainActor @Test func malformedAndUntrustedWireNeverBecomesComplete() async throws {
    let valid = payload()
    let cases = [payload(operation: "original-B"), payload(status: "future_success"),
        payload(status: "complete"), payload(revision: "-1"), payload(revision: "true"), payload(revision: "0.5"),
        valid.replacingOccurrences(of: "\"revision\":0", with: "\"revision\":0,\"revision\":1"),
        valid.replacingOccurrences(of: "\"revision\":0", with: "\"revision\":0,\"receipt\":\"private\""),
        valid.replacingOccurrences(of: "\"progress\":{", with: "\"progress\":null,\"other\":{"),
        valid.replacingOccurrences(of: "backup_retention", with: "private text"),
        payload(reasons: "[\"hook_unavailable\",\"hook_unavailable\"]"),
        "{\"request_id\":\"\(trace)\"}"]
    for text in cases {
        let h = try Harness { _, _ in response(text) }; try await h.read()
        guard case .failed = h.model.state else { Issue.record("accepted bad wire: \(text)"); continue }
    }
}
@MainActor @Test func unavailableNotFoundDeniedAndRedirectAreNotSuccess() async throws {
    for status in [401,403,404,503,302] {
        let h = try Harness { _, _ in response("{\"request_id\":\"\(trace)\",\"error\":{\"code\":\"unavailable\",\"category\":\"access\",\"message_en\":\"unavailable\",\"message_zh\":\"暂不可用\",\"outcome\":\"unknown\",\"recovery\":\"do_not_retry\"}}", status: status) }
        try await h.read()
        if status == 503 { #expect(h.model.state == .failed(.unavailable)) }
        else if status != 302 { #expect(h.model.state == .failed(.rejected(status))) }
        else { #expect(h.model.state == .failed(.invalidResponse)) }
    }
}
@MainActor @Test func responseBudgetsAndCacheAreEnforced() async throws {
    for limit in [1,128] {
        let h = try Harness(response: { _, _ in response(payload()) }, maximumResponseBytes: limit)
        try await h.read()
        guard case .failed = h.model.state else { Issue.record("oversize accepted"); continue }
    }
    let h = try Harness { _, _ in response(payload(), cache: "public") }; try await h.read()
    guard case .failed = h.model.state else { Issue.record("cache accepted"); return }
}
@MainActor @Test func missingSourceConfigurationAndInvalidOperationSendNothing() throws {
    let h = try Harness { _, _ in response(payload()) }
    let model = CleanupViewModel(session: h.session, environment: h.environment, maximumSteps: 128, currentBinding: { h.binding })
    #expect(throws: CleanupFailure.unavailable) { try model.prepare(h.binding!) }
    for id in ["", "invented id", String(repeating: "a", count: 161)] {
        h.binding = CleanupBinding(environment: h.environment, actorIdentity: "account-A",
            sessionOperation: h.binding!.sessionOperation, trustedOriginalOperationID: id)
        #expect(throws: CleanupFailure.unavailable) { try h.model.prepare(h.binding!) }
    }
    #expect(h.calls == 0)
}
@MainActor @Test func credentialsAwaitSwitchAndLogoutFenceBeforeNetwork() async throws {
    for logout in [true, false] {
        let h = try Harness(response: { _, _ in response(payload()) }, credentials: { h in
            if logout { try h.session.clear() } else { try h.switchAccount() }
            return "fixture-only"
        })
        try await h.read(); #expect(h.calls == 0); #expect(h.model.state == .unavailable)
    }
}
@MainActor @Test func lateResponseAndLateErrorCannotPublishAfterSwitch() async throws {
    for fail in [false,true] {
        let h = try Harness { h, _ in
            try h.switchAccount()
            if fail { throw CleanupFailure.exchangeUnknown }
            return response(payload())
        }
        try await h.read(); #expect(h.model.state == .unavailable)
    }
}
@MainActor @Test func cancelAndSameIdentityNewSessionDiscardLateResults() async throws {
    let h = try Harness { h, _ in h.model.invalidate(); return response(payload()) }
    try await h.read(); #expect(h.model.state == .unavailable)
    let same = try Harness { h, _ in
        h.binding = CleanupBinding(environment: h.environment, actorIdentity: "account-A",
            sessionOperation: try h.session.beginTrustedSDKSave(), trustedOriginalOperationID: "original-A")
        return response(payload())
    }
    try await same.read(); #expect(same.model.state == .unavailable)
}
@MainActor @Test func currentCallbackReentrancyFencesOldSuccessAndStateGetterClears() async throws {
    let h = try Harness { _, _ in response(payload()) }; try await h.read()
    h.currentCallback = { h.model.invalidate() }
    #expect(h.model.state == .unavailable)
    h.currentCallback = nil
    #expect(h.model.state == .unavailable)
}
@MainActor @Test func environmentAndPreparedOwnerAreBound() async throws {
    let a = try Harness { _, _ in response(payload()) }
    let b = try Harness { _, _ in response(payload()) }
    let p = try a.model.prepare(a.binding!)
    await b.model.read(p); #expect(b.calls == 0)
    try a.switchAccount(environment: UUID())
    #expect(throws: CleanupFailure.stale) { try a.model.prepare(a.binding!) }
    #expect(a.calls == 0)
}
@Test func bilingualLabelsDoNotCallUnknownComplete() {
    for language in [CleanupLanguage.english, .chinese] {
        #expect(language.label("unknown") != language.label("complete"))
        #expect(!language.failure(.unavailable).isEmpty)
        for reason in Components.Schemas.CleanupProgressStep.reasonPayload.allCases {
            #expect(!language.label(reason.rawValue).isEmpty)
        }
    }
}

@MainActor @Test func oldResultCannotClearNewLoadedGeneration() async throws {
    for fail in [false,true] {
        let h = try Harness { h, _ in
            if h.calls == 1 {
                try h.switchAccount()
                let next = try h.model.prepare(h.binding!)
                await h.model.read(next)
                if fail { throw CleanupFailure.exchangeUnknown }
                return response(payload())
            }
            return response(payload(operation: "original-B", status: "unknown", state: "unknown",
                reason: "original_result_unknown", reasons: "[\"original_result_unknown\"]"))
        }
        try await h.read()
        guard case .loaded(let p) = h.model.state else { Issue.record("new result erased"); continue }
        #expect(p.operation_id == "original-B"); #expect(p.status == .unknown); #expect(h.calls == 2)
    }
}
@MainActor @Test func actualTaskCancellationDiscardsNoncooperativeTransport() async throws {
    var waiting: CheckedContinuation<Void, Never>?
    let h = try Harness { _, _ in
        await withCheckedContinuation { waiting = $0 }
        return response(payload())
    }
    let p = try h.model.prepare(h.binding!)
    let task = Task { await h.model.read(p) }
    while waiting == nil { await Task.yield() }
    task.cancel(); waiting?.resume(); await task.value
    #expect(h.model.state == .unavailable); #expect(h.calls == 1)
}
@MainActor @Test func stepCountBudgetAndWholeBodyTraceAreEnforced() async throws {
    for text in [
        payload().replacingOccurrences(of: "\"steps\":[{", with: "\"steps\":[],\"other\":[{"),
        payload().replacingOccurrences(of: "\"revision\":0", with: "\"revision\":0.0"),
        payload().replacingOccurrences(of: trace, with: "22222222-2222-4222-8222-222222222222")
    ] {
        let h = try Harness { _, _ in response(text) }; try await h.read()
        guard case .failed = h.model.state else { Issue.record("invalid bounds/trace accepted"); continue }
    }
    let bad = try Harness(response: { _, _ in response(payload()) }, maximumResponseBytes: 65537)
    #expect(throws: CleanupFailure.unavailable) { try bad.model.prepare(bad.binding!) }
    #expect(bad.calls == 0)
}
@MainActor @Test func finalCurrentCallbackCanSwitchAfterResponseWithoutLeaking() async throws {
    let h = try Harness { h, _ in
        h.currentCallback = { try? h.switchAccount() }
        return response(payload())
    }
    try await h.read(); #expect(h.model.state == .unavailable)
}

@MainActor @Test func loadedProjectionClearsOnLogoutWithoutAnotherRequest() async throws {
    let h = try Harness { _, _ in response(payload()) }; try await h.read()
    try h.session.clear()
    #expect(h.model.state == .unavailable); #expect(h.calls == 1)
}
@MainActor @Test func configuredStepCapRejectsRatherThanTruncating() async throws {
    let one = payload()
    let step = "{\"target\":\"offline_devices\",\"state\":\"pending\",\"reason\":\"pending_original_result\"}"
    let two = one.replacingOccurrences(of: "}],\"reasons\"", with: "}," + step + "],\"reasons\"")
    let h = try Harness(response: { _, _ in response(two) }, maximumSteps: 1)
    try await h.read()
    guard case .failed = h.model.state else { Issue.record("steps truncated or accepted"); return }
}
@MainActor @Test func nonUTF8JSONCannotBypassDuplicateKeyCheck() async throws {
    let duplicate = payload().replacingOccurrences(of: "\"revision\":0", with: "\"revision\":0,\"revision\":1")
    for encoding in [String.Encoding.utf16BigEndian, .utf16LittleEndian, .utf32BigEndian, .utf32LittleEndian] {
        let h = try Harness { _, _ in
            let (headers, _) = response(payload())
            return (headers, HTTPBody(duplicate.data(using: encoding)!))
        }
        try await h.read()
        guard case .failed = h.model.state else { Issue.record("non-UTF8 duplicate accepted: \(encoding)"); continue }
    }
}
