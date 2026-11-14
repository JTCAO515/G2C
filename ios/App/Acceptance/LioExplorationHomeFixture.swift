// Generated actual-App simulator acceptance only; no external requests or credentials.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import HTTPTypes
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
                    ExplorationHomeCounts(wire: host.wire)
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
    @State private var count = ""
    @State private var last = ""
    @State private var lastID = ""
    var body: some View {
        VStack {
            Text(count).accessibilityValue(lastID).accessibilityIdentifier("fixture.send-count")
            Text(last).accessibilityIdentifier("fixture.last-text")
        }.task { (count, last, lastID) = await wire.counts() }
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
    let wire: ExplorationHomeWire
    let service: LioService
    init() throws {
        let wire = ExplorationHomeWire()
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
        service = .signedExplorationConversation(client, destination: .defaultChat) { _ in }
    }
}

private actor ExplorationHomeWire: ClientTransport {
    private static let conversation = "lio-dialogue-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    private var messages: [[String: Any]] = []
    private var sent: [String] = []
    func counts() -> (String, String, String) {
        ("\(sent.count)", sent.last ?? "", messages.last?["message_id"] as? String ?? "")
    }

    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL,
              operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let path = request.path!, null = NSNull()
        let output: [String: Any]
        if request.method == .post, path == "/v4/lio/messages" {
            let input = try JSONSerialization.jsonObject(with: await Data(collecting: body!, upTo: 16384)) as! [String: Any]
            precondition(input["version"] as? String == "LIO-message.4")
            let text = input["text"] as! String, chinese = input["locale"] as? String == "zh"
            sent.append(text)
            messages.append(message(input, chinese: chinese, first: sent.count == 1))
            output = ["version": "LIO-message-receipt.4", "message_id": input["message_id"]!,
                      "conversation_id": Self.conversation]
        } else if request.method == .get, path.hasPrefix("/v4/lio/timeline") {
            output = ["version": "LIO-timeline.4", "conversation_id": Self.conversation,
                      "messages": messages, "next_before": null]
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
                "activity": null, "sources": [], "trip": null, "memory": null,
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
}
#endif
