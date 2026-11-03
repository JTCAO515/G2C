import Foundation
import Testing
import CJSession
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJCleanupClient

private let v3Trace = "11111111-1111-4111-8111-111111111451"
private let v3State = String(repeating: "b", count: 64)
@MainActor private final class V3Store: SessionPersistence {
    var value: SessionMaterial?
    func load() throws -> SessionMaterial? { value }
    func save(_ material: SessionMaterial) throws { value = material }
    func clearAndBlock() throws { value = nil }
    func record() throws -> DeviceCleanupRecord {
        guard let value else { throw CleanupFailure.unavailable }
        return try value.withBytes { try JSONDecoder().decode(DeviceCleanupRecord.self, from: $0) }
    }
}
private func v3Encode(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes]) }
@MainActor private final class V3Server {
    var requests: [(operation: String, body: Data?, auth: String?)] = []
    var registration: [String: Any]?
    var invocation: [String: Any]?
    var actionID: String?
    var actionHash: String?
    var loseRegistration = false, loseCall = false, loseReceipt = false
    var nullRegistration = false, nullAction = false
    var identityStatus = 403
    var activeAccountOperation: String?
    var completionStatus = "complete"
    var completionPolicy: String? = "CLEANUP-CONTROL-RECORDS@1"
    var changeCompletion: ((inout [String: Any]) -> Void)?
    var after: (() -> Void)?
    func respond(_ request: HTTPRequest, body: Data?, operation: String) throws -> (HTTPResponse, HTTPBody?) {
        requests.append((operation, body, request.headerFields[.authorization]))
        let input = try body.map { try JSONSerialization.jsonObject(with: $0) as! [String: Any] }
        var status = 200
        var result: [String: Any]
        switch operation {
        case "readCleanupDeviceCompletionV1":
            #expect(body == nil && request.method == .get)
            #expect(request.headerFields[.authorization] == "Device DEVICE.SYNTHETIC.V3")
            let current = try #require(invocation), call = current["call"] as! [String: Any]
            let parts = try #require(URLComponents(string: request.path!))
            #expect(parts.queryItems?.count == 1 && parts.queryItems?.first?.name == "request_digest")
            #expect(parts.queryItems?.first?.value == current["request_digest"] as? String)
            let account = call["reason"] as? String == "account_cleanup"
            result = ["version":"CLEANUP-DEVICE-COMPLETION@1","operation_id":call["operation_id"]!,"binding_id":call["binding_id"]!,
                "invocation_id":call["invocation_id"]!,"request_digest":current["request_digest"]!,"reason":call["reason"]!,
                "device_state":current["state"]!,"receipt_digest":current["receipt_digest"]!,
                "content_status":account ? completionStatus : "not_applicable",
                "registry_digest":account ? String(repeating:"c",count:64) : NSNull(),
                "control_record_protocol":account ? completionPolicy as Any? ?? NSNull() : NSNull(),
                "complete_scope":account ? "frozen_online_domains_only" : "original_device_action_only", "business_access":"not_granted"]
            changeCompletion?(&result)
        case "registerCleanupDeviceV3":
            let payload: [String: Any] = ["version":"CLEANUP-DEVICE@3", "binding_id":"server-binding", "device_id":input!["device_id"]!,
                "state_ref":input!["state_ref"]!, "scope_digest":String(repeating: "a", count: 64), "device_token":"DEVICE.SYNTHETIC.V3", "server_time":1000, "business_access":"not_granted"]
            registration = payload
            if loseRegistration { throw CleanupFailure.exchangeUnknown }
            result = payload
        case "queryCleanupDeviceRegistrationV3":
            let query = URLComponents(string: request.path!)!.queryItems!
            result = ["version":"CLEANUP-DEVICE@3", "action_id":query.first { $0.name == "action_id" }!.value!,
                "input_sha256":query.first { $0.name == "input_sha256" }!.value!, "registration":nullRegistration ? NSNull() : registration as Any]
        case "verifyDeviceCleanupIdentityV3":
            status = identityStatus
            if status == 200 { result = ["receipt":NSNull()] }
            else { result = ["error":["code":"ACCESS_DENIED","category":"access","message_en":"Unavailable","message_zh":"不可用","outcome":status == 503 ? "unknown" : "failed","recovery":"do_not_retry"]] }
        case "createCleanupDeviceCallV3":
            actionID = input!["action_id"] as? String; actionHash = deviceCleanupSHA(body!)
            let operationID = activeAccountOperation ?? "device-original-operation"
            let call: [String: Any] = ["version":"CLEANUP-DEVICE@3", "operation_id":operationID, "invocation_id":"server-original-invocation",
                "binding_id":"server-binding", "scope_digest":String(repeating:"a", count:64), "state_ref":v3State,
                "reason":activeAccountOperation == nil ? "session_invalid" : "account_cleanup", "targets":legacyDeviceTargetNames, "business_access":"not_granted"]
            invocation = ["call":call,"request_digest":deviceCleanupSHA(try v3Encode(call)),"state":"pending","receipt_digest":NSNull(),"receipt_token":"RECEIPT.SYNTHETIC.V3"]
            if loseCall { throw CleanupFailure.exchangeUnknown }
            result = ["version":"CLEANUP-DEVICE@3", "action_id":actionID!, "input_sha256":actionHash!, "invocation":invocation!]
        case "queryCleanupDeviceCallActionV3":
            result = ["version":"CLEANUP-DEVICE@3", "action_id":actionID!, "input_sha256":actionHash!, "invocation":nullAction ? NSNull() : invocation as Any]
        case "queryCleanupDeviceInvocationV3": result = invocation!
        case "reportCleanupDeviceReceiptV3":
            invocation!["state"] = input!["outcome"]; invocation!["receipt_digest"] = deviceCleanupSHA(body!)
            if loseReceipt { throw CleanupFailure.exchangeUnknown }
            result = invocation!
        default: throw CleanupFailure.unavailable
        }
        let callback = after; after = nil; callback?()
        result["request_id"] = v3Trace
        var headers = HTTPFields(); headers[.contentType] = "application/json"; headers[.cacheControl] = "no-store"
        headers[HTTPField.Name("X-Request-ID")!] = v3Trace
        return (HTTPResponse(status: .init(code: status), headerFields: headers), HTTPBody(try v3Encode(result)))
    }
}
private struct V3Wire: ClientTransport {
    let server: V3Server
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 16384) } else { bytes = nil }
        return try await server.respond(request, body: bytes, operation: operationID)
    }
}
@MainActor private final class V3Harness {
    let scope = AccountCleanupScope(environment: UUID(), account: UUID(), generation: UUID())
    let secure = V3Store(), sdk = V3Store(), server = V3Server()
    let session: SessionLifecycle
    let operation: SessionOperation
    let lifetime: AccountCleanupLifetime
    var client: DeviceCleanupClient!
    let endpoint = try! MessageEndpoint(url: URL(string:"http://127.0.0.1:1234")!,maximumRequestBytes:16384,maximumResponseBytes:65536,allowLoopbackHTTP:true)
    var credentialCallback: (() -> Void)?
    init() throws {
        session = SessionLifecycle(persistence: sdk, restorePolicy: .userInitiatedOnly)
        operation = try session.beginTrustedSDKSave()
        try session.save(SessionMaterial(trustedSDKBytes: Data("SYNTHETIC.SDK".utf8)), for: operation)
        lifetime = AccountCleanupLifetime(scope: scope); client = try ordinary()
    }
    func ordinary() throws -> DeviceCleanupClient {
        try DeviceCleanupClient(endpoint:endpoint,lifetime:lifetime,securePersistence:secure,session:session,sessionOperation:operation,credentials:{ [self] in
            let callback = credentialCallback; credentialCallback=nil; callback?(); return "BEARER.SYNTHETIC.V3"
        },interceptedTransport:V3Wire(server:server))
    }
    func restricted() throws -> DeviceCleanupClient {
        try DeviceCleanupClient(endpoint:endpoint,lifetime:lifetime,securePersistence:secure,interceptedTransport:V3Wire(server:server))
    }
    func enroll() async throws { _ = try await client.perform(client.prepareRegistration(stateRef:v3State)) }
    func refuse() async throws {
        try await enroll()
        guard case .identityRefused = try await client.perform(client.prepareIdentityVerification()) else { throw CleanupFailure.unavailable }
    }
}
@MainActor private final class V3Native: DeviceCleanupNativeExecuting {
    let scope: AccountCleanupScope
    let stateRef = v3State
    let store: V3Store
    var executions = 0, reconciliations = 0
    var first: DeviceCleanupNativeOutcome = .unknown
    var recovered: DeviceCleanupNativeOutcome = .confirmed
    var failReconciliation = false
    init(_ h: V3Harness) { scope=h.scope;store=h.secure }
    func executeOriginal(_ invocation:DeviceCleanupInvocation,intentID:UUID) throws -> DeviceCleanupNativeOutcome {
        #expect(try store.record().nativeIntentID == intentID)
        #expect(invocation.targets.count == 19); executions += 1;return first
    }
    func reconcileOriginal(_ invocation:DeviceCleanupInvocation,intentID:UUID) throws -> DeviceCleanupNativeOutcome {
        #expect(try store.record().nativeIntentID == intentID);reconciliations += 1
        if failReconciliation { throw CleanupFailure.unavailable }; return recovered
    }
}
@MainActor private final class FinalizationMemoryStore: CleanupControlRecordStoring {
    let scope: AccountCleanupScope
    var selected: Data?
    var records: [CleanupControlRecord: Data]
    var removals: [CleanupControlRecord] = []
    var afterStage: (() -> Void)?
    var failAfterRemoval: CleanupControlRecord?
    init(_ h: V3Harness, completion: DeviceCleanupCompletion) throws {
        scope = h.scope
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        selected = try encoder.encode(scope)
        records = [.manifest:Data("manifest".utf8), .execution:Data("execution".utf8),
            .account:Data("account".utf8), .device:try #require(h.secure.value?.withBytes { $0 })]
    }
    func read(_ record: CleanupControlRecord) throws -> Data? { records[record] }
    func readSelected() throws -> Data? { selected }
    func stageSelected(_ plan: Data, expected: Data) throws {
        guard selected == expected else { throw CleanupFailure.stale }; selected = plan; afterStage?()
    }
    func remove(_ record: CleanupControlRecord, expected: Data) throws -> Bool {
        guard records[record] == expected else { return false }
        records[record] = nil; removals.append(record)
        if failAfterRemoval == record { throw CleanupFailure.exchangeUnknown }
        return true
    }
    func removeSelected(expected: Data) throws -> Bool {
        guard selected == expected else { return false }; selected = nil; return true
    }
    func writeTerminalIfSelectedAbsent(_ terminal: Data) throws -> Bool {
        guard selected == nil else { return false }; selected = terminal; return true
    }
}
@MainActor struct DeviceCleanupClientTests {
    private func accountCompletion(_ h: V3Harness) async throws -> DeviceCleanupCompletion {
        try await h.refuse(); h.server.activeAccountOperation = "server-original-account-operation"
        _ = try await h.client.perform(h.client.prepareSessionInvalidation())
        let native = V3Native(h); native.first = .confirmed
        _ = try h.client.executeNative(using: native)
        _ = try await h.client.perform(h.client.prepareReceipt())
        let before = h.secure.value?.withBytes { $0 }
        guard case .completion(let result) = try await h.client.perform(h.client.prepareCompletionQuery()) else { throw CleanupFailure.unavailable }
        #expect(h.secure.value?.withBytes { $0 } == before)
        return result
    }
    @Test func originalCompletionUsesOnlyDeviceCredentialAndDoesNotMutateTheJournal() async throws {
        let h = try V3Harness()
        let completion = try await accountCompletion(h)
        #expect(completion.permitsAccountRecordFinalization && completion.scope == h.scope)
        #expect(completion.operationID == "server-original-account-operation" && completion.contentStatus == .complete)
        #expect(completion.journalSHA256 == h.secure.value?.withBytes(deviceCleanupSHA))
        try h.session.clear()
        _ = try await h.client.perform(h.client.prepareCompletionQuery())
        #expect(h.server.requests.last?.auth == "Device DEVICE.SYNTHETIC.V3")
    }
    @Test(arguments: ["in_progress", "unknown", "blocked", "failed", "no-policy"])
    func contentNotCompleteOrMissingPolicyNeverFinalizesControls(_ status: String) async throws {
        let h = try V3Harness()
        if status == "no-policy" { h.server.completionPolicy = nil } else { h.server.completionStatus = status }
        let completion = try await accountCompletion(h)
        #expect(!completion.permitsAccountRecordFinalization)
    }
    @Test func standaloneInvalidationAndUnacknowledgedOwnOutcomeCannotFinalizeAccountControls() async throws {
        let h = try V3Harness(); try await h.refuse()
        _ = try await h.client.perform(h.client.prepareSessionInvalidation())
        guard case .completion(let standalone) = try await h.client.perform(h.client.prepareCompletionQuery()) else { throw CleanupFailure.unavailable }
        #expect(standalone.reason == .sessionInvalid && !standalone.permitsAccountRecordFinalization && standalone.contentStatus == .notApplicable)
        let other = try V3Harness(); try await other.refuse(); other.server.activeAccountOperation = "account-original"
        _ = try await other.client.perform(other.client.prepareSessionInvalidation())
        let native = V3Native(other); native.first = .confirmed; _ = try other.client.executeNative(using: native)
        other.server.loseReceipt = true
        await #expect(throws: CleanupFailure.exchangeUnknown) { try await other.client.perform(other.client.prepareReceipt()) }
        guard case .completion(let unacknowledged) = try await other.client.perform(other.client.prepareCompletionQuery()) else { throw CleanupFailure.unavailable }
        #expect(!unacknowledged.permitsAccountRecordFinalization)
    }
    @Test(arguments: ["operation_id", "binding_id", "invocation_id", "request_digest", "receipt_digest", "reason", "control_record_protocol", "business_access"])
    func completionCannotRetargetOrBroadenOriginalEvidence(_ field: String) async throws {
        let h = try V3Harness()
        h.server.changeCompletion = { fields in
            fields[field] = field.hasSuffix("digest") ? String(repeating:"e",count:64) : "other"
        }
        await #expect(throws: CleanupFailure.invalidResponse) { try await accountCompletion(h) }
    }
    @Test func finalizationPlanRecoversOnlyItsOwnMissingRecordsAndLeavesHashOnlyTerminal() async throws {
        let h = try V3Harness(), completion = try await accountCompletion(h)
        let store = try FinalizationMemoryStore(h, completion: completion)
        store.failAfterRemoval = .device
        #expect(throws: CleanupFailure.exchangeUnknown) { try CleanupControlFinalizer.start(completion: completion, store: store) }
        let staged = try #require(store.selected)
        let plan = try CleanupControlFinalizationPlan(bytes: staged)
        store.failAfterRemoval = nil
        let terminal = try CleanupControlFinalizer.resume(plan: plan, store: store)
        #expect(store.records.isEmpty && store.removals.filter { $0 == .device }.count == 1)
        let raw = try terminal.encoded(), restored = try CleanupControlTerminal(bytes: raw)
        #expect(restored.outcome == "original_control_records_cleared" && store.selected == raw)
        #expect(!raw.contains(Data(h.scope.account.uuidString.utf8)) && !raw.contains(Data(completion.operationID.utf8)))
        #expect(!raw.contains(Data("DEVICE.SYNTHETIC.V3".utf8)))
    }
    @Test func replacementAndAnotherSelectedAccountWithholdAllFinalization() async throws {
        let h = try V3Harness(), completion = try await accountCompletion(h)
        let store = try FinalizationMemoryStore(h, completion: completion)
        store.afterStage = { store.records[.account] = Data("different-generation".utf8) }
        #expect(throws: CleanupFailure.stale) { try CleanupControlFinalizer.start(completion: completion, store: store) }
        #expect(store.removals.isEmpty)
        let other = try FinalizationMemoryStore(h, completion: completion)
        other.selected = try v3Encode(["environment":h.scope.environment.uuidString,"account":UUID().uuidString,"generation":UUID().uuidString])
        let before = other.selected
        #expect(throws: CleanupFailure.stale) { try CleanupControlFinalizer.start(completion: completion, store: other) }
        #expect(other.removals.isEmpty && other.selected == before)
    }
    @Test func firstRegistrationLostACKUsesOriginalHashGETAndNullNeverReposts() async throws {
        let h=try V3Harness();h.server.loseRegistration=true
        let work=try h.client.prepareRegistration(stateRef:v3State),original=try h.secure.record().registration
        await #expect(throws:CleanupFailure.exchangeUnknown){try await h.client.perform(work)}
        h.client=try h.ordinary();h.server.nullRegistration=true
        guard case .notObserved=try await h.client.perform(h.client.prepareRegistrationQuery()) else {Issue.record("null fabricated registration");return}
        #expect(throws:CleanupFailure.unavailable){try h.client.prepareRegistration(stateRef:v3State)}
        h.server.nullRegistration=false
        guard case .enrolled(let enrollment)=try await h.client.perform(h.client.prepareRegistrationQuery()) else {Issue.record("original enrollment not recovered");return}
        #expect(enrollment.originalUTF8==original)
        #expect(h.server.requests.filter{$0.operation=="registerCleanupDeviceV3"}.count==1)
    }
    @Test func unknownIdentityNeverAuthorizesCallOrErasure() async throws {
        let h=try V3Harness();try await h.enroll();h.server.identityStatus=503
        #expect(try !h.client.hasVerifiedIdentityRefusal)
        await #expect(throws:CleanupFailure.exchangeUnknown){try await h.client.perform(h.client.prepareIdentityVerification())}
        #expect(throws:CleanupFailure.unavailable){try h.client.prepareSessionInvalidation()}
        #expect(try h.secure.record().action==nil && h.secure.record().nativeIntentID==nil)
        #expect(try !h.client.hasVerifiedIdentityRefusal)
    }
    @Test func lostCallACKIsStickyAcrossLaterAccountFenceAndSDKClear() async throws {
        let h=try V3Harness();try await h.refuse();h.server.loseCall=true
        let work=try h.client.prepareSessionInvalidation(),raw=try h.secure.record().action
        await #expect(throws:CleanupFailure.exchangeUnknown){try await h.client.perform(work)}
        try h.session.clear();h.server.activeAccountOperation="later-account-operation";h.client=try h.restricted()
        h.server.nullAction=true
        guard case .notObserved=try await h.client.perform(h.client.prepareOriginalCallQuery()) else {Issue.record("null fabricated invocation");return}
        #expect(throws:CleanupFailure.unavailable){try h.client.prepareSessionInvalidation()}
        h.server.nullAction=false
        guard case .invocation(let invocation)=try await h.client.perform(h.client.prepareOriginalCallQuery()) else {Issue.record("original call not recovered");return}
        #expect(invocation.operationID=="device-original-operation")
        #expect(try h.secure.record().action==raw)
        #expect(h.server.requests.last?.auth=="Device DEVICE.SYNTHETIC.V3")
        #expect(h.server.requests.filter{$0.operation=="createCleanupDeviceCallV3"}.count==1)
    }
    @Test func originalNativeIntentReconcilesAndReceiptACKLossOnlyQueries() async throws {
        let h=try V3Harness();try await h.refuse();_ = try await h.client.perform(h.client.prepareSessionInvalidation())
        let native=V3Native(h)
        #expect(try h.client.executeNative(using:native) == .unknown)
        h.server.loseReceipt=true;let receipt=try h.client.prepareReceipt(),raw=try h.secure.record().receipts.last?.originalUTF8
        await #expect(throws:CleanupFailure.exchangeUnknown){try await h.client.perform(receipt)}
        #expect(try h.client.executeNative(using:native) == .confirmed)
        #expect(throws:CleanupFailure.unavailable){try h.client.prepareReceipt()}
        _ = try await h.client.perform(h.client.prepareOriginalInvocationQuery())
        #expect(try h.secure.record().receipts[0].acknowledged)
        #expect(try h.secure.record().receipts[0].originalUTF8==raw)
        h.server.loseReceipt=false
        guard case .invocation(let final)=try await h.client.perform(h.client.prepareReceipt()) else {Issue.record("no original receipt result");return}
        #expect(final.state == .confirmed && native.executions==1 && native.reconciliations==1)
        #expect(h.server.requests.filter{$0.operation=="reportCleanupDeviceReceiptV3"}.count==2)
        #expect(throws:CleanupFailure.unavailable){try h.client.prepareReceipt()}
    }
    @Test func nativeOutcomeBeforeFirstReceiptCanResumeButUnacknowledgedReceiptCannotRepost() async throws {
        let h = try V3Harness(); try await h.refuse()
        _ = try await h.client.perform(h.client.prepareSessionInvalidation())
        let native = V3Native(h); native.first = .confirmed
        #expect(try h.client.executeNative(using: native) == .confirmed)
        let originalIntent = try h.secure.record().nativeIntentID
        h.client = try h.restricted()
        _ = try await h.client.perform(h.client.prepareOriginalInvocationQuery())
        #expect(try h.client.canPrepareReceipt)
        #expect(try h.secure.record().receipts.isEmpty)
        let first = try h.client.prepareReceipt()
        #expect(try !h.client.canPrepareReceipt)
        h.server.loseReceipt = true
        await #expect(throws: CleanupFailure.exchangeUnknown) { try await h.client.perform(first) }
        h.client = try h.restricted()
        #expect(try !h.client.canPrepareReceipt)
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareReceipt() }
        _ = try await h.client.perform(h.client.prepareOriginalInvocationQuery())
        #expect(try !h.client.canPrepareReceipt)
        #expect(try h.secure.record().nativeIntentID == originalIntent)
        #expect(native.executions == 1 && native.reconciliations == 0)
        #expect(h.server.requests.filter { $0.operation == "reportCleanupDeviceReceiptV3" }.count == 1)
    }
    @Test func originalActionQueryCannotRetargetAnAlreadySealedNativeCall() async throws {
        let h = try V3Harness(); try await h.refuse()
        _ = try await h.client.perform(h.client.prepareSessionInvalidation())
        let original = try h.secure.record().invocationReply
        var result = try #require(h.server.invocation), call = try #require(result["call"] as? [String: Any])
        call["operation_id"] = "another-valid-operation"
        call["invocation_id"] = "another-valid-invocation"
        result["call"] = call; result["request_digest"] = deviceCleanupSHA(try v3Encode(call))
        h.server.invocation = result
        await #expect(throws: CleanupFailure.invalidResponse) { try await h.client.perform(h.client.prepareOriginalCallQuery()) }
        #expect(try h.secure.record().invocationReply == original)
        #expect(try h.secure.record().nativeIntentID == nil)
    }
    @Test func throwingOriginalReconciliationRetainsIntentAndNeverRunsAnotherErase() async throws {
        let h = try V3Harness(); try await h.refuse()
        _ = try await h.client.perform(h.client.prepareSessionInvalidation())
        let native = V3Native(h)
        #expect(try h.client.executeNative(using: native) == .unknown)
        let originalIntent = try h.secure.record().nativeIntentID
        native.failReconciliation = true
        #expect(throws: CleanupFailure.exchangeUnknown) { try h.client.executeNative(using: native) }
        #expect(try h.secure.record().nativeIntentID == originalIntent)
        #expect(try h.secure.record().nativeOutcome == .unknown)
        #expect(native.executions == 1 && native.reconciliations == 1)
    }
    @Test func callbackAccountSwitchAndLateResponseCannotCommitAnotherScope() async throws {
        let h=try V3Harness(),work=try h.client.prepareRegistration(stateRef:v3State)
        h.credentialCallback={h.lifetime.invalidate()}
        await #expect(throws:CleanupFailure.stale){try await h.client.perform(work)}
        #expect(h.server.requests.isEmpty)
        let other=try V3Harness(),late=try other.client.prepareRegistration(stateRef:v3State)
        let before=other.secure.value?.withBytes{$0};other.server.after={other.lifetime.invalidate()}
        await #expect(throws:CleanupFailure.stale){try await other.client.perform(late)}
        #expect(other.secure.value?.withBytes{$0}==before)
    }
}
