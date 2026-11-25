// Generated actual-App simulator acceptance only; no external requests or credentials.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import HTTPTypes
import CryptoKit
import OpenAPIRuntime
import CJMessageClient
@testable import CJMessageHTTP

private struct LioExplorationHomeFixture: View {
    let shell: ShellState
    @State private var host: ExplorationHomeHost?
    @State private var failed = false

    var body: some View {
        Group {
            if let host {
                LioHome(language: shell.language.lio, service: host.service, isDemo: false) {
                    ExplorationHomeCounts(wire: host.wire, timingsSince: host.timingsSince)
                }
            } else if failed {
                Text("Sample unavailable").accessibilityIdentifier("fixture.failed")
            } else {
                ProgressView().task {
                    do { host = try ExplorationHomeHost() }
                    catch { failed = true }
                }
            }
        }
    }
}

private struct ExplorationHomeCounts: View {
    let wire: ExplorationHomeWire
    let timingsSince: TimeInterval
    @State private var count = ""
    @State private var last = ""
    @State private var lastID = ""
    @State private var finishedTimings = 0
    @State private var timingComplete = false
    @State private var copiedDigest = ""
    var body: some View {
        VStack {
            Text(count).accessibilityValue(lastID).accessibilityIdentifier("fixture.send-count")
            Text(last).accessibilityIdentifier("fixture.last-text")
            Text(String(finishedTimings)).accessibilityValue(timingComplete ? "complete" : "incomplete")
                .accessibilityIdentifier("fixture.finished-timings")
            Button {
                if let copied = UIPasteboard.general.string {
                    copiedDigest = SHA256.hash(data: Data(copied.utf8)).map { String(format: "%02x", $0) }.joined()
                } else { copiedDigest = "unavailable" }
            } label: {
                Text("Inspect copied text").frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            }
            .accessibilityIdentifier("fixture.clipboard.probe")
            Text("Copy result").accessibilityValue(copiedDigest).accessibilityIdentifier("fixture.clipboard.digest")
        }.task {
            (count, last, lastID) = await wire.counts()
            let entries = LioTimingLog().entries().filter { $0.sentAt >= timingsSince }
            finishedTimings = entries.count
            let requiresIndicator = ProcessInfo.processInfo.arguments.contains("--lio-home-progress-acceptance")
            timingComplete = entries.allSatisfy { entry in
                guard let first = entry.firstTextMs, let finished = entry.finishedMs else { return false }
                return first >= 0 && first <= finished && (!requiresIndicator || entry.indicatorMs != nil)
            }
        }
    }
}

@MainActor private final class ExplorationHomeStorage: SecureMessageStorage {
    private var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ value: Snapshot, scope: StorageScope) throws { snapshot = value }
}

@MainActor private final class ExplorationHomeCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic-only" }
}

@MainActor private final class ExplorationHomeHost {
    let timingsSince = Date().timeIntervalSince1970
    let wire: ExplorationHomeWire
    let service: LioService
    init() throws {
        let arguments = ProcessInfo.processInfo.arguments
        let version = arguments.contains("--lio-home-legacy1-acceptance") ? 1
            : arguments.contains("--lio-home-legacy2-acceptance") ? 2 : 4
        let wire = ExplorationHomeWire(showsProgress: arguments.contains("--lio-home-progress-acceptance"), version: version,
                                       plans: arguments.contains("--lio-home-plan-acceptance"))
        self.wire = wire
        let recovery = MessageRecovery(storage: ExplorationHomeStorage())
        let scope = try StorageScope(environment: "synthetic", account: UUID().uuidString)
        let lease = try recovery.activate(scope)
        let endpoint = try MessageEndpoint(url: URL(string: "https://synthetic.invalid")!,
                                          maximumRequestBytes: 16384, maximumResponseBytes: 4500000)
        let transport = try NoRedirectTransport(interceptedTransport: wire, messageEndpoint: endpoint,
                                               validateMessage: {}, lio: true)
        let client = LioTimelineHTTP(scope: scope, lease: lease, credentials: ExplorationHomeCredentials(),
                                     transport: transport, firstChatRecovery: recovery)
        switch version {
        case 1: service = .signedTimeline(client)
        case 2: service = .signedConversation(client, destination: .defaultChat) { _ in }
        default: service = .signedExplorationConversation(client, destination: .defaultChat) { _ in }
        }
    }
}

private actor ExplorationHomeWire: ClientTransport {
    private static let conversation = "lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    private let showsProgress: Bool
    private let version: Int
    /// #1453: the second reply carries a LIO-trip-card.3 summary.
    private let plans: Bool
    private var progressReads = 0
    private var chinese = false
    private var messages: [[String: Any]] = []
    private var sent: [String] = []
    init(showsProgress: Bool, version: Int, plans: Bool = false) {
        self.showsProgress = showsProgress; self.version = version; self.plans = plans
    }
    func counts() -> (String, String, String) {
        ("\(sent.count)", sent.last ?? "", messages.last?["message_id"] as? String ?? "")
    }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL,
              operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let path = request.path!, null = NSNull()
        let output: [String: Any]
        if request.method == .post, path == "/v\(version)/lio/messages" {
            let input = try JSONSerialization.jsonObject(with: await Data(collecting: body!, upTo: 16384)) as! [String: Any]
            let inputVersion = input["version"] as? String
            let expectedVersion = "LIO-message.\(version)"
            precondition(inputVersion == expectedVersion)
            let text = input["text"] as! String
            chinese = input["locale"] as? String == "zh"
            sent.append(text)
            messages.append(message(input, chinese: chinese, first: sent.count == 1))
            output = ["version": "LIO-message-receipt.\(version)", "message_id": input["message_id"]!,
                      "conversation_id": Self.conversation]
        } else if request.method == .get, path.hasPrefix("/v\(version)/lio/timeline") {
            var visible = messages
            if showsProgress, !messages.isEmpty {
                progressReads += 1
                if progressReads < 9 {
                    var waiting = messages[0]
                    waiting["answer"] = ""
                    waiting["status"] = "answering"
                    for field in ["segments", "question_groups", "profile", "notices", "exits"] { waiting[field] = [] }
                    waiting["progress"] = progressReads < 5
                        ? ["kind": "waiting", "text": chinese ? "正在比较酒店的位置" : "Comparing hotel locations"]
                        : ["kind": "planning_started", "text": chinese ? "开始安排三天行程" : "Starting your three-day plan", "duration_days": 3]
                    visible = [waiting]
                }
            }
            output = ["version": "LIO-timeline.\(version)", "conversation_id": Self.conversation,
                      "messages": visible, "next_before": null]
        } else { throw URLError(.unsupportedURL) }
        let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[HTTPField.Name("Cache-Control")!] = "no-store"
        return (response, HTTPBody(data))
    }

    private func message(_ input: [String: Any], chinese: Bool, first: Bool) -> [String: Any] {
        let null = NSNull()
        func text(_ en: String, _ zh: String) -> String { chinese ? zh : en }
        if version != 4 {
            let answer = text("## Earlier reply\n\nYou can start with an **outline**.\n\nDates can stay open.",
                              "## 之前的回答\n\n可以先聊一个**大致安排**。\n\n日期可以之后再定。")
            return ["message_id": input["message_id"]!, "text": input["text"]!,
                    "answer": answer, "status": "completed", "failure": null,
                    "activity": null, "sources": [], "trip": null, "memory": null]
        }
        let response = first ? text("We can start with an outline.", "可以先聊一个大致安排。")
            : text("I’ll use your choices for the next step.", "接下来我会按你的选择安排。")
        let second = text("Dates can stay open for now.", "日期可以之后再定。")
        let options = [
            ["id": "interests.history", "display_text": text("History", "历史"), "send_text": text("Interests: History", "兴趣：历史")],
            ["id": "interests.food", "display_text": text("Food", "美食"), "send_text": text("Interests: Food", "兴趣：美食")],
            ["id": "interests.nature", "display_text": text("Nature", "自然"), "send_text": text("Interests: Nature", "兴趣：自然")]
        ]
        var answer = [response, second]
        if first {
            answer.append(text("What interests you?", "更想体验什么？") + "\n" + options.map { $0["display_text"]! }.joined(separator: " / "))
            answer.append(text("Bring a raincoat.", "带一件雨衣。"))
        }
        answer.append(text("Make a plan now", "直接出方案"))
        return ["message_id": input["message_id"]!, "text": input["text"]!,
                "answer": answer.joined(separator: "\n\n"), "status": "completed", "failure": null,
                "activity": null, "sources": [], "trip": plans && !first ? trip(chinese: chinese) as Any : null, "memory": null,
                "segments": [["purpose": "response", "text": response], ["purpose": "summary", "text": second]],
                "question_groups": first ? [["factor_key": "interests", "question": text("What interests you?", "更想体验什么？"),
                                              "multiple": true, "options": options]] : [],
                "profile": [["factor_key": "pace", "display_text": text("An easy pace", "慢慢逛"), "state": "inferred"]],
                "notices": first ? [["id": "weather.1", "type": "weather", "severity": "info", "item_ids": [],
                                     "text": text("Bring a raincoat.", "带一件雨衣。"),
                                     "source": ["title": text("Weather guidance", "天气提示"), "url": "https://example.org/guide",
                                                "observed_at": "2026-11-14T00:00:00Z"]]] : [],
                "exits": [["id": "plan_now", "display_text": text("Make a plan now", "直接出方案"),
                           "send_text": text("Make a plan now", "直接出方案")]], "progress": null]
    }

    private func trip(chinese: Bool) -> [String: Any] {
        func item(_ id: String, _ en: String, _ zh: String, _ start: String?, _ end: String?) -> [String: Any] {
            ["item_id": id, "label": chinese ? zh : en, "start_time": start ?? NSNull(), "end_time": end ?? NSNull(), "fixed": false]
        }
        // Matches the contract's undated example: no day dates, and date checks are not run.
        let unknown: [String: Any] = ["state": "not_checked", "day_indices": [1, 2, 3], "item_ids": [],
                                      "reason": "date_not_set", "evidence_refs": []]
        return ["version": "LIO-trip-card.3", "trip_id": "synthetic-plan-trip", "trip_version": 1,
                "content_version": "structured.4", "content_sha256": String(repeating: "5", count: 64),
                "title": chinese ? "北京三日行" : "Three days in Beijing",
                "calendar": ["state": "undated"],
                "days": [
                    ["day_index": 1, "items": [
                        item("d1a", "Tiananmen Square", "天安门广场", "08:30", "09:30"),
                        item("d1b", "Palace Museum", "故宫博物院", "10:00", "13:00"),
                        item("d1c", "Jingshan Park", "景山公园", "15:00", "16:30")]],
                    ["day_index": 2, "items": [
                        item("d2a", "Mutianyu Great Wall", "慕田峪长城", "09:00", "14:00")]],
                    ["day_index": 3, "items": []]
                ],
                "date_checks": [unknown.merging(["kind": "weather"]) { $1 }, unknown.merging(["kind": "day_opening"]) { $1 }]]
    }
}
#endif
