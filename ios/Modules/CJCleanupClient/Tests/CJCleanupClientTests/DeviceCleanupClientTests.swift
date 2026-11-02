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
    var after: (() -> Void)?
    func respond(_ request: HTTPRequest, body: Data?, operation: String) throws -> (HTTPResponse, HTTPBody?) {
        requests.append((operation, body, request.headerFields[.authorization]))
        let input = try body.map { try JSONSerialization.jsonObject(with: $0) as! [String: Any] }
        var status = 200
        var result: [String: Any]
        switch operation {
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
                "reason":activeAccountOperation == nil ? "session_invalid" : "account_cleanup", "targets":DeviceCleanupTarget.allCases.map(\.rawValue), "business_access":"not_granted"]
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
@MainActor struct DeviceCleanupClientTests {
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
