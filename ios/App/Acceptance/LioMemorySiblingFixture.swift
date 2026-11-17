// Generated local acceptance App only. No network or real account material.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private struct LioMemorySiblingFixture: View {
    let shell: ShellState
    @State private var clients: Result<SiblingMemoryClients, any Error>?
    @State private var inspected = "not inspected"

    var body: some View {
        VStack(spacing: 0) {
            switch clients {
            case .success(let value):
                LioHome(language: shell.language.lio, service: value.service, isDemo: false,
                        memoryActions: value.choices,
                        savedMemory: AnyView(LioSavedMemoryView(host: value.saved, language: shell.language))) {
                    LioMenuSettings(shell: shell)
                }
                HStack {
                    Button { Task { inspected = await value.backend.snapshot() } } label: {
                        Text("Inspect choices").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                    }
                    .accessibilityIdentifier("fixture.siblings.inspect")
                    Text(inspected).accessibilityIdentifier("fixture.siblings.state")
                }
                .font(.caption).foregroundStyle(LioTheme.ink).tint(LioTheme.vermilion)
                .padding(4).background(LioTheme.paper)
            case .failure:
                Text("Synthetic sibling fixture setup failed")
            case nil:
                ProgressView()
            }
        }
        .task {
            guard clients == nil else { return }
            clients = Result { try SiblingMemoryClients(shell: shell) }
        }
    }
}

@MainActor private struct SiblingMemoryClients {
    let service: LioService
    let choices: LioMemoryActionsClient
    let saved: TypedMemoryContainerHost
    let backend: SiblingMemoryBackend

    init(shell: ShellState) throws {
        let backend = SiblingMemoryBackend(language: shell.language.lio)
        self.backend = backend
        let environment = UUID(), account = UUID()
        let scope = try StorageScope(environment: environment.uuidString, account: account.uuidString)
        let recovery = MessageRecovery(storage: JourneyStorage())
        let lease = try recovery.activate(scope)
        service = LioService.timeline(send: { _ in throw MessageHTTPFailure.invalidConfiguration },
                                     read: { _, _ in try await backend.timeline() })
        let choices = LioMemoryActionsClient(recovery: recovery, scope: scope, lease: lease,
            submit: { try await backend.choose($0) }, readReceipt: { try await backend.receipt($0) })
        self.choices = choices
        saved = try journeyMemoryHost(shell: shell, backend: backend, recovery: recovery, scope: scope,
            lease: lease, environment: environment, account: account, lioChoices: choices)
    }
}

private actor SiblingMemoryBackend: ClientTransport {
    private let language: LioLanguage
    private let ids = ["luxury-hotel", "museum"]
    private let trace = "00000000-0000-4000-8000-000000000001"
    private var saved: [String] = []
    private var actions: [String: Data] = [:]
    private var epoch = 1
    private var stale = 0
    private var refreshed = false

    init(language: LioLanguage) { self.language = language }

    private func text(_ id: String) -> String {
        id == "luxury-hotel" ? language.text("You prefer luxury hotels.", "你偏好豪华酒店。")
            : language.text("You enjoy museums.", "你喜欢参观博物馆。")
    }
    private func target(_ id: String) throws -> String {
        try json(["candidate_id": id, "text": text(id), "epoch": epoch]).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
    func timeline() throws -> LioTimelineWire.Page {
        if !saved.isEmpty { refreshed = true }
        let tags = try ids.filter { !saved.contains($0) }.map {
            ["id": $0, "text": text($0), "kind": "preference", "target": try target($0)]
        }
        return try LioTimelineWire.decodePage(json([
            "version": "LIO-timeline.1", "conversation_id": "lio-dialogue-0123456789abcdef0123456789abcdef",
            "messages": [["message_id": "synthetic-sibling-question", "text": language.text("I prefer luxury hotels and museums.", "我喜欢豪华酒店和博物馆。"),
                          "answer": language.text("Two travel preferences to consider.", "这里有两条旅行偏好。"), "status": "completed",
                          "sources": [], "memory": ["tags": tags]]], "next_before": NSNull()
        ]), for: nil)
    }
    func choose(_ action: LioMemoryWire.Action) throws -> LioMemoryActionsClient.SubmissionResult {
        struct Request: Decodable { let target: String }
        let request = try JSONDecoder().decode(Request.self, from: action.originalUTF8)
        guard action.choice == .remember, actions[action.actionID] == nil else { throw MessageHTTPFailure.invalidConfiguration }
        var selected: String?
        for id in ids where !saved.contains(id) {
            if try request.target == target(id) { selected = id }
        }
        guard let selected else {
            stale += 1
            return .conflict(try json(["error": "stale_synthetic_target"]))
        }
        saved.append(selected)
        actions[action.actionID] = action.originalUTF8
        epoch += 1
        return .receipt(try receipt(action))
    }
    func receipt(_ action: LioMemoryWire.Action) throws -> Data {
        guard actions[action.actionID] == action.originalUTF8 else { throw MessageHTTPFailure.invalidConfiguration }
        return try json(["version": "LIO-memory-action-receipt.1", "action_id": action.actionID, "status": "remembered"])
    }
    func snapshot() -> String { "saved=\(saved.count)|actions=\(actions.count)|stale=\(stale)|refreshed=\(refreshed)" }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        guard request.headerFields[.authorization] == "Bearer SYNTHETIC", body == nil else { throw MemoryFailure.invalidInput }
        let version: String
        let fields: [String: Any]
        switch operationID {
        case "listTitledMemories":
            version = "MEMORY-result.3"
            let after = URLComponents(string: request.path ?? "")?.queryItems?.first { $0.name == "after" }?.value
            fields = ["items": saved.sorted().filter { id in
                after.map { $0.utf8.lexicographicallyPrecedes(id.utf8) } ?? true
            }.map(item)]
        case "getTitledMemoryItem":
            version = "MEMORY-result.3"
            let id = URLComponents(string: request.path ?? "")?.queryItems?.first { $0.name == "item_id" }?.value
            fields = ["item": id.flatMap { saved.contains($0) ? item($0) : nil }.map { $0 as Any } ?? NSNull()]
        default: throw MemoryFailure.invalidInput
        }
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[.cacheControl] = "no-store"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        return (response, HTTPBody(try json(fields.merging(["version": version, "request_id": trace]) { _, new in new })))
    }
    private func item(_ id: String) -> [String: Any] {
        ["version": 1, "status": "active", "recorded_at": "2026-11-17T00:00:00Z",
         "title": id == "luxury-hotel" ? language.text("Luxury hotels", "豪华酒店") : language.text("Museums", "博物馆"),
         "command": ["operation_id": "remember-\(id)", "item_id": id, "subject": "self", "slot": id,
                     "text": text(id), "occurred_at": "2026-11-17T00:00:00Z", "source_id": "source-\(id)-1",
                     "source_version": 1, "kind": "preference", "extent": "long_term", "context": NSNull()]]
    }
    private func json(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) }
}
#endif
