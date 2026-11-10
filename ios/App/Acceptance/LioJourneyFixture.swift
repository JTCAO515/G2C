// App source used only by the generated simulator acceptance project.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageClient
@testable import CJMessageHTTP

private struct LioJourneyFixture: View {
    let shell: ShellState
    @State private var journey: Result<JourneyClients, any Error>?

    var body: some View {
        Group {
            switch journey {
            case .success(let clients):
                LioHome(language: shell.language.lio, service: clients.conversation, isDemo: false,
                        tripHistory: clients.trips, memoryActions: clients.memory,
                        savedMemory: AnyView(LioSavedMemoryView(host: clients.savedMemory, language: shell.language))) {
                    LioLanguagePicker(shell: shell)
                }
            case .failure(let error):
                Text("Synthetic journey setup failed: \(String(reflecting: error))")
            case nil:
                ProgressView()
            }
        }
        .task {
            guard journey == nil else { return }
            journey = Result { try JourneyClients(shell: shell) }
        }
    }
}

@MainActor
private struct JourneyClients {
    let conversation: LioService
    let trips: LioTripHistoryClient
    let memory: LioMemoryActionsClient
    let savedMemory: TypedMemoryContainerHost

    init(shell: ShellState) throws {
        let language = shell.language.lio
        let backend = JourneyMemoryBackend(language: language)
        let service = JourneyScenario(language: language, memoryBackend: backend)
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let recovery = MessageRecovery(storage: JourneyStorage())
        let lease = try recovery.activate(scope)
        conversation = LioService.timeline(send: { try await service.submit($0) }, read: { id, _ in
            try await service.timeline(id)
        }, pollInterval: .milliseconds(300))
        trips = LioTripHistoryClient(recovery: recovery, scope: scope, lease: lease,
            readHistory: { _ in try await service.history() },
            submit: { try await service.submitUndo($0) },
            readReceipt: { try await service.readUndo($0) })
        memory = LioMemoryActionsClient(recovery: recovery, scope: scope, lease: lease,
            submit: { try await service.submitMemory($0) },
            readReceipt: { try await service.readMemory($0) })
        savedMemory = try journeyMemoryHost(shell: shell, backend: backend, recovery: recovery, scope: scope, lease: lease)
    }
}

@MainActor
private final class JourneyStorage: SecureMessageStorage {
    private var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}

private actor JourneyScenario {
    private let language: LioLanguage
    private let memoryBackend: JourneyMemoryBackend
    private let conversationID = "lio-dialogue-0123456789abcdef0123456789abcdef"
    private let clock = ContinuousClock()
    private var rows: [[String: Any]] = []
    private var metroStarted: ContinuousClock.Instant?
    private var plans: [Bool] = []
    private var undoBytes: Data?
    private var memoryBytes: Data?

    init(language: LioLanguage, memoryBackend: JourneyMemoryBackend) {
        self.language = language
        self.memoryBackend = memoryBackend
    }

    func submit(_ request: LioTimelineWire.Send) async throws -> LioService.SendResult {
        let value = try JSONDecoder().decode([String: String].self, from: request.originalUTF8)
        guard let question = value["text"] else { throw MessageHTTPFailure.invalidConfiguration }
        let text = question.lowercased()
        var row: [String: Any] = ["message_id": request.messageID, "text": question, "status": "completed",
                                  "answer": "", "sources": []]
        if text.contains("metro") || text.contains("地铁") {
            metroStarted = clock.now
            row["answer"] = language.text("Follow the signs for your metro line.", "跟着地铁线路指示牌走。")
            row["sources"] = [["title": language.text("Sample metro guide", "地铁演示指南")]]
        } else if text.contains("plan") || text.contains("规划") {
            row["answer"] = language.text("Would you like a slower pace?", "你想慢慢逛吗？")
        } else if text.contains("slow") || text.contains("慢") {
            plans.append(false)
            row["answer"] = language.text("I saved your Beijing trip.", "北京行程已保存。")
            row["trip"] = trip(edited: false)
        } else if text.contains("second day") || text.contains("第二天") {
            guard plans.last == false else { throw MessageHTTPFailure.invalidConfiguration }
            plans.append(true)
            row["answer"] = language.text("I changed the second afternoon.", "第二天下午已经改好了。")
            row["trip"] = trip(edited: true)
        } else if text.contains("prefer") || text.contains("喜欢") {
            row["answer"] = language.text("Quiet hotels sound good.", "安静的酒店很不错。")
            if await memoryBackend.rememberedPreference() == nil {
                row["memory"] = ["tags": [
                    ["id": "quiet-hotel", "kind": "preference", "target": "quiet_hotel",
                     "text": language.text("You like quiet hotels", "你喜欢安静的酒店")],
                    ["id": "technical-tag", "kind": "preference", "target": "technical_tag",
                     "text": language.text("Review the request ID", "核实这次操作")]
                ]]
            }
        } else {
            let preference = await memoryBackend.rememberedPreference()
            row["answer"] = preference.map { $0 + language.text(".", "。") }
                ?? language.text("Tell me what kind of hotel you like.", "你喜欢什么样的酒店？")
        }
        rows.append(row)
        return .accepted(conversationID: conversationID)
    }

    func timeline(_ expectedID: String?) throws -> LioTimelineWire.Page {
        var messages = rows
        if let started = metroStarted, messages.count == 1 {
            let elapsed = started.duration(to: clock.now)
            if elapsed < .seconds(3) {
                messages[0]["status"] = "answering"
                messages[0]["activity"] = "checking_travel_information"
                messages[0]["answer"] = ""
                messages[0]["sources"] = []
            } else if elapsed < .seconds(4) {
                messages[0]["status"] = "answering"
                messages[0]["answer"] = language.text("Follow the signs", "跟着指示牌")
                messages[0]["sources"] = []
            }
        }
        return try LioTimelineWire.decodePage(json([
            "version": "LIO-timeline.1", "conversation_id": conversationID, "messages": messages,
            "next_before": NSNull()
        ]), for: expectedID)
    }

    func history() throws -> LioTripHistoryWire.Page {
        try LioTripHistoryWire.decodePage(json([
            "version": "LIO-trip-history.1",
            "current": plans.last.map { trip(edited: $0) as Any } ?? NSNull(),
            "history": plans.dropLast().reversed().map { trip(edited: $0) },
            "undo_target": plans.count > 1 ? "trip_\(plans.count)" as Any : NSNull(),
            "next_before": NSNull()
        ]))
    }

    func submitUndo(_ action: LioTripHistoryWire.Undo) throws -> LioTripHistoryClient.SubmissionResult {
        guard undoBytes == nil, action.target == "trip_\(plans.count)", let previous = plans.dropLast().last else {
            throw MessageHTTPFailure.invalidConfiguration
        }
        plans.append(previous)
        undoBytes = action.originalUTF8
        throw URLError(.networkConnectionLost)
    }

    func readUndo(_ action: LioTripHistoryWire.Undo) throws -> Data? {
        guard action.originalUTF8 == undoBytes else { return nil }
        return try json(["version": "LIO-trip-undo-receipt.1", "action_id": action.actionID, "committed": true])
    }

    func submitMemory(_ action: LioMemoryWire.Action) async throws -> LioMemoryActionsClient.SubmissionResult {
        guard action.choice == .remember, memoryBytes == nil else { throw MessageHTTPFailure.invalidConfiguration }
        memoryBytes = action.originalUTF8
        await memoryBackend.remember()
        for index in rows.indices { rows[index].removeValue(forKey: "memory") }
        throw URLError(.networkConnectionLost)
    }

    func readMemory(_ action: LioMemoryWire.Action) throws -> Data {
        guard action.originalUTF8 == memoryBytes else { throw MessageHTTPFailure.invalidConfiguration }
        return try json(["version": "LIO-memory-action-receipt.1", "action_id": action.actionID, "status": "remembered"])
    }

    private func trip(edited: Bool) -> [String: Any] {
        [
            "trip_id": "trip:beijing", "title": language.text("Beijing trip", "北京行程"),
            "days": [
                ["date": "2026-11-10", "items": [
                    ["item_id": "hotel", "label": language.text("Hotel check-in", "酒店入住"), "start_time": "15:00", "fixed": true]
                ]],
                ["date": "2026-11-11", "items": [
                    ["item_id": "afternoon", "label": edited ? language.text("Art museum", "美术馆") : language.text("Park walk", "公园散步"),
                     "start_time": "14:00", "fixed": false]
                ]]
            ]
        ]
    }

    private func json(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
}
#endif
