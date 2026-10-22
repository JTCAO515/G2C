import Foundation
import Testing
import CJAPI
import CJMessageClient
@testable import CJMessageHTTP
import CJSession
import HTTPTypes
import OpenAPIRuntime
@testable import CJUsageClient

@MainActor private final class IndependentLongRefStorage: SecureMessageStorage {
    var snapshot: Snapshot?
    var saves = 0
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot; saves += 1 }
}
@MainActor private final class IndependentLongRefCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic" }
}
@MainActor private final class IndependentLongRefHarness {
    let storage = IndependentLongRefStorage()
    let recovery: MessageRecovery
    let scope: StorageScope
    let lease: Lease
    let session = SessionLifecycle(persistence: MemorySession(), restorePolicy: .userInitiatedOnly)
    let endpoint = try! MessageEndpoint(url: URL(string: "https://synthetic.invalid")!, maximumRequestBytes: 4096, maximumResponseBytes: 16384)
    var message = "synthetic-message/+%e\u{301}"
    var conversation = "synthetic-chat-e\u{301}"
    var messageGeneration = "synthetic-generation-e\u{301}"
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
        let raw = try JSONSerialization.data(withJSONObject: ["version":"MESSAGE-draft.1","message_id":message,"conversation_id":conversation,"text":"synthetic","trip_id":NSNull(),"creation_intent":"none"])
        try recovery.stage(messageID: message, originalUTF8: raw, lease: lease)
        let submission = try recovery.beginSubmission(messageID: message, lease: lease)
        try recovery.observeUnknown(submission.operation)
        let record = try #require(try recovery.action(messageID: message, lease: lease))
        let receipt: [String:Any] = ["message_id":message,"conversation_id":conversation,"generation":messageGeneration,"run_id":run,"sequence":7,"input_sha256":record.inputSHA256]
        let http = MessageHTTPClient(recovery: recovery, scope: scope, endpoint: endpoint, credentials: IndependentLongRefCredentials(),
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


@MainActor struct IndependentOriginalReferenceBoundsTests {
    @Test(arguments: ["message_id", "conversation_id", "generation"], [200, 201])
    func validCanonicalAcceptedMessageReferencesOver200RemainUsable(_ field: String, _ length: Int) async throws {
        let h = try IndependentLongRefHarness(), long = String(repeating: "x", count: length)
        switch field {
        case "message_id": h.message = long
        case "conversation_id": h.conversation = long
        default: h.messageGeneration = long
        }
        h.association[field] = long
        do { try await h.accept() }
        catch {
            let actual = try #require(try h.recovery.action(messageID: h.message, lease: h.lease))
            #expect(actual.phase == .accepted)
            Issue.record("Canonical MESSAGE query accepted original bytes within configured caps, but usage capture rejects unbounded contract field \(field): \(error)")
            return
        }
        let source = try #require(try await h.resolve())
        #expect(source.messageID == h.message && h.paths.count == 1)
    }
    @Test(arguments: ["message_id", "conversation_id", "generation"], [200, 201])
    func associationWireMustUseItsOwnFieldBounds(_ field: String, _ length: Int) throws {
        var row: [String: Any] = ["message_id":"m","conversation_id":"c","generation":"g","run_id":"run","message_sequence":1,"attempt_id":"attempt","operation_id":"operation"]
        row[field] = String(repeating:"x",count:length)
        try validateAssociationWire(["request_id":"00000000-0000-4000-8000-000000000818","association":row])
    }
}
