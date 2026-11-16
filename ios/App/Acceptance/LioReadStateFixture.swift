// Disposable no-network fixture for the actual ordinary Home read branches.
@MainActor private struct LioReadStateFixture: View {
    let language: LioLanguage
    var body: some View {
        let unavailable = ProcessInfo.processInfo.arguments.contains("--read-stream-ended")
        let service = LioService(updates: { _ in AsyncStream<LioTimelineUpdate> { output in
            if !unavailable { output.yield(.snapshot(.empty)) }
            output.finish()
        } }, events: { _ in AsyncStream { $0.finish() } })
        LioHome(language: language,
                service: service, isDemo: false,
                chatLibrary: LioChatLibrary(currentID: "synthetic-read-state", history: { [] },
                    newChat: { LioChatSession(id: "synthetic-new", title: "", service: .unavailable) })) { EmptyView() }
    }
}
