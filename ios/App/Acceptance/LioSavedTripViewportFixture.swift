// Generated simulator App only. Real Home and typed trip reader; no business API or account.
import CJMessageHTTP

@MainActor private struct LioSavedTripViewportFixture: View {
    let shell: ShellState
    private let library: LioTripLibrary
    private let service: LioService

    init(shell: ShellState) {
        self.shell = shell
        library = try! LioPreviewTripFixture.library("__LIO_RECORDED_TRIP_FIXTURE__")
        let chinese = shell.language == .chinese
        service = LioService(updates: { _ in AsyncStream { output in
            do {
                let value: [String: Any] = [
                    "version": "LIO-timeline.1",
                    "conversation_id": "lio-dialogue-0123456789abcdef0123456789abcdef",
                    "messages": [["message_id": "synthetic-transition", "text": chinese ? "看看安排" : "Show the plan",
                        "status": "completed", "answer": chinese ? "这是一天的安排。" : "Here is the plan for one day.",
                        "sources": [], "trip": ["trip_id": "trip:lio-map-demo", "title": chinese ? "一天的安排" : "One-day plan",
                            "days": [["date": "2026-11-17", "items": [
                                ["item_id": "synthetic-stop", "label": chinese ? "公园散步" : "Park walk", "fixed": false]
                            ]]]]]], "next_before": NSNull()
                ]
                output.yield(.snapshot(LioTimelinePage(try LioTimelineWire.decodePage(JSONSerialization.data(withJSONObject: value)))))
            } catch { output.yield(.failed(.init(error, stage: .timeline))) }
            output.finish()
        } }, events: { _ in AsyncStream { $0.yield(.failed(.unavailable)); $0.finish() } })
    }

    var body: some View {
        LioHome(language: shell.language.lio, service: service, isDemo: true, tripLibrary: library) {
            LioMenuSettings(shell: shell)
        }
    }
}
