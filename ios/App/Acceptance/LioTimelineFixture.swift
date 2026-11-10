// App source used only by the generated simulator acceptance project.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageHTTP
import Observation

private struct LioTimelineFixture: View {
    let shell: ShellState
    @State private var server: TimelineAcceptanceServer
    @State private var service: LioService

    init(shell: ShellState) {
        self.shell = shell
        let server = TimelineAcceptanceServer()
        _server = State(initialValue: server)
        _service = State(initialValue: LioService.timeline(
            send: { try await server.submit($0) },
            read: { id, _ in try await server.read(id) },
            pollInterval: .milliseconds(250)
        ))
    }

    var body: some View {
        LioHome(language: shell.language.lio, service: service, isDemo: true) {
            LioLanguagePicker(shell: shell)
        }
        .overlay(alignment: .topTrailing) {
            VStack {
                Button("Next timeline state") { server.advance() }
                Text(String(server.reads)).accessibilityIdentifier("lio.fixture.read-count")
                Text(String(server.sends)).accessibilityIdentifier("lio.fixture.send-count")
            }
            .padding(12)
        }
    }
}

@MainActor @Observable
private final class TimelineAcceptanceServer {
    private enum Step: Int { case sending, weather, prefix, finished }
    private let conversationID = "lio-dialogue-0123456789abcdef0123456789abcdef"
    private var step = Step.sending
    private var sent: (id: String, question: String)?
    private(set) var reads = 0
    private(set) var sends = 0

    func advance() {
        if let next = Step(rawValue: step.rawValue + 1) { step = next }
    }

    func submit(_ request: LioTimelineWire.Send) throws -> LioService.SendResult {
        sends += 1
        let body = try JSONDecoder().decode([String: String].self, from: request.originalUTF8)
        guard sent == nil, let question = body["text"] else { throw MessageHTTPFailure.invalidConfiguration }
        sent = (request.messageID, question)
        return .accepted(conversationID: conversationID)
    }

    func read(_ id: String?) throws -> LioTimelineWire.Page {
        reads += 1
        var messages: [[String: Any]] = []
        if let sent {
            var row: [String: Any] = ["message_id": sent.id, "text": sent.question,
                                       "status": "answering", "answer": "", "sources": []]
            switch step {
            case .sending: row["status"] = "sending"
            case .weather: row["activity"] = "checking_weather"
            case .prefix: row["answer"] = "北京明天"
            case .finished:
                row["status"] = "completed"
                row["answer"] = "北京明天有小雨。"
                row["sources"] = [["title": "演示天气预报", "url": "https://weather.example.org/beijing"]]
            }
            messages = [row]
        }
        let bytes = try JSONSerialization.data(withJSONObject: [
            "version": "LIO-timeline.1", "conversation_id": conversationID, "messages": messages, "next_before": NSNull()
        ])
        return try LioTimelineWire.decodePage(bytes, for: id)
    }
}
#endif
