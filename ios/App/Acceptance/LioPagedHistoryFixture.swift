// Generated simulator fixture only: synthetic 32/41 rows, no service or credential.
@MainActor private struct LioPagedHistoryFixture: View {
    let language: LioLanguage
    nonisolated static func page(before: String? = nil, language: LioLanguage) throws -> LioTimelinePage {
        let end = before.flatMap { Int($0.replacingOccurrences(of: "synthetic-page-", with: "")) } ?? (language == .chinese ? 32 : 41)
        let start = max(0, end - 20)
        let rows: [[String: Any]] = (start..<end).map { index in
            var row: [String: Any] = ["message_id": "synthetic-page-" + String(index),
                "text": "Synthetic question " + String(index % 3), "answer": "Synthetic answer " + String(index % 2),
                "status": (language == .english && index == 5) ? "failed" : "completed", "sources": []]
            if (language == .english && index == 5) { row["failure"] = "unavailable"; row["answer"] = "A hidden historical partial answer" }
            return row
        }
        let value: [String: Any] = ["version": "LIO-timeline.2", "conversation_id": "lio-dialogue-0123456789abcdef0123456789abcdef",
            "messages": rows, "next_before": start > 0 ? "synthetic-page-" + String(start) : NSNull()]
        return LioTimelinePage(try LioTimelineWire.decodePage(JSONSerialization.data(withJSONObject: value), version: .v2))
    }
    var body: some View {
        let language = language
        let service = LioService(updates: { _ in AsyncStream<LioTimelineUpdate> { c in
            do { c.yield(.snapshot(try Self.page(language: language))); c.finish() } catch { c.finish() }
        } }, earlier: { try Self.page(before: $0, language: language) }, events: { _ in AsyncStream { $0.finish() } })
        LioHome(language: language, service: service, isDemo: false,
          chatLibrary: LioChatLibrary(currentID: "synthetic-original", history: { [] },
            newChat: { LioChatSession(id: "synthetic-new", title: "", service: .unavailable) })) { EmptyView() }
    }
}
