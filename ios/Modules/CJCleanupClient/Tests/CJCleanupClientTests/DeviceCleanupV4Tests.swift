import Foundation
import Testing
import CJSession
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJCleanupClient

private let v4Trace = "44444444-4444-4444-8444-444444444468"
private let v4State = String(repeating: "b", count: 64)
private let v4TargetNames = legacyDeviceTargetNames + ["device-cache/memory-erasure-pending", "device-cache/memory-candidate-pending"]
private func v4JSON(_ object: [String: Any]) throws -> Data {
    try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes])
}
@MainActor private final class V4Store: SessionPersistence {
    var material: SessionMaterial?
    func load() throws -> SessionMaterial? { material }
    func save(_ value: SessionMaterial) throws { material = value }
    func clearAndBlock() throws { material = nil }
}
@MainActor private final class V4Server {
    var requests: [(String, String, Data?)] = []
    var registration: [String: Any]?
    var invocation: [String: Any]?
    var action: [String: Any]?
    var actionHash: String?
    var loseRegistration = false, loseCall = false, loseReceipt = false
    var changeReply: ((inout [String: Any]) -> Void)?
    func respond(_ request: HTTPRequest, body: Data?, operation: String) throws -> (HTTPResponse, HTTPBody?) {
        requests.append((operation, request.path!, body))
        let input = try body.map { try JSONSerialization.jsonObject(with: $0) as! [String: Any] }
        var reply: [String: Any], status = 200
        switch operation {
        case "registerCleanupDeviceV4":
            #expect(request.path == "/v4/cleanup-devices" && input?["version"] as? String == "CLEANUP-DEVICE@4")
            #expect(request.headerFields[.authorization] == "Bearer SDK.SYNTHETIC.V4")
            registration = ["version":"CLEANUP-DEVICE@4","binding_id":"binding-v4","device_id":input!["device_id"]!,
                "state_ref":input!["state_ref"]!,"scope_digest":String(repeating:"a",count:64),"device_token":"DEVICE.SYNTHETIC.V4",
                "server_time":1000,"business_access":"not_granted"]
            if loseRegistration { throw CleanupFailure.exchangeUnknown }
            reply = registration!
        case "queryCleanupDeviceRegistrationV4":
            #expect(request.path!.hasPrefix("/v4/cleanup-device-registrations?"))
            let q = URLComponents(string:request.path!)!.queryItems!
            reply = ["version":"CLEANUP-DEVICE@4","action_id":q.first{$0.name == "action_id"}!.value!,
                "input_sha256":q.first{$0.name == "input_sha256"}!.value!,"registration":registration as Any]
        case "verifyDeviceCleanupIdentityV4":
            status = 403
            reply = ["error":["code":"ACCESS_DENIED","category":"access","message_en":"Unavailable","message_zh":"不可用",
                "outcome":"failed","recovery":"do_not_retry"]]
        case "createCleanupDeviceCallV4":
            #expect(request.path == "/v4/cleanup-device-calls" && input?["version"] as? String == "CLEANUP-DEVICE@4")
            #expect(request.headerFields[.authorization] == "Device DEVICE.SYNTHETIC.V4")
            action = input; actionHash = deviceCleanupSHA(body!)
            let call: [String: Any] = ["version":"CLEANUP-DEVICE@4","operation_id":"server-original-operation-v4",
                "invocation_id":"server-original-invocation-v4","binding_id":"binding-v4","scope_digest":String(repeating:"a",count:64),
                "state_ref":v4State,"reason":"session_invalid","targets":v4TargetNames,"business_access":"not_granted"]
            invocation = ["call":call,"request_digest":deviceCleanupSHA(try v4JSON(call)),"state":"pending",
                "receipt_digest":NSNull(),"receipt_token":"RECEIPT.SYNTHETIC.V4"]
            if loseCall { throw CleanupFailure.exchangeUnknown }
            reply = ["version":"CLEANUP-DEVICE@4","action_id":action!["action_id"]!,"input_sha256":actionHash!,"invocation":invocation!]
        case "queryCleanupDeviceCallActionV4":
            #expect(request.path!.hasPrefix("/v4/cleanup-device-call-actions?"))
            reply = ["version":"CLEANUP-DEVICE@4","action_id":action!["action_id"]!,"input_sha256":actionHash!,"invocation":invocation!]
        case "queryCleanupDeviceInvocationV4":
            #expect(request.path == "/v4/cleanup-device-calls/server-original-invocation-v4")
            reply = invocation!
        case "reportCleanupDeviceReceiptV4":
            #expect(request.path == "/v4/cleanup-device-receipts" && input?["version"] as? String == "CLEANUP-DEVICE@4")
            #expect(request.headerFields[.authorization] == "Cleanup RECEIPT.SYNTHETIC.V4")
            invocation!["state"] = input!["outcome"]!; invocation!["receipt_digest"] = deviceCleanupSHA(body!)
            if loseReceipt { throw CleanupFailure.exchangeUnknown }
            reply = invocation!
        case "readCleanupDeviceCompletionV2":
            #expect(request.method == .get && body == nil && request.path!.hasPrefix("/v2/cleanup-device-completions/server-original-invocation-v4?"))
            #expect(request.headerFields[.authorization] == "Device DEVICE.SYNTHETIC.V4")
            let value = invocation!, call = value["call"] as! [String:Any]
            reply = ["version":"CLEANUP-DEVICE-COMPLETION@2","operation_id":call["operation_id"]!,"binding_id":"binding-v4",
                "invocation_id":call["invocation_id"]!,"request_digest":value["request_digest"]!,"reason":"session_invalid",
                "device_state":value["state"]!,"receipt_digest":value["receipt_digest"]!,"content_status":"not_applicable",
                "registry_digest":NSNull(),"control_record_protocol":NSNull(),"complete_scope":"original_device_action_only","business_access":"not_granted"]
        default: throw CleanupFailure.unavailable
        }
        reply["request_id"] = v4Trace; changeReply?(&reply)
        var response = HTTPResponse(status:.init(code:status));response.headerFields[.contentType]="application/json"
        response.headerFields[.cacheControl]="no-store";response.headerFields[HTTPField.Name("X-Request-ID")!]=v4Trace
        return (response, HTTPBody(try v4JSON(reply)))
    }
}
private struct V4Wire: ClientTransport {
    let server: V4Server
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting:body,upTo:16384) } else { bytes = nil }
        return try await server.respond(request, body:bytes, operation:operationID)
    }
}
@MainActor private final class V4Fixture {
    let scope = AccountCleanupScope(environment:UUID(),account:UUID(),generation:UUID())
    let secure = V4Store(), sdk = V4Store(), server = V4Server()
    let session: SessionLifecycle
    let operation: SessionOperation
    let lifetime: AccountCleanupLifetime
    let endpoint = try! MessageEndpoint(url:URL(string:"http://127.0.0.1:1234")!,maximumRequestBytes:16384,maximumResponseBytes:65536,allowLoopbackHTTP:true)
    var client: DeviceCleanupClient!
    init() throws {
        session = SessionLifecycle(persistence:sdk,restorePolicy:.userInitiatedOnly)
        operation = try session.beginTrustedSDKSave();try session.save(.init(trustedSDKBytes:Data("SDK.SYNTHETIC.V4".utf8)),for:operation)
        lifetime = AccountCleanupLifetime(scope:scope);client = try make()
    }
    func make(version: CleanupDeviceVersion = .v4) throws -> DeviceCleanupClient {
        try DeviceCleanupClient(endpoint:endpoint,lifetime:lifetime,securePersistence:secure,session:session,sessionOperation:operation,
            credentials:{"SDK.SYNTHETIC.V4"},interceptedTransport:V4Wire(server:server),version:version)
    }
    func call() async throws -> DeviceCleanupInvocation {
        _ = try await client.perform(client.prepareRegistration(stateRef:v4State))
        _ = try await client.perform(client.prepareIdentityVerification())
        guard case .invocation(let value) = try await client.perform(client.prepareSessionInvalidation()) else { throw CleanupFailure.invalidResponse }
        return value
    }
}
@MainActor private final class V4Native: DeviceCleanupNativeExecuting {
    let scope: AccountCleanupScope
    let stateRef = v4State
    let store: V4Store
    var calls = 0
    init(_ f: V4Fixture) { scope=f.scope;store=f.secure }
    func executeOriginal(_ invocation: DeviceCleanupInvocation, intentID: UUID) throws -> DeviceCleanupNativeOutcome {
        let bytes = try #require(store.material?.withBytes{$0})
        let record = try JSONDecoder().decode(DeviceCleanupRecord.self,from:bytes)
        #expect(record.nativeIntentID == intentID && invocation.version == .v4 && invocation.targets.count == 21)
        calls += 1;return .confirmed
    }
    func reconcileOriginal(_ invocation: DeviceCleanupInvocation, intentID: UUID) throws -> DeviceCleanupNativeOutcome { .confirmed }
}
@MainActor struct DeviceCleanupV4Tests {
    @Test func currentV4UsesTwentyOneTargetsAndOriginalCompletion2WithoutRelabeling() async throws {
        let f = try V4Fixture(), invocation = try await f.call()
        #expect(invocation.version == .v4 && Set(invocation.targets.map(\.rawValue)) == Set(v4TargetNames))
        let native = V4Native(f);#expect(try f.client.executeNative(using:native) == .confirmed && native.calls == 1)
        _ = try await f.client.perform(f.client.prepareReceipt())
        let before = try #require(f.secure.material?.withBytes{$0})
        guard case .completion(let value) = try await f.client.perform(f.client.prepareCompletionQuery()) else { Issue.record("Expected completion2");return }
        #expect(value.deviceState == .confirmed && !value.permitsAccountRecordFinalization)
        #expect(try f.secure.material?.withBytes{$0} == before)
    }
    @Test func registrationAckLossRestoresItsOriginalV4EvenWithLegacyConstructorDefault() async throws {
        let f = try V4Fixture();f.server.loseRegistration=true
        await #expect(throws:(any Error).self) { try await f.client.perform(f.client.prepareRegistration(stateRef:v4State)) }
        let original = try #require(f.secure.material?.withBytes{$0})
        f.client = try f.make(version:.v3)
        #expect(f.client.version == .v4)
        #expect(throws:(any Error).self) { try f.client.prepareRegistration(stateRef:v4State) }
        guard case .enrolled(let enrollment) = try await f.client.perform(f.client.prepareRegistrationQuery()) else { Issue.record("Expected original V4");return }
        #expect(enrollment.version == .v4 && f.server.requests.filter{$0.0 == "registerCleanupDeviceV4"}.count == 1)
        let fields = try JSONSerialization.jsonObject(with:original) as! [String:Any]
        #expect(fields["version"] as? String == "DeviceCleanup.Native@2")
    }
    @Test func missingFamilyOrCompletion1CannotBeAcceptedForCurrentV4() async throws {
        let f = try V4Fixture();_ = try await f.call()
        let native = V4Native(f);_ = try f.client.executeNative(using:native);_ = try await f.client.perform(f.client.prepareReceipt())
        f.server.changeReply = { $0["version"] = "CLEANUP-DEVICE-COMPLETION@1" }
        await #expect(throws:(any Error).self) { try await f.client.perform(f.client.prepareCompletionQuery()) }
        let g = try V4Fixture()
        _ = try await g.client.perform(g.client.prepareRegistration(stateRef:v4State));_ = try await g.client.perform(g.client.prepareIdentityVerification())
        g.server.changeReply = { root in
            var payload=root["invocation"] as! [String:Any],call=payload["call"] as! [String:Any]
            call["targets"]=Array(v4TargetNames.dropLast());payload["call"]=call
            payload["request_digest"]=deviceCleanupSHA(try! v4JSON(call));root["invocation"]=payload
        }
        await #expect(throws:(any Error).self) { try await g.client.perform(g.client.prepareSessionInvalidation()) }
    }
    @Test func accountAPI1AdoptsOnlyTheSealedV4AndPersistsSeparateVersion3Record() async throws {
        let f = try V4Fixture();_ = try await f.client.perform(f.client.prepareRegistration(stateRef:v4State))
        let store = V4Store()
        let client = try AccountCleanupClient(endpoint:f.endpoint,lifetime:f.lifetime,securePersistence:store,session:f.session,sessionOperation:f.operation,
            credentials:{"SDK.SYNTHETIC.V4"},beforeConfirmation:{_ in},interceptedTransport:V4Wire(server:f.server))
        try client.adoptDeviceEnrollment(f.client.acceptedEnrollment())
        let bytes = try #require(store.material?.withBytes{$0}), record = try JSONDecoder().decode(AccountCleanupRecord.self,from:bytes)
        #expect(record.version == "AccountCleanup.Native@3" && record.deviceV4Scope == f.scope && record.deviceV3Scope == nil)
        try record.validate(scope:f.scope)
    }
}
