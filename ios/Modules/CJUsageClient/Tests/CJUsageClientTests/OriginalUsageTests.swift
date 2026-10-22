import Foundation
import Testing
import CJAPI
import CJMessageClient
@testable import CJMessageHTTP
import CJSession
import HTTPTypes
import OpenAPIRuntime
@testable import CJUsageClient

@MainActor private final class OriginalStorage: SecureMessageStorage {
    var snapshot: Snapshot?
    var saves = 0
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot; saves += 1 }
}
@MainActor private final class OriginalCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic" }
}
@MainActor private final class OriginalHarness {
    let storage = OriginalStorage()
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let session = SessionLifecycle(persistence: MemorySession(), restorePolicy: .userInitiatedOnly)
    let endpoint = try! MessageEndpoint(url: URL(string: "https://synthetic.invalid")!, maximumRequestBytes: 4096, maximumResponseBytes: 16384)
    let message = "synthetic-message/+%e\u{301}"
    let conversation = "synthetic-chat-e\u{301}"
    let messageGeneration = "synthetic-generation-e\u{301}"
    let run = "synthetic-run-e\u{301}"
    let trace = "ee47419a-77ec-435f-8495-e867d7a2bc63"
    var selected: OriginalUsageBinding?
    var currentHook: (() -> Void)?
    var credentialHook: (() async throws -> String?)?
    var sendHook: (() async throws -> Void)?
    var delayedBody: HTTPBody?
    var paths: [String] = []
    var methods: [HTTPRequest.Method] = []
    var associationStatus = 200
    var association: [String: Any] = [:]
    var status: [String: Any] = [:]
    lazy var model: OriginalUsageViewModel = makeModel()
    func makeModel() -> OriginalUsageViewModel {
        OriginalUsageViewModel(session: session, recovery: recovery, scope: scope, endpoint: endpoint,
            credentials: { [self] _ in if let credentialHook { return try await credentialHook() }; return "synthetic" },
            currentBinding: { [self] in currentHook?(); return selected }, interceptedTransport: try! NoRedirectTransport(interceptedTransport: Intercept { [self] request, body, _, operation in
                #expect(body == nil && request.method == .get && request.headerFields[.cacheControl] == "no-store")
                paths.append(request.path ?? ""); methods.append(request.method)
                try await sendHook?()
                let isAssociation = operation == "getOriginalUsageAssociation"
                #expect(isAssociation || operation == "getUsageAttemptStatus")
                let code = isAssociation ? associationStatus : 200
                var response = HTTPResponse(status: .init(code: code))
                response.headerFields[.contentType] = "application/json"; response.headerFields[.cacheControl] = "no-store"
                response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
                if let delayedBody { return (response, delayedBody) }
                let payload: [String: Any]
                if code == 503 { payload = ["request_id":trace,"error":["code":"ORIGINAL_USAGE_UNAVAILABLE","category":"dependency","outcome":"unknown","recovery":"retry_safe_read","message_en":"Unavailable","message_zh":"不可用"]] }
                else { payload = ["request_id": trace, isAssociation ? "association" : "attempt": isAssociation ? association : status] }
                return (response, HTTPBody(try JSONSerialization.data(withJSONObject: payload)))
            }, previewEndpoint: nil, validatePreview: nil))
    }
    init() throws {
        scope = try StorageScope(environment: "synthetic-association-" + UUID().uuidString, account: "synthetic-account")
        recovery = MessageRecovery(storage: storage); lease = try recovery.activate(scope)
        association = ["message_id":message,"conversation_id":conversation,"generation":messageGeneration,"run_id":run,"message_sequence":7,"attempt_id":"original-attempt/+%e\u{301}","operation_id":"original-operation-e\u{301}"]
        status = ["attempt_id":association["attempt_id"]!,"operation_id":association["operation_id"]!,"run_id":run,"status":"unknown","unit":"opaque","reserved_units":"999999999999999999999999999999","confirmed_units":NSNull(),"confirmed_output":NSNull(),"receipt_id":NSNull(),"cancelled":false,"exceeded":false,"message_en":"Unknown","message_zh":"未知"]
    }
    /// The synthetic accepted input is produced via actual canonical generated
    /// MessageHTTPClient.query and MessageRecovery, never by constructing accepted refs.
    func accept() async throws {
        let raw = try JSONSerialization.data(withJSONObject: ["message_id":message,"conversation_id":conversation,"text":"synthetic"])
        try recovery.stage(messageID: message, originalUTF8: raw, lease: lease)
        let submission = try recovery.beginSubmission(messageID: message, lease: lease)
        try recovery.observeUnknown(submission.operation)
        let record = try #require(try recovery.action(messageID: message, lease: lease))
        let receipt: [String:Any] = ["message_id":message,"conversation_id":conversation,"generation":messageGeneration,"run_id":run,"sequence":7,"input_sha256":record.inputSHA256]
        let http = MessageHTTPClient(recovery: recovery, scope: scope, endpoint: endpoint, credentials: OriginalCredentials(),
            interceptedTestTransport: Intercept { [self] request, body, _, operation in
                #expect(operation == "queryMessageReceipt" && request.method == .get && body == nil)
                var response = HTTPResponse(status: .ok); response.headerFields[.contentType] = "application/json"
                response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
                return (response, HTTPBody(try JSONSerialization.data(withJSONObject: ["request_id":trace,"receipt":receipt])))
            })
        if case .accepted = try await http.query(messageID: message, lease: lease) {} else { Issue.record("canonical query not accepted") }
        let accepted = try #require(try recovery.action(messageID: message, lease: lease))
        let captured = try model.captureAcceptedMessage(accepted, lease: lease)
        selected = OriginalUsageBinding(acceptedMessage: captured, sessionOperation: try session.beginTrustedSDKSave(),
            actorIdentity: Data("actor-A".utf8), selectionGeneration: UUID(), revision: 7)
    }
    func resolve() async throws -> ResolvedUsageSource? {
        let prepared = try model.prepareAssociation(try #require(selected)); await model.read(prepared)
        if case .sourceReady(let source) = model.state { return source }; return nil
    }
    func switchSelection(actor: String = "actor-A") throws {
        let old = try #require(selected)
        selected = OriginalUsageBinding(acceptedMessage: old.acceptedMessage, sessionOperation: old.sessionOperation,
            actorIdentity: Data(actor.utf8), selectionGeneration: UUID(), revision: old.revision)
    }
}

@MainActor struct OriginalUsageTests {
    @Test func acceptedCanonicalReceiptThenAssociationThenExplicitOriginalStatus() async throws {
        let h = try OriginalHarness(); try await h.accept(); let saves = h.storage.saves
        let source = try #require(try await h.resolve())
        #expect(h.paths.count == 1 && h.storage.saves == saves)
        let first = try #require(URLComponents(string: "https://synthetic.invalid" + h.paths[0])?.queryItems)
        #expect(first.count == 1 && first[0].name == "message_id" && Data((first[0].value ?? "").utf8) == Data(h.message.utf8))
        #expect(Data(source.attemptID.utf8) == Data((h.association["attempt_id"] as! String).utf8))
        let prepared = try h.model.prepareStatus(source); await h.model.read(prepared); await h.model.read(prepared)
        #expect(h.paths.count == 2 && h.storage.saves == saves && h.methods.allSatisfy({ $0 == .get }))
        let last = try #require(URLComponents(string: "https://synthetic.invalid" + h.paths[1])?.queryItems)
        #expect(last.count == 1 && last[0].name == "attempt_id" && Data((last[0].value ?? "").utf8) == Data(source.attemptID.utf8))
        guard case .loaded(let result) = h.model.state else { Issue.record("missing explicit status"); return }
        #expect(result.confirmedUnits == nil && result.reservedUnits == "999999999999999999999999999999")
    }
    @Test(arguments: ["message_id","conversation_id","generation","run_id","message_sequence","attempt_id","operation_id","extra","missing","normalized-message","normalized-generation","fraction-sequence","bool-sequence","503"])
    func badAssociationNeverBecomesUsageSource(_ field: String) async throws {
        let h = try OriginalHarness(); try await h.accept()
        switch field {
        case "message_sequence": h.association[field] = 8
        case "attempt_id", "operation_id": h.association[field] = ""
        case "extra": h.association["scope"] = "caller-scope"
        case "missing": h.association.removeValue(forKey: "attempt_id")
        case "normalized-message": h.association["message_id"] = h.message.precomposedStringWithCanonicalMapping
        case "normalized-generation": h.association["generation"] = h.messageGeneration.precomposedStringWithCanonicalMapping
        case "fraction-sequence": h.association["message_sequence"] = 7.5
        case "bool-sequence": h.association["message_sequence"] = true
        case "503": h.associationStatus = 503
        default: h.association[field] = "other"
        }
        #expect(try await h.resolve() == nil && h.paths.count == 1)
        if field == "503" { #expect(h.model.state == .failed(.unavailable)) }
        else { guard case .failed = h.model.state else { Issue.record("bad association accepted"); return } }
    }
    @Test func stagedForeignOrReplacedCanonicalInputCannotBeCaptured() async throws {
        let h = try OriginalHarness()
        try h.recovery.stage(messageID: h.message, originalUTF8: Data("{}".utf8), lease: h.lease)
        let staged = try #require(try h.recovery.action(messageID: h.message, lease: h.lease))
        #expect(throws: UsageFailure.unavailable) { try h.model.captureAcceptedMessage(staged, lease: h.lease) }
        #expect(h.paths.isEmpty)
        let accepted = try OriginalHarness(); try await accepted.accept()
        let oldRecord = try #require(try accepted.recovery.action(messageID: accepted.message, lease: accepted.lease))
        accepted.recovery.invalidate()
        #expect(throws: (any Error).self) { try accepted.model.captureAcceptedMessage(oldRecord, lease: accepted.lease) }
    }
    @Test(arguments: [false, true])
    func actorABAAndRecoveryInvalidationAcrossBothReads(_ statusStage: Bool) async throws {
        for mutation in ["actor", "ABA", "recovery", "session"] {
            let h = try OriginalHarness(); try await h.accept()
            var source: ResolvedUsageSource?
        if statusStage { let result = try await h.resolve(); source = try #require(result) }
            let old = h.paths.count
            h.credentialHook = {
                switch mutation {
                case "actor": try h.switchSelection(actor: "actor-B")
                case "ABA": try h.switchSelection(); try h.switchSelection()
                case "recovery": h.recovery.invalidate()
                default: _ = try h.session.beginTrustedSDKSave()
                }
                return "synthetic"
            }
            let p = try source.map(h.model.prepareStatus) ?? h.model.prepareAssociation(try #require(h.selected))
            await h.model.read(p)
            #expect(h.model.state == .unavailable && h.paths.count == old)
        }
    }
    @Test(arguments: [false, true])
    func equalRevisionPrepareAndFinalCallbackReentryKeepNewOwner(_ statusStage: Bool) async throws {
        let h = try OriginalHarness(); try await h.accept()
        var source: ResolvedUsageSource?
        if statusStage { let result = try await h.resolve(); source = try #require(result) }
        var inner: PreparedOriginalUsageRead?
        func prepare() throws -> PreparedOriginalUsageRead { try source.map(h.model.prepareStatus) ?? h.model.prepareAssociation(try #require(h.selected)) }
        h.currentHook = { h.currentHook = nil; inner = try? prepare() }
        #expect(throws: UsageFailure.stale) { try prepare() }
        #expect(h.model.state == .loading)
        await h.model.read(try #require(inner))
        if statusStage { guard case .loaded = h.model.state else { Issue.record("new status lost"); return } }
        else { guard case .sourceReady = h.model.state else { Issue.record("new association lost"); return } }
    }
    @Test(arguments: [false, true])
    func finalPublicationCallbackCannotOverwriteNewPreparation(_ statusStage: Bool) async throws {
        let h = try OriginalHarness(); try await h.accept()
        var source: ResolvedUsageSource?
        if statusStage { let result = try await h.resolve(); source = try #require(result) }
        var received = false; var count = 0; var inner: PreparedOriginalUsageRead?
        h.sendHook = { received = true }
        h.currentHook = {
            guard received else { return }; count += 1
            if count == 5 { h.currentHook = nil; inner = try? source.map(h.model.prepareStatus) ?? h.model.prepareAssociation(try #require(h.selected)) }
        }
        let p = try source.map(h.model.prepareStatus) ?? h.model.prepareAssociation(try #require(h.selected)); await h.model.read(p)
        #expect(inner != nil && h.model.state == .loading)
        await h.model.read(try #require(inner))
        if statusStage { guard case .loaded = h.model.state else { Issue.record("final status overwrite"); return } }
        else { guard case .sourceReady = h.model.state else { Issue.record("final association overwrite"); return } }
    }
    @Test func sourceCannotMoveToAnotherModelOrSurviveInvalidation() async throws {
        let h = try OriginalHarness(); try await h.accept(); let source = try #require(try await h.resolve())
        let other = h.makeModel()
        #expect(throws: UsageFailure.stale) { try other.prepareStatus(source) }
        #expect(throws: UsageFailure.stale) { try other.prepareAssociation(try #require(h.selected)) }
        h.model.invalidate()
        #expect(throws: UsageFailure.stale) { try h.model.prepareStatus(source) }
    }
    @Test(arguments: ["attempt_id","operation_id","run_id"])
    func statusMustRemainBoundToClosedAssociation(_ field: String) async throws {
        let h = try OriginalHarness(); try await h.accept(); let source = try #require(try await h.resolve())
        h.status[field] = "other"
        let p = try h.model.prepareStatus(source); await h.model.read(p)
        #expect(h.model.state == .failed(.invalidResponse))
    }
}

private actor AssociationBodyGate {
    private(set) var started = false
    private var delivered = false
    private var continuation: CheckedContinuation<HTTPBody.ByteChunk?, Never>?
    func next() async -> HTTPBody.ByteChunk? {
        guard !delivered else { return nil }; delivered = true; started = true
        return await withCheckedContinuation { continuation = $0 }
    }
    func release(_ bytes: Data) { continuation?.resume(returning: ArraySlice(bytes)); continuation = nil }
}

@MainActor extension OriginalUsageTests {
    @Test(arguments: [false, true])
    func bodyAwaitAndLateErrorCannotReplaceNewerSourceOrStatus(_ statusStage: Bool) async throws {
        for cancel in [false, true] {
            let h = try OriginalHarness(); try await h.accept()
            var source: ResolvedUsageSource?
            if statusStage { let result = try await h.resolve(); source = try #require(result) }
            let gate = AssociationBodyGate()
            h.delayedBody = HTTPBody(AsyncThrowingStream<HTTPBody.ByteChunk, any Error>(unfolding: { await gate.next() }), length: .unknown)
            let p = try source.map(h.model.prepareStatus) ?? h.model.prepareAssociation(try #require(h.selected))
            let old = Task { await h.model.read(p) }
            while !(await gate.started) { await Task.yield() }
            h.delayedBody = nil
            try h.switchSelection(); try h.switchSelection()
            let next = try h.model.prepareAssociation(try #require(h.selected)); await h.model.read(next)
            guard case .sourceReady(let newSource) = h.model.state else { Issue.record("new source not ready"); return }
            if statusStage { let read = try h.model.prepareStatus(newSource); await h.model.read(read) }
            if cancel { old.cancel() }
            await gate.release(try JSONSerialization.data(withJSONObject: ["request_id":h.trace, statusStage ? "attempt" : "association": statusStage ? h.status : h.association]))
            await old.value
            if statusStage { guard case .loaded = h.model.state else { Issue.record("old body/error overwrote status"); return } }
            else { guard case .sourceReady(let current) = h.model.state else { Issue.record("old body/error overwrote source"); return }; #expect(current == newSource) }
        }
    }
    @Test(arguments: [false, true])
    func credentialErrorReentryCannotClearNewPreparation(_ statusStage: Bool) async throws {
        let h = try OriginalHarness(); try await h.accept()
        var source: ResolvedUsageSource?
        if statusStage { let result = try await h.resolve(); source = try #require(result) }
        var newer: PreparedOriginalUsageRead?
        h.credentialHook = {
            h.credentialHook = nil
            newer = try source.map(h.model.prepareStatus) ?? h.model.prepareAssociation(try #require(h.selected))
            await h.model.read(try #require(newer))
            throw UsageFailure.exchangeFailed
        }
        let old = try source.map(h.model.prepareStatus) ?? h.model.prepareAssociation(try #require(h.selected)); await h.model.read(old)
        if statusStage { guard case .loaded = h.model.state else { Issue.record("late credential error cleared status"); return } }
        else { guard case .sourceReady = h.model.state else { Issue.record("late credential error cleared source"); return } }
    }
}
