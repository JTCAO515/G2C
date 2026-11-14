// Generated simulator project only. All content and callbacks are local synthetic data.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private struct LioStreamingFixture: View {
    let chinese: Bool
    private let inlineMode = ProcessInfo.processInfo.arguments.contains("--lio-streaming-inline-acceptance")
    @State private var source: String
    @State private var streaming = true
    @State private var fresh = true
    @State private var shown = true
    @State private var firstTexts = 0
    @State private var completions = 0

    init(chinese: Bool) {
        self.chinese = chinese
        _source = State(initialValue: chinese ? "我们可以先聊聊。 " : "Here are a few ideas. ")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if shown {
                    LioStreamingText(source: source, streaming: streaming, animate: fresh,
                        language: chinese ? .chinese : .english, onFirstVisible: {
                            firstTexts += 1
                            fresh = false
                        }, onComplete: { completions += 1 })
                }
                Text(String(firstTexts)).accessibilityIdentifier("fixture.streaming.first")
                Text(String(completions)).accessibilityIdentifier("fixture.streaming.complete")
                Text(shown ? "1" : "0").accessibilityIdentifier("fixture.streaming.shown")
                Button("Heading") {
                    if inlineMode { source += chinese ? "**轻松的" : "**an easy " }
                    else { source += chinese ? "\n\n# 第1天" : "\n\n# Day 1" }
                }
                    .accessibilityIdentifier("fixture.streaming.heading")
                Button("Body") {
                    if inlineMode {
                        source += chinese ? "安排**，再看看 [指南](https://example.com/guide)。"
                            : "pace** and [the guide](https://example.com/guide)."
                    } else {
                      source += chinese
                        ? "\n\n• 博物馆\n• 公园\n\n看看 **轻松的安排** 和 [指南](https://example.com/guide)。"
                        : "\n\n• Museum\n• Park\n\nTry **an easy pace** and [the guide](https://example.com/guide)."
                    }
                }.accessibilityIdentifier("fixture.streaming.body")
                Button("Finish") { streaming = false }.accessibilityIdentifier("fixture.streaming.finish")
                Button("Hide or show") { shown.toggle() }.accessibilityIdentifier("fixture.streaming.show")
                Button("Unsafe update") { source += " Calling Amap Weather now."; streaming = false }
                    .accessibilityIdentifier("fixture.streaming.unsafe")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(20)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .tint(LioTheme.vermilion)
        .background(LioTheme.paper)
        .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("--lio-streaming-dark-acceptance") ? .dark : .light)
    }
}
#endif
