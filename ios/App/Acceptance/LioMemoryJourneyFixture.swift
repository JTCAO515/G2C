// App source used only by the generated simulator acceptance project.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageKeys
@testable import CJMemoryClient
import CJSession
import CryptoKit
import HTTPTypes
import OpenAPIRuntime

@MainActor
private func journeyMemoryHost(shell: ShellState, backend: JourneyMemoryBackend, recovery: MessageRecovery,
                               scope: StorageScope, lease: Lease, environment: UUID, account: UUID,
                               lioChoices: LioMemoryActionsClient) throws -> TypedMemoryContainerHost {
    let binding = MemoryBinding(environment: environment, account: account, generation: UUID(), selection: UUID())
    let namespace = MessageKeyNamespace(environment: binding.environment, account: binding.account, purpose: .localMemoryPendingV1)
    let key = SymmetricKey(size: .bits256)
    let keyID = UUID()
    let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
        .appendingPathComponent("lio-memory-journey-" + UUID().uuidString)
    func directory(_ family: String) throws -> URL {
        let url = root.appendingPathComponent(family)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        return url
    }
    let manual = try MemoryPendingStore(directory: directory("manual"), maximumBytes: 100_000, maximumRecords: 20,
                                        namespace: namespace, keyID: keyID, key: { key })
    let management = try MemoryManagementPendingStore(directory: directory("management"), maximumBytes: 100_000, maximumRecords: 20,
                                                      namespace: namespace, keyID: keyID, key: { key })
    let typed = try TypedMemoryPendingStore(directory: directory("typed"), maximumBytes: 100_000, maximumRecords: 20,
                                           namespace: namespace, keyID: keyID, key: { key })
    let erasureStore = try MemoryErasurePendingStore(directory: directory("erasure"), maximumBytes: 100_000, maximumRecords: 20,
                                                    namespace: namespace, keyID: keyID, key: { key })
    let url = URL(string: "https://synthetic.invalid")!
    let memoryEndpoint = try MemoryEndpoint(url: url, maximumRequestBytes: 32_768, maximumResponseBytes: 100_000)
    let messageEndpoint = try MessageEndpoint(url: url, maximumRequestBytes: 32_768, maximumResponseBytes: 100_000)
    let reader = TypedMemoryClient(endpoint: memoryEndpoint, credentials: { _ in "SYNTHETIC" },
                                   currentBinding: { binding }, pendingStore: typed, interceptedTransport: backend)
    let message = MessageHTTPClient(recovery: recovery, scope: scope, endpoint: messageEndpoint,
                                    credentials: JourneyCredentials(), interceptedTestTransport: backend)
    let travel = try TravelSelectionModel(ids: [], client: message, lease: lease, isCurrent: { true })
    let session = SessionLifecycle(persistence: JourneySession(), restorePolicy: .userInitiatedOnly)
    let operation = try session.beginTrustedSDKSave()
    try session.save(SessionMaterial(trustedSDKBytes: Data("synthetic-memory-journey".utf8)), for: operation)
    let erasure = MemoryErasureClient(endpoint: memoryEndpoint, credentials: { _ in "SYNTHETIC" },
                                      currentBinding: { binding }, session: session, sessionOperation: operation,
                                      pendingStore: erasureStore, interceptedTransport: backend)
    let cleanup = MemoryItemLocalCleanup(manual: manual, management: management, typed: typed,
                                         clearAdditionalOriginals: { binding, itemID in
        try lioChoices.clearErasedItem(itemID, environment: binding.environment, account: binding.account)
        guard try recovery.localProjection(scope: scope, lease: lease).actions.allSatisfy({
            !$0.messageID.hasPrefix("lio-memory-")
        }) else { throw RecoveryError.persistenceUnknown }
    })
    return try TypedMemoryContainerHost(shell: shell, client: reader, binding: binding, pageSize: 20,
                                        options: [], travel: travel, currentBinding: { binding }, erasureClient: erasure,
                                        itemCleanup: cleanup)
}

@MainActor
private final class JourneySession: SessionPersistence {
    private var material: SessionMaterial?
    func load() throws -> SessionMaterial? { material }
    func save(_ material: SessionMaterial) throws { self.material = material }
    func clearAndBlock() throws { material = nil }
}

@MainActor
private final class JourneyCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "SYNTHETIC" }
}

private actor JourneyMemoryBackend: ClientTransport {
    private let trace = "00000000-0000-4000-8000-000000000001"
    private let selectedID = "quiet-hotel"
    private let otherID = "aisle-seat"
    private let language: LioLanguage
    private var preference: String?
    private let gridPreview: Bool
    private var version = 1
    private var editReceipt: [String: Any]?
    private var deletion: MemoryErasureAction?

    init(language: LioLanguage) {
        self.language = language
        gridPreview = ProcessInfo.processInfo.arguments.contains("--lio-memory-grid-acceptance")
        if gridPreview { preference = language.text("You like quiet hotels", "你喜欢安静的酒店") }
    }

    func remember() {
        preference = language.text("You like quiet hotels", "你喜欢安静的酒店")
    }

    func rememberedPreference() -> String? { preference }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard request.headerFields[.authorization] == "Bearer SYNTHETIC", let path = request.path else {
            throw MemoryFailure.invalidInput
        }
        let arguments = URLComponents(string: path)?.queryItems ?? []
        func parameter(_ name: String) -> String? { arguments.first { $0.name == name }?.value }
        let fields: [String: Any]
        var responseVersion = "MEMORY-result.2"
        switch operationID {
        case "listTypedMemories":
            try Task.checkCancellation()
            let ids = (gridPreview ? [otherID, selectedID, "city-walks", "food-interest", "museum-stops", "train-seat"]
                                   : [otherID, selectedID]).sorted().filter { id in
                parameter("after").map { $0.utf8.lexicographicallyPrecedes(id.utf8) } ?? true
            }
            fields = ["items": ids.compactMap(item)]
        case "getTypedMemoryItem":
            fields = ["item": parameter("item_id").flatMap(item).map { $0 as Any } ?? NSNull()]
        case "applyTypedMemoryManagement":
            guard let body, preference != nil, editReceipt == nil else { throw MemoryFailure.invalidInput }
            let raw = try await Data(collecting: body, upTo: 32_768)
            guard let command = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
                  command["operation"] as? String == "edit", command["item_id"] as? String == selectedID,
                  command["expected_version"] as? Int == version, command["expected_source_version"] as? Int == version,
                  let action = command["action_id"] as? String, let updated = command["text"] as? String else {
                throw MemoryFailure.invalidInput
            }
            preference = updated
            version += 1
            editReceipt = ["action_id": action, "item_id": selectedID, "version": version, "status": "active", "input_sha256": digest(raw)]
            throw URLError(.networkConnectionLost)
        case "getTypedMemoryManagementReceipt":
            guard let receipt = editReceipt, parameter("action_id") == receipt["action_id"] as? String else {
                throw MemoryFailure.invalidInput
            }
            fields = ["receipt": receipt]
        case "eraseMemoryV1":
            guard let body, preference != nil, deletion == nil else { throw MemoryFailure.invalidInput }
            let original = try MemoryErasureAction(originalUTF8: await Data(collecting: body, upTo: 32_768))
            guard original.itemID == selectedID, original.expectedVersion == version else { throw MemoryFailure.invalidInput }
            preference = nil
            deletion = original
            throw URLError(.networkConnectionLost)
        case "readMemoryErasureProgressV1":
            guard let original = deletion, parameter("action_id") == original.actionID else { throw MemoryFailure.invalidInput }
            responseVersion = "MEMORY-ERASURE-response@1"
            fields = ["result": [
                "action_id": original.actionID, "operation_id": "memory-erasure-v1:" + String(repeating: "a", count: 64),
                "item_version": original.expectedVersion + 1, "scope_epoch": 5, "stop_use": "stopped", "online_status": "complete",
                "steps": MemoryErasureTarget.allCases.map { ["target": $0.rawValue, "state": "confirmed"] }
            ]]
        default:
            throw MemoryFailure.invalidInput
        }
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[.cacheControl] = "no-store"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        let envelope = fields.merging(["version": responseVersion, "request_id": trace]) { _, updated in updated }
        return (response, HTTPBody(try JSONSerialization.data(withJSONObject: envelope)))
    }

    private func item(_ id: String) -> [String: Any]? {
        let text: String
        let itemVersion: Int
        if id == selectedID, let preference {
            text = preference
            itemVersion = version
        } else if id == otherID {
            text = language.text("You prefer an aisle seat", "你偏好靠过道的座位")
            itemVersion = 1
        } else if gridPreview && ["city-walks", "food-interest", "museum-stops", "train-seat"].contains(id) {
            text = switch id {
            case "city-walks": language.text("You enjoy long walks through quiet neighbourhoods, with time to pause for tea and explore small local shops at your own pace.", "你喜欢在安静的街区慢慢散步，随时停下来喝茶，在当地小店里逛逛，不希望把一天安排得太满。")
            case "food-interest": language.text("You enjoy local food", "你喜欢尝试当地美食")
            case "museum-stops": language.text("You enjoy art museums", "你喜欢参观美术馆")
            default: language.text("You prefer a window seat on trains", "你喜欢火车上靠窗的座位")
            }
            itemVersion = 1
        } else {
            return nil
        }
        return ["version": itemVersion, "status": gridPreview && id == "city-walks" ? "disabled" : "active", "recorded_at": "2026-11-03T00:00:00Z", "command": [
            "operation_id": "remember-\(id)", "item_id": id, "subject": "self", "slot": id,
            "text": text, "occurred_at": "2026-11-03T00:00:00Z", "source_id": "source-\(id)-\(itemVersion)",
            "source_version": itemVersion, "kind": "preference", "extent": "long_term", "context": NSNull()
        ]]
    }
}
#endif
