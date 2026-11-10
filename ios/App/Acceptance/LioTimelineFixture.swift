// App source used only by the generated simulator acceptance project.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageHTTP
import Observation

private struct LioTimelineFixture: View {
    let shell: ShellState
    let tripLibrary: LioTripLibrary?
    @State private var server: TimelineAcceptanceServer
    @State private var service: LioService

    init(shell: ShellState, exerciseResend: Bool) {
        self.shell = shell
        let historicalTrip = ProcessInfo.processInfo.arguments.contains("--lio-stale-trip-acceptance")
        if historicalTrip {
            let fixture = ProcessInfo.processInfo.environment["G2C_LIO_PREVIEW_TRIP"]!
            let library = try! LioPreviewTripFixture.library(fixture)
            var opens = 0
            tripLibrary = LioTripLibrary(list: library.list, detail: { id in
                opens += 1
                if opens == 1 { return try await library.detail(id) }
                throw URLError(.networkConnectionLost)
            })
        } else {
            tripLibrary = nil
        }
        let acceptedFailure = ProcessInfo.processInfo.arguments.contains("--lio-accepted-failure-acceptance")
        let server = TimelineAcceptanceServer(exerciseResend: exerciseResend, historicalTrip: historicalTrip,
                                              acceptedFailure: acceptedFailure)
        _server = State(initialValue: server)
        _service = State(initialValue: LioService.timeline(
            send: { try await server.submit($0) },
            read: { id, _ in try await server.read(id) },
            pollInterval: .milliseconds(250)
        ))
    }

    var body: some View {
        LioHome(language: shell.language.lio, service: service, isDemo: true, tripLibrary: tripLibrary) {
            LioMenuSettings(shell: shell)
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
    private let exerciseResend: Bool
    private let historicalTrip: Bool
    private let acceptedFailure: Bool
    private var step = Step.sending
    private var sent: (id: String, question: String)?
    private var unsent: LioTimelineWire.Send?
    private(set) var reads = 0
    private(set) var sends = 0

    init(exerciseResend: Bool, historicalTrip: Bool, acceptedFailure: Bool) {
        self.exerciseResend = exerciseResend
        self.historicalTrip = historicalTrip
        self.acceptedFailure = acceptedFailure
        if historicalTrip || acceptedFailure { step = .finished }
    }

    func advance() {
        if let next = Step(rawValue: step.rawValue + 1) { step = next }
    }

    func submit(_ request: LioTimelineWire.Send) throws -> LioService.SendResult {
        sends += 1
        if exerciseResend {
            if sends == 1 {
                unsent = request
                return .notSent
            }
            guard sends == 2, let unsent, unsent.messageID == request.messageID,
                  unsent.originalUTF8 == request.originalUTF8 else { throw MessageHTTPFailure.invalidConfiguration }
            return .dailyLimit
        }
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
                if acceptedFailure {
                    row["status"] = "failed"
                    row["failure"] = "unavailable"
                    break
                }
                row["status"] = "completed"
                row["answer"] = "**北京明天**[有小雨](https://weather.example.org/model-link)。"
                row["sources"] = [["title": "演示天气预报", "url": "https://weather.example.org/beijing"]]
                if historicalTrip {
                    row["trip"] = ["trip_id": "trip:lio-map-demo", "title": "Earlier plan", "days": [
                        ["date": "2026-11-11", "items": [
                            ["item_id": "old-stop", "label": "Earlier stop", "fixed": false]
                        ]]
                    ]]
                }
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
