import Foundation
import Testing
import CJSession
import CJMessageHTTP
import HTTPTypes
import OpenAPIRuntime
@testable import CJCleanupClient

private let accountTrace = "11111111-1111-4111-8111-111111111443"
private let accountHash = String(repeating: "a", count: 64)
@MainActor private final class AccountSecureStore: SessionPersistence {
    var value: SessionMaterial?
    var onSave: (() throws -> Void)?
    var onLoad: (() throws -> Void)?
    var failSave = false
    func load() throws -> SessionMaterial? { let callback = onLoad; onLoad = nil; try callback?(); return value }
    func save(_ material: SessionMaterial) throws {
        value = material
        let callback = onSave; onSave = nil; try callback?()
        if failSave { throw CleanupFailure.unavailable }
    }
    func clearAndBlock() throws { value = nil }
    func record() throws -> AccountCleanupRecord {
        guard let value else { throw CleanupFailure.unavailable }
        return try value.withBytes { try JSONDecoder().decode(AccountCleanupRecord.self, from: $0) }
    }
    var bytes: Data? { value?.withBytes { $0 } }
}
@MainActor private final class AccountServer {
    var requests: [(operation: String, path: String, body: Data?, authorization: String?)] = []
    var registered: [String: Any]?
    var prepared: [String: Any]?
    var committed = false
    var blocked = false
    var loseRegistrationACK = false
    var losePreparationACK = false
    var loseConfirmationACK = false
    var nullPreparation = false
    var callback: (() throws -> Void)?
    var transform: ((String, [String: Any]) -> [String: Any])?
    var rawTransform: ((String, Data) -> Data)?
    var responseStatus = 200
    func response(_ request: HTTPRequest, body: Data?, operation: String) throws -> (HTTPResponse, HTTPBody?) {
        requests.append((operation, request.path!, body, request.headerFields[.authorization]))
        let input = try body.map { try JSONSerialization.jsonObject(with: $0) as! [String: Any] }
        let result: [String: Any]
        switch operation {
        case "registerCleanupDeviceV1":
            let value: [String: Any] = ["version":"CLEANUP-DEVICE@1", "request_id":accountTrace,
                "binding_id":"server-binding", "device_id":input!["device_id"]!, "state_ref":input!["state_ref"]!,
                "scope_digest":accountHash, "device_token":"DEVICE.SYNTHETIC.CAP", "server_time":1000, "business_access":"not_granted"]
            registered = value
            if loseRegistrationACK { throw CleanupFailure.exchangeUnknown }
            result = value
        case "prepareAccountCleanupV1":
            let value: [String: Any] = ["version":"CLEANUP-API@1", "request_id":accountTrace,
                "operation_id":"server-original-operation", "phase":"prepared", "registry_digest":accountHash,
                "plan_digest":accountHash, "binding_id":"server-binding", "revision":0,
                "confirmation":"DELETE_ACCOUNT", "progress_token":"PROGRESS.SYNTHETIC.CAP"]
            prepared = value
            if losePreparationACK { throw CleanupFailure.exchangeUnknown }
            result = value
        case "queryAccountCleanupPreparationV1":
            var value = prepared
            value?.removeValue(forKey: "version"); value?.removeValue(forKey: "request_id"); value?.removeValue(forKey: "confirmation")
            result = ["version":"CLEANUP-API@1", "request_id":accountTrace, "preparation":nullPreparation ? NSNull() : value as Any]
        case "confirmAccountCleanupV1":
            if blocked {
                result = ["version":"CLEANUP-API@1", "request_id":accountTrace, "operation_id":"server-original-operation",
                    "phase":"prepared", "status":"blocked", "steps":[["target":"business/message", "state":"pending"]],
                    "reason":"domain_hooks_unavailable", "business_access":"unchanged"]
            } else {
                committed = true
                if loseConfirmationACK { throw CleanupFailure.exchangeUnknown }
                result = progress()
            }
        case "readOriginalAccountCleanupV1": result = progress()
        default: throw CleanupFailure.unavailable
        }
        let callback = self.callback; self.callback = nil; try callback?()
        let output = transform?(operation, result) ?? result
        var headers = HTTPFields(); headers[.contentType] = "application/json"; headers[.cacheControl] = "no-store"
        headers[HTTPField.Name("X-Request-ID")!] = accountTrace
        let raw = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
        return (HTTPResponse(status: .init(code: responseStatus), headerFields: headers),
            HTTPBody(rawTransform?(operation, raw) ?? raw))
    }
    func progress() -> [String: Any] {
        if !committed {
            return ["version":"CLEANUP-API@1", "request_id":accountTrace, "operation_id":"server-original-operation",
                "phase":"prepared", "status":"awaiting_confirmation", "revision":0, "steps":[]]
        }
        return ["version":"CLEANUP-API@1", "request_id":accountTrace, "operation_id":"server-original-operation",
            "phase":"confirmed", "status":"in_progress", "online_status":"complete", "revision":1,
            "steps":[["target":"business/message", "state":"confirmed"]], "devices":[],
            "obligations":["backups":"unverified_30_day_rolling", "other_devices":"pending_actual_receipts", "external":"unverified"],
            "complete_scope":"frozen_online_domains_only", "business_access":"revoked"]
    }
}
private struct AccountIntercept: ClientTransport {
    let server: AccountServer
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let bytes: Data?
        if let body { bytes = try await Data(collecting: body, upTo: 16384) } else { bytes = nil }
        return try await server.response(request, body: bytes, operation: operationID)
    }
}
@MainActor private final class AccountHarness {
    let scope = AccountCleanupScope(environment: UUID(), account: UUID(), generation: UUID())
    let sdkStore = AccountSecureStore()
    let secure = AccountSecureStore()
    let server = AccountServer()
    let endpoint = try! MessageEndpoint(url: URL(string: "http://127.0.0.1:1234")!, maximumRequestBytes: 16384,
        maximumResponseBytes: 65536, allowLoopbackHTTP: true)
    let session: SessionLifecycle
    let operation: SessionOperation
    let lifetime: AccountCleanupLifetime
    var client: AccountCleanupClient!
    var credentialCalls = 0
    var beforeConfirmCalls = 0
    var credentialCallback: (() throws -> Void)?
    var beforeConfirmation: (() throws -> Void)?
    init() throws {
        session = SessionLifecycle(persistence: sdkStore, restorePolicy: .userInitiatedOnly)
        operation = try session.beginTrustedSDKSave()
        try session.save(SessionMaterial(trustedSDKBytes: Data("synthetic verified SDK envelope".utf8)), for: operation)
        lifetime = AccountCleanupLifetime(scope: scope)
        client = try ordinary()
    }
    func ordinary() throws -> AccountCleanupClient {
        try AccountCleanupClient(endpoint: endpoint, lifetime: lifetime, securePersistence: secure,
            session: session, sessionOperation: operation, credentials: { [self] in
                credentialCalls += 1
                let callback = credentialCallback; credentialCallback = nil; try callback?()
                return "ORDINARY.SYNTHETIC.JWT"
            }, beforeConfirmation: { [self] operation in
                #expect(operation == "server-original-operation")
                #expect(try secure.record().prepared != nil && secure.record().confirmation != nil && !secure.record().confirmationDispatched)
                beforeConfirmCalls += 1; try beforeConfirmation?()
            }, interceptedTransport: AccountIntercept(server: server))
    }
    func restricted() throws -> AccountCleanupClient {
        try AccountCleanupClient(endpoint: endpoint, lifetime: lifetime, securePersistence: secure,
            interceptedTransport: AccountIntercept(server: server))
    }
    func register() async throws {
        let work = try client.prepareDeviceRegistration(stateRef: accountHash)
        try await client.perform(work)
    }
    func prepare() async throws -> AccountCleanupPreparation {
        try await register()
        let work = try client.prepareAccountDeletion(); try await client.perform(work)
        guard case .awaitingConfirmation(let value) = client.state else { throw CleanupFailure.unavailable }
        return value
    }
    func confirmation(_ original: AccountCleanupPreparation) throws -> AccountCleanupWork {
        try client.prepareConfirmation(operationID: original.operationID, registryDigest: original.registryDigest, confirmation: "DELETE_ACCOUNT")
    }
}

@MainActor struct AccountCleanupTests {
    @Test func exactBytesAreSecureBeforePostAndOnlyServerCreatesOperation() async throws {
        let h = try AccountHarness()
        let registration = try h.client.prepareDeviceRegistration(stateRef: accountHash)
        let first = try h.secure.record()
        #expect(h.server.requests.isEmpty && first.registration != nil && first.registered == nil)
        try await h.client.perform(registration)
        #expect(h.server.requests[0].body == first.registration)
        let prepare = try h.client.prepareAccountDeletion(); let before = try h.secure.record()
        #expect(before.preparation != nil && before.prepared == nil)
        try await h.client.perform(prepare)
        #expect(h.server.requests[1].body == before.preparation)
        guard case .awaitingConfirmation(let original) = h.client.state else { Issue.record("no actual original operation"); return }
        #expect(original.operationID == "server-original-operation")
        #expect(!String(reflecting: original).contains("PROGRESS.SYNTHETIC"))
        #expect(Mirror(reflecting: original).children.isEmpty)
        #expect(h.server.requests.allSatisfy { $0.authorization == "Bearer ORDINARY.SYNTHETIC.JWT" })
        #expect(h.beforeConfirmCalls == 0 && !h.server.committed)
        await #expect(throws: CleanupFailure.stale) { try await h.client.perform(prepare) }
        #expect(h.server.requests.count == 2)
    }
    @Test func lostPreparationACKReopenQueriesOriginalAndNullDoesNotReleaseAnotherPost() async throws {
        let h = try AccountHarness(); try await h.register(); h.server.losePreparationACK = true
        let work = try h.client.prepareAccountDeletion(); let bytes = try h.secure.record().preparation
        await #expect(throws: CleanupFailure.exchangeUnknown) { try await h.client.perform(work) }
        h.client = try h.ordinary()
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareAccountDeletion() }
        h.server.nullPreparation = true
        guard case .notObserved = try await h.client.read(h.client.prepareOriginalRead()) else { Issue.record("null fabricated an operation"); return }
        #expect(try h.secure.record().preparation == bytes)
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareAccountDeletion() }
        h.server.nullPreparation = false
        guard case .prepared(let original) = try await h.client.read(h.client.prepareOriginalRead()) else { Issue.record("original query not reconciled"); return }
        #expect(original.operationID == "server-original-operation")
        #expect(h.server.requests.filter { $0.body != nil }.count == 2)
        #expect(h.server.requests.last?.path.hasPrefix("/v1/account-cleanup-preparations?action_id=") == true)
    }
    @Test func lostConfirmationACKClearedSDKUsesOnlyRestrictedOriginalProgress() async throws {
        let h = try AccountHarness(); let original = try await h.prepare()
        h.server.loseConfirmationACK = true
        let work = try h.confirmation(original); let body = try h.secure.record().confirmation
        await #expect(throws: CleanupFailure.exchangeUnknown) { try await h.client.perform(work) }
        #expect(h.beforeConfirmCalls == 1 && h.server.committed)
        #expect(try h.client.requiresRestrictedProgress)
        #expect(try h.secure.record().confirmationDispatched)
        try h.session.clear()
        h.client = try h.restricted(); let calls = h.credentialCalls
        let read = try h.client.prepareOriginalRead()
        guard case .progress(let progress) = try await h.client.read(read) else { Issue.record("restricted progress unavailable"); return }
        #expect(progress.operationID == original.operationID && progress.businessRevoked)
        #expect(progress.onlineStatus == .complete && progress.status == .inProgress)
        #expect(!progress.allDevicesAndBackupsVerified)
        #expect(h.credentialCalls == calls)
        #expect(h.server.requests.last?.authorization == "Cleanup PROGRESS.SYNTHETIC.CAP")
        #expect(h.server.requests.last?.path == "/v1/account-cleanup-operations/server-original-operation")
        #expect(try h.secure.record().confirmation == body)
        #expect(throws: CleanupFailure.stale) { try h.confirmation(original) }
        await #expect(throws: CleanupFailure.stale) { try await h.client.read(read) }
        #expect(h.server.requests.filter { $0.operation == "confirmAccountCleanupV1" }.count == 1)
    }
    @Test func knownBlockedNeverClaimsRevocationAndHistoricalACKSurvivesCurrentGET() async throws {
        let h = try AccountHarness(); let original = try await h.prepare(); h.server.blocked = true
        try await h.client.perform(h.confirmation(original))
        guard case .progress(let blocked) = h.client.state else { Issue.record("blocked hidden"); return }
        #expect(blocked.status == .blocked && !blocked.businessRevoked && !h.server.committed)
        #expect(h.session.isCurrent(h.operation))
        #expect(try !h.client.requiresRestrictedProgress)
        guard case .progress(let current) = try await h.client.read(h.client.prepareOriginalRead()) else { Issue.record("no original GET"); return }
        #expect(current.status == .awaitingConfirmation)
        #expect(try h.client.historicalConfirmation?.status == .blocked)
        #expect(throws: CleanupFailure.unavailable) { try h.confirmation(original) }
        #expect(h.server.requests.filter { $0.operation == "confirmAccountCleanupV1" }.count == 1)
    }
    @Test func lostRegistrationACKHasNoInventedReadOrReplacementID() async throws {
        let h = try AccountHarness(); h.server.loseRegistrationACK = true
        let work = try h.client.prepareDeviceRegistration(stateRef: accountHash)
        await #expect(throws: CleanupFailure.exchangeUnknown) { try await h.client.perform(work) }
        h.client = try h.ordinary()
        guard case .registrationUnknown = h.client.state else { Issue.record("registration ACK loss was hidden"); return }
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareOriginalRead() }
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareDeviceRegistration(stateRef: accountHash) }
        #expect(h.server.requests.count == 1)
    }
    @Test func uncertainSecureWriteSendsNothingAndReopenKeepsUnknownIntent() throws {
        let h = try AccountHarness(); h.secure.failSave = true
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareDeviceRegistration(stateRef: accountHash) }
        #expect(h.server.requests.isEmpty)
        h.secure.failSave = false; h.client = try h.ordinary()
        guard case .registrationUnknown = h.client.state else { Issue.record("secure write uncertainty was dropped"); return }
    }
    @Test(arguments: ["scope", "sdk", "secure-record"])
    func finalCredentialCallbackCannotDispatchFromReplacedSource(change: String) async throws {
        let h = try AccountHarness(); let work = try h.client.prepareDeviceRegistration(stateRef: accountHash)
        h.credentialCallback = {
            switch change {
            case "scope": h.lifetime.invalidate()
            case "sdk": _ = try h.session.beginTrustedSDKSave()
            default: h.secure.value = try SessionMaterial(trustedSDKBytes: Data("changed slot".utf8))
            }
        }
        await #expect(throws: CleanupFailure.stale) { try await h.client.perform(work) }
        #expect(h.server.requests.isEmpty)
    }
    @Test func securePersistenceCallbackRetiresOriginalBeforeAnyPost() throws {
        let h = try AccountHarness(); h.secure.onSave = { h.lifetime.invalidate() }
        #expect(throws: CleanupFailure.stale) { try h.client.prepareDeviceRegistration(stateRef: accountHash) }
        #expect(h.server.requests.isEmpty)
    }
    @Test(arguments: ["registration", "preparation", "progress"])
    func lateNetworkResultCannotWriteAcrossCleanupLifetime(change: String) async throws {
        let h = try AccountHarness()
        let work: AccountCleanupWork
        if change == "registration" { work = try h.client.prepareDeviceRegistration(stateRef: accountHash) }
        else if change == "preparation" { try await h.register(); work = try h.client.prepareAccountDeletion() }
        else { _ = try await h.prepare(); work = try h.client.prepareOriginalRead() }
        let before = h.secure.bytes; h.server.callback = { h.lifetime.invalidate() }
        if change == "progress" { await #expect(throws: CleanupFailure.stale) { try await h.client.read(work) } }
        else { await #expect(throws: CleanupFailure.stale) { try await h.client.perform(work) } }
        #expect(h.secure.bytes == before)
        guard case .unavailable = h.client.state else { Issue.record("late result escaped retired lifetime"); return }
    }
    @Test func foreignAccountCannotRestoreOriginalSecureRecord() async throws {
        let h = try AccountHarness(); _ = try await h.prepare()
        let other = AccountCleanupLifetime(scope: AccountCleanupScope(environment: h.scope.environment, account: UUID(), generation: UUID()))
        #expect(throws: CleanupFailure.invalidResponse) {
            try AccountCleanupClient(endpoint: h.endpoint, lifetime: other, securePersistence: h.secure,
                interceptedTransport: AccountIntercept(server: h.server))
        }
    }
    @Test(arguments: ["true", "float", "negative", "wrong-op", "wrong-obligations", "false-complete"])
    func invalidProtectedProgressIsNotPublished(kind: String) async throws {
        let h = try AccountHarness(); let original = try await h.prepare(); try await h.client.perform(h.confirmation(original))
        h.server.transform = { operation, input in
            guard operation == "readOriginalAccountCleanupV1" else { return input }
            var value = input
            switch kind {
            case "true": value["revision"] = true
            case "float": value["revision"] = 1.0
            case "negative": value["revision"] = -1
            case "wrong-op": value["operation_id"] = "other-operation"
            case "wrong-obligations": value["obligations"] = ["backups":"complete", "other_devices":"all_erased", "external":"complete"]
            default: value["status"] = "complete"
            }
            return value
        }
        if kind == "float" {
            h.server.rawTransform = { operation, bytes in
                guard operation == "readOriginalAccountCleanupV1" else { return bytes }
                let text = String(decoding: bytes, as: UTF8.self).replacingOccurrences(of: "\"revision\":1", with: "\"revision\":1.0")
                #expect(text.contains("\"revision\":1.0"))
                return Data(text.utf8)
            }
        }
        let before = h.secure.bytes
        await #expect(throws: CleanupFailure.invalidResponse) { try await h.client.read(h.client.prepareOriginalRead()) }
        #expect(h.secure.bytes == before)
    }
    @Test func explicitConfirmationBindsExactOriginalOperationAndRegistry() async throws {
        let h = try AccountHarness(); let original = try await h.prepare()
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareConfirmation(operationID: "invented", registryDigest: original.registryDigest, confirmation: "DELETE_ACCOUNT") }
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareConfirmation(operationID: original.operationID, registryDigest: String(repeating: "b", count: 64), confirmation: "DELETE_ACCOUNT") }
        #expect(throws: CleanupFailure.unavailable) { try h.client.prepareConfirmation(operationID: original.operationID, registryDigest: original.registryDigest, confirmation: "yes") }
        #expect(try h.secure.record().confirmation == nil)
        #expect(h.server.requests.count == 2)
    }
    @Test func stagedUnsentConfirmationCanResumeOriginalBytesButUnknownCannot() async throws {
        let h = try AccountHarness(); let original = try await h.prepare()
        _ = try h.confirmation(original)
        let bytes = try h.secure.record().confirmation
        h.client = try h.ordinary()
        let resumed = try h.client.prepareStagedConfirmation(operationID: original.operationID, registryDigest: original.registryDigest, confirmation: "DELETE_ACCOUNT")
        h.server.loseConfirmationACK = true
        await #expect(throws: CleanupFailure.exchangeUnknown) { try await h.client.perform(resumed) }
        #expect(try h.secure.record().confirmation == bytes)
        #expect(throws: CleanupFailure.unavailable) {
            try h.client.prepareStagedConfirmation(operationID: original.operationID, registryDigest: original.registryDigest, confirmation: "DELETE_ACCOUNT")
        }
        #expect(h.server.requests.filter { $0.operation == "confirmAccountCleanupV1" }.map(\.body) == [bytes])
    }
    @Test func failedQuiescenceKeepsUnsentOriginalAndDoesNotDispatchOrExposeUnsafeError() async throws {
        let h = try AccountHarness(); let original = try await h.prepare()
        h.beforeConfirmation = { throw NSError(domain: "PRIVATE.SYNTHETIC.HEADER", code: 1) }
        await #expect(throws: CleanupFailure.unavailable) { try await h.client.perform(h.confirmation(original)) }
        #expect(try !h.client.requiresRestrictedProgress)
        #expect(try !h.secure.record().confirmationDispatched)
        #expect(h.server.requests.filter { $0.operation == "confirmAccountCleanupV1" }.isEmpty)
    }

}
