// Native component harness for #443. This is not the shipped CJProbeApp root or
// a device-cache hook. Every operation/capability comes from the actual local API.
import SwiftUI
import Observation
import Foundation
import CryptoKit
import CJAPI
import CJSession
import CJMessageHTTP
import CJCleanupClient
import HTTPTypes
import OpenAPIRuntime

private struct CleanupComponentFixture: Decodable {
    let endpoint: String
    let accounts: [String: String]
    let case_id: String
}
@MainActor @Observable private final class CleanupComponentModel {
    private struct Display {
        var status = "loading"
        var operation = ""
        var sdk = "none"
        var result = ""
    }
    @ObservationIgnored private var display = Display()
    private var signal = false
    @ObservationIgnored private var notifying = false
    @ObservationIgnored private var epoch = UUID()
    @ObservationIgnored private var fixture: CleanupComponentFixture?
    @ObservationIgnored private var client: AccountCleanupClient?
    @ObservationIgnored private var lifetime: AccountCleanupLifetime?
    @ObservationIgnored private var session: SessionLifecycle?
    @ObservationIgnored private var sessionOperation: SessionOperation?
    @ObservationIgnored private var selectedConfiguration: DevelopmentSessionConfiguration?
    @ObservationIgnored private var stateRef: String?
    @ObservationIgnored private var task: Task<Void, Never>?
    var status: String { _ = signal; return display.status }
    var operation: String { _ = signal; return display.operation }
    var sdk: String { _ = signal; return display.sdk }
    var result: String { _ = signal; return display.result }
    private func publish(_ expected: UUID, _ update: (inout Display) -> Void) {
        guard epoch == expected else { return }
        update(&display)
        guard !notifying else { return }
        notifying = true; signal.toggle(); notifying = false
    }
    func load() async {
        let stamp = epoch
        do {
            guard let raw = ProcessInfo.processInfo.environment["G2C_COMPONENT_CONTROL"],
                  let endpoint = URL(string: raw), endpoint.scheme == "http", endpoint.host == "127.0.0.1" else { throw CleanupFailure.unavailable }
            let (bytes, response) = try await URLSession.shared.data(from: endpoint.appendingPathComponent("fixture"))
            guard epoch == stamp, (response as? HTTPURLResponse)?.statusCode == 200 else { throw CleanupFailure.unavailable }
            fixture = try JSONDecoder().decode(CleanupComponentFixture.self, from: bytes)
            publish(stamp) { $0.status = "ready" }
        } catch { publish(stamp) { $0.status = "unavailable" } }
    }
    private func configuration(_ choice: String) throws -> DevelopmentSessionConfiguration {
        guard let fixture, let token = fixture.accounts[choice], let result = DevelopmentSessionConfiguration.read([
            "G2C_DEV_API_BASE_URL":fixture.endpoint,"G2C_DEV_TOKEN":token]) else { throw CleanupFailure.unavailable }
        return result
    }
    private func stores(_ configuration: DevelopmentSessionConfiguration) throws -> (KeychainSessionStore, KeychainSessionStore) {
        guard let applicationID = Bundle.main.bundleIdentifier else { throw CleanupFailure.unavailable }
        let sdk = try KeychainSessionScope(namespace: SessionNamespace(environment: configuration.environmentID,
            slot: "M3.Cleanup.Component.SDK"), applicationIdentifier: applicationID)
        let journal = try KeychainSessionScope(namespace: SessionNamespace(environment: configuration.environmentID,
            slot: "M3.Cleanup.Component." + configuration.accountID.uuidString), applicationIdentifier: applicationID)
        return (KeychainSessionStore(scope: sdk, protection: .whenUnlockedThisDeviceOnly),
            KeychainSessionStore(scope: journal, protection: .whenUnlockedThisDeviceOnly))
    }
    func signIn(_ choice: String) {
        epoch = UUID(); let stamp = epoch
        task?.cancel(); client?.invalidate(); lifetime?.invalidate()
        if let session { _ = session.clearWithSettlement() }
        client = nil; lifetime = nil; session = nil; sessionOperation = nil; stateRef = nil
        publish(stamp) { $0 = Display(); $0.status = "verifying" }
        task = Task {
            do {
                guard epoch == stamp else { return }
                let configuration = try configuration(choice)
                let endpoint = try MessageEndpoint(url: configuration.endpoint, maximumRequestBytes: 16384,
                    maximumResponseBytes: 65536, allowLoopbackHTTP: true)
                let transport = try NoRedirectTransport(requestTimeout: 5, resourceTimeout: 10)
                var request = HTTPRequest(method: .get, scheme: nil, authority: nil,
                    path: "/v1/message-receipts?message_id=component-verification-" + UUID().uuidString)
                request.headerFields[.authorization] = "Bearer " + configuration.token
                let (response, body) = try await transport.send(request, body: nil, baseURL: endpoint.url, operationID: Operations.queryMessageReceipt.id)
                guard epoch == stamp, response.status.code == 200, let body else { throw CleanupFailure.unavailable }
                let bytes = try await Data(collecting: body, upTo: 65536)
                let parsed = try JSONDecoder().decode(Components.Schemas.MessageReceiptQueryResponse.self, from: bytes)
                guard epoch == stamp, UUID(uuidString: parsed.request_id) != nil,
                      parsed.request_id == response.headerFields[HTTPField.Name("X-Request-ID")!] else { throw CleanupFailure.unavailable }
                let (sdk, journal) = try stores(configuration)
                let session = SessionLifecycle(persistence: sdk, restorePolicy: .userInitiatedOnly)
                let operation = try session.beginTrustedSDKSave()
                let material = try SessionMaterial(trustedSDKBytes: Data(configuration.token.utf8))
                try session.save(material, for: operation)
                let scope = AccountCleanupScope(environment: configuration.environmentID, account: configuration.accountID, generation: UUID())
                let lifetime = AccountCleanupLifetime(scope: scope)
                let client = try AccountCleanupClient(development: endpoint, lifetime: lifetime, securePersistence: journal,
                    session: session, sessionOperation: operation, credentials: { configuration.token },
                    beforeConfirmation: { _ in
                        // This component harness has no other business writer. The
                        // actual App's complete writer/device hook remains #27.
                        guard session.isCurrent(operation) else { throw CleanupFailure.stale }
                    }, requestTimeout: 10, resourceTimeout: 20)
                guard epoch == stamp else { client.invalidate(); lifetime.invalidate(); return }
                self.client = client; self.lifetime = lifetime; self.session = session; sessionOperation = operation
                selectedConfiguration = configuration
                let state = configuration.environmentID.uuidString + "|" + configuration.accountID.uuidString + "|" + scope.generation.uuidString + "|M3.Cleanup.Component.SDK|M3.Cleanup.Component." + configuration.accountID.uuidString
                stateRef = SHA256.hash(data: Data(state.utf8) + material.withBytes { $0 }).map { String(format: "%02x", $0) }.joined()
                refresh(stamp, status: "verified-" + choice)
            } catch { publish(stamp) { $0.status = "verification-denied" } }
        }
    }
    func restoreOriginalA() {
        epoch = UUID(); let stamp = epoch
        task?.cancel(); client?.invalidate(); lifetime?.invalidate()
        client = nil; lifetime = nil; session = nil; sessionOperation = nil; stateRef = nil
        do {
            let configuration = try configuration("A"), (_, journal) = try stores(configuration)
            let lifetime = AccountCleanupLifetime(scope: .init(environment: configuration.environmentID,
                account: configuration.accountID, generation: UUID()))
            let endpoint = try MessageEndpoint(url: configuration.endpoint, maximumRequestBytes: 16384,
                maximumResponseBytes: 65536, allowLoopbackHTTP: true)
            let client = try AccountCleanupClient(developmentRestrictedProgress: endpoint, lifetime: lifetime,
                securePersistence: journal, requestTimeout: 10, resourceTimeout: 20)
            self.client = client; self.lifetime = lifetime; selectedConfiguration = configuration
            refresh(stamp, status: "restored-original")
        } catch { publish(stamp) { $0 = Display(); $0.status = "restore-unavailable" } }
    }
    func prepare() {
        let stamp = epoch
        guard let client else { return }
        do {
            let first: AccountCleanupWork
            switch client.state {
            case .ready:
                guard let stateRef else { throw CleanupFailure.unavailable }
                first = try client.prepareDeviceRegistration(stateRef: stateRef)
            case .registered: first = try client.prepareAccountDeletion()
            default: throw CleanupFailure.unavailable
            }
            publish(stamp) { $0.status = "preparing" }
            task = Task {
                do {
                    try await client.perform(first)
                    guard epoch == stamp else { return }
                    if case .registered = client.state { try await client.perform(client.prepareAccountDeletion()) }
                    guard epoch == stamp else { return }; refresh(stamp)
                } catch { guard epoch == stamp else { return }; refresh(stamp, status: "preparation-unknown") }
            }
        } catch { refresh(stamp, status: "preparation-unavailable") }
    }
    func confirm() {
        let stamp = epoch
        guard let client, case .awaitingConfirmation(let original) = client.state else { return }
        do {
            let work = try client.prepareConfirmation(operationID: original.operationID,
                registryDigest: original.registryDigest, confirmation: "DELETE_ACCOUNT")
            let sdk = session, sdkOperation = sessionOperation
            task = Task {
                do { try await client.perform(work) }
                catch { /* exact original intent remains query-only; never retain unsafe error text */ }
                guard epoch == stamp else { return }
                do {
                    if try client.requiresRestrictedProgress {
                        guard let sdk, let sdkOperation, sdk.isCurrent(sdkOperation) else { throw CleanupFailure.stale }
                        try sdk.clear()
                    }
                    refresh(stamp)
                } catch { publish(stamp) { $0.status = "sdk-clear-unconfirmed" } }
            }
        } catch { refresh(stamp, status: "confirmation-unavailable") }
    }
    func readOriginal() {
        let stamp = epoch
        guard let client else { return }
        do {
            let work = try client.prepareOriginalRead()
            task = Task {
                do { _ = try await client.read(work); guard epoch == stamp else { return }; refresh(stamp) }
                catch { guard epoch == stamp else { return }; refresh(stamp, status: "read-unknown") }
            }
        } catch { refresh(stamp, status: "read-unavailable") }
    }
    private func refresh(_ stamp: UUID, status override: String? = nil) {
        guard epoch == stamp, let client else { return }
        var status = "unavailable", operation = "", result = ""
        switch client.state {
        case .ready: status = "verified"
        case .registered: status = "registered"
        case .registrationUnknown: status = "registration-unknown"
        case .preparationUnknown: status = "preparation-unknown"
        case .awaitingConfirmation(let p): status = "awaiting-confirmation"; operation = p.operationID
        case .confirmationStaged(let p): status = "confirmation-staged"; operation = p.operationID
        case .confirmationUnknown(let p): status = "confirmation-unknown"; operation = p.operationID
        case .progress(let p): status = p.status.rawValue; operation = p.operationID
            result = "business=" + (p.businessRevoked ? "revoked" : "unchanged") + ";online=" + (p.onlineStatus?.rawValue ?? "not-confirmed") + ";all-devices=false"
        case .unavailable: break
        }
        let sdk: String
        do {
            guard let selectedConfiguration else { throw CleanupFailure.unavailable }
            let (store, _) = try stores(selectedConfiguration)
            if try store.load() != nil { sdk = "stored" } else { sdk = "missing" }
        } catch SessionFailure.restorationBlocked { sdk = "blocked" }
        catch { sdk = "unknown" }
        publish(stamp) { $0.status = override ?? status; $0.operation = operation; $0.result = result; $0.sdk = sdk }
    }
}

@main private struct AccountCleanupComponentApp: App {
    @State private var model = CleanupComponentModel()
    var body: some Scene {
        WindowGroup {
            NavigationStack {
                Form {
                    Section("CLEANUP-API@1 native component / 原生组件") {
                        Text("This probe verifies the client only. Complete App/device cleanup is not established. / 仅验证客户端，不证明完整 App 或设备清理。")
                        Text(model.status).accessibilityIdentifier("cleanup.component.status")
                        Text(model.operation.isEmpty ? "No operation / 无操作" : model.operation).accessibilityIdentifier("cleanup.component.operation")
                        Text(model.sdk).accessibilityIdentifier("cleanup.component.sdk")
                        Text(model.result.isEmpty ? "No confirmed result / 无确认结果" : model.result).accessibilityIdentifier("cleanup.component.result")
                    }
                    Section("Explicit actions / 明确操作") {
                        Button("Verify A / 核验 A") { model.signIn("A") }.accessibilityIdentifier("cleanup.component.signin.A")
                        Button("Prepare original / 准备原操作") { model.prepare() }.accessibilityIdentifier("cleanup.component.prepare")
                        Button("Confirm deletion / 确认注销", role: .destructive) { model.confirm() }.accessibilityIdentifier("cleanup.component.confirm")
                        Button("Read original / 查询原操作") { model.readOriginal() }.accessibilityIdentifier("cleanup.component.read")
                        Button("Restore restricted A / 恢复 A 受限进度") { model.restoreOriginalA() }.accessibilityIdentifier("cleanup.component.restore")
                        Button("Verify B / 核验 B") { model.signIn("B") }.accessibilityIdentifier("cleanup.component.signin.B")
                    }
                }.navigationTitle("Cleanup component / 清理组件")
            }.task { await model.load() }
        }
    }
}
