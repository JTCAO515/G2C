#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageClient
import CJMessageHTTP
import Observation

@MainActor private struct LioReadFailureFixture: View {
    let shell: ShellState
    @State private var source = ReadFailureAcceptanceSource()
    var body: some View {
        LioHome(language: shell.language.lio, service: .timeline(send: { _ in
            IssueNotUsedForReads.fail()
            return .uncertain
        }, read: { _,_ in try await source.read() }, pollInterval: .milliseconds(100), observationWindow: .seconds(3)), isDemo: false) {
            Button("Fail next read") { source.failing = true }
                .accessibilityIdentifier("fixture.read.fail")
            Button("Restore read") { source.failing = false }
                .accessibilityIdentifier("fixture.read.restore")
        }
    }
}

@MainActor @Observable private final class ReadFailureAcceptanceSource {
    var failing = !ProcessInfo.processInfo.arguments.contains("--lio-read-after-loaded")
    func read() throws -> LioTimelineWire.Page {
        if failing {
            let mode = ProcessInfo.processInfo.arguments
            if mode.contains("--lio-read-503") {
                throw LioRequestProblem(MessageHTTPFailure.invalidResponse, stage: .timeline,
                    observation: .init(kind: .timeline, httpStatus: 503, offline: false))
            }
            if mode.contains("--lio-read-401") {
                throw LioRequestProblem(MessageHTTPFailure.invalidResponse, stage: .timeline,
                    observation: .init(kind: .timeline, httpStatus: 401, offline: false))
            }
            if mode.contains("--lio-read-inactive") { throw RecoveryError.inactive }
            throw URLError(.notConnectedToInternet)
        }
        return try LioTimelineWire.decodePage(Data(#"{"version":"LIO-timeline.1","conversation_id":"lio-dialogue-0123456789abcdef0123456789abcdef","messages":[{"message_id":"fixture-old","text":"A travel question","answer":"Your earlier answer is still here.","status":"completed","failure":null,"sources":[],"trip":null,"memory":null}],"next_before":null}"#.utf8))
    }
}
private enum IssueNotUsedForReads { nonisolated static func fail() { assertionFailure("Read-only recovery must not submit") } }
#endif
