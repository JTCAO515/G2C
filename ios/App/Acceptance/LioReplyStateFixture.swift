// Generated Debug simulator target only; no network or product test hook.
@MainActor private struct LioReplyStateFixture: View {
    let language: LioLanguage
    @State private var source = ""
    @State private var streaming = true
    @State private var started = false

    var body: some View {
        VStack(spacing: 20) {
            if started {
                LioStreamingText(source: source, streaming: streaming, animate: true, language: language)
            }
            Button("Begin reply") {
                source = language.text("First reply.", "第一条回答。")
                started = true
            }.accessibilityIdentifier("fixture.reply.begin")
            Button("Finish reply") {
                source += language.text(" All of the reply is here.", "完整回答已经显示。")
                streaming = false
            }.accessibilityIdentifier("fixture.reply.finish")
            Button("Reject reply") {
                source = #"{"tool_calls":[{"name":"weather"}]}"#
                streaming = false
            }.accessibilityIdentifier("fixture.reply.reject")
        }
        .buttonStyle(.bordered)
        .controlSize(.large)
        .font(.body)
        .foregroundStyle(LioTheme.ink)
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(LioTheme.paper)
    }
}
