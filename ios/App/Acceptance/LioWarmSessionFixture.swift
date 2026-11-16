// Disposable no-network fixture. It exercises the production Home's rebind path,
// not the real SDK account root, Hong Kong session or a physical phone call.
@MainActor private struct LioWarmSessionFixture: View {
    let language: LioLanguage
    @State private var revision = UUID()
    @State private var available = true
    @State private var failed = false
    @State private var renewed = false
    @State private var reconnects = 0
    @State private var newChats = 0

    private func service() -> LioService {
        let renewed = renewed
        return LioService(updates: { _ in
            AsyncStream { output in
                do {
                    var rows: [[String: Any]] = [["message_id": "synthetic-existing", "text": "Existing question",
                        "answer": "Existing answer", "status": "completed", "sources": []]]
                    if renewed { rows.append(["message_id": "synthetic-read-after-renewal", "text": "Same conversation",
                        "answer": "Details after renewal", "status": "completed", "sources": []]) }
                    let value: [String: Any] = ["version": "LIO-timeline.2", "conversation_id": "lio-dialogue-0123456789abcdef0123456789abcdef",
                                               "messages": rows, "next_before": NSNull()]
                    output.yield(.snapshot(LioTimelinePage(try LioTimelineWire.decodePage(JSONSerialization.data(withJSONObject: value), version: .v2))))
                } catch { output.yield(.failed(.init(error, stage: .timeline))) }
                output.finish()
            }
        }, events: { _ in AsyncStream { $0.yield(.failed(.unavailable)); $0.finish() } })
    }
    var body: some View {
        VStack(spacing: 0) {
            LioHome(language: language, service: service(), isDemo: false,
                    chatLibrary: LioChatLibrary(currentID: "synthetic-default", history: { [] },
                      newChat: { newChats += 1; return LioChatSession(id: "synthetic-new", title: "", service: service()) }),
                    tripLibrary: LioTripLibrary(entries: {
                        [.init(tripID: "synthetic-trip", title: renewed ? "Trip after renewal" : "Trip before renewal", calendar: nil, dayCount: nil)]
                    }, record: { _ in nil }),
                    session: .init(revision: revision, available: available, showsRetry: failed),
                    reconnect: { reconnects += 1; renewed = true; failed = false; revision = UUID(); available = true }) { EmptyView() }
            HStack {
                Button("Refresh") { revision = UUID() }.accessibilityIdentifier("fixture.session.read-failure")
                Button("Suspend") { available = false }.accessibilityIdentifier("fixture.session.suspend")
                Button("Connection error") { failed = true }.accessibilityIdentifier("fixture.session.offline")
            }
            .frame(minHeight: 44)
            .font(.body).foregroundStyle(LioTheme.ink).tint(LioTheme.vermilion)
            .padding(8).background(LioTheme.surface)
            HStack {
                Text(String(reconnects)).accessibilityIdentifier("fixture.session.reconnects")
                Text(String(newChats)).accessibilityIdentifier("fixture.session.new-chats")
            }.font(.caption).foregroundStyle(LioTheme.ink)
        }
    }
}
