// Generated simulator acceptance only (#913): waiting indicators at fixed ages, with line L's progress
// mapped through LioThinkingInput the same way the conversation will pass it.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageHTTP
struct LioThinkingFixture: View {
    let chinese: Bool
    @State private var started = Date()

    var body: some View {
        let language: LioLanguage = chinese ? .chinese : .english
        let waiting = LioThinkingInput(.waiting(chinese ? "正在比较几家酒店的位置" : "Comparing where the hotels are"))
        let planning = LioThinkingInput(.planningStarted(text: chinese ? "开始安排 3 天行程" : "Starting your 3-day plan", days: 3))
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                LioThinkingIndicator(since: started, progress: nil, planningDays: nil, language: language)
                LioThinkingIndicator(since: started.addingTimeInterval(-7), progress: nil, planningDays: nil, language: language)
                LioThinkingIndicator(since: started.addingTimeInterval(-16), progress: nil, planningDays: nil, language: language)
                LioThinkingIndicator(since: started.addingTimeInterval(-7), progress: waiting.progress,
                                     planningDays: waiting.planningDays, language: language)
                LioThinkingIndicator(since: started.addingTimeInterval(-7), progress: planning.progress,
                                     planningDays: planning.planningDays, language: language)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(LioTheme.paper)
        .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("--lio-thinking-dark-acceptance") ? .dark : .light)
    }
}

// Injected scene phases exercise the real indicator's lifecycle without a service request.
private struct LioThinkingLifecycleFixture: View {
    @State private var paused = true
    @State private var shown = true
    @State private var change = 0
    @State private var appearances = 0
    @State private var announcements = 0
    private let since = Date().addingTimeInterval(-7)

    var body: some View {
        VStack(spacing: 20) {
            if shown {
                LioThinkingIndicator(since: since, progress: "Travel ideas \(change)", planningDays: 2,
                    language: .english, onVisible: { appearances += 1 },
                    onAnnouncement: { _ in announcements += 1 })
                    .environment(\.scenePhase, paused ? .background : .active)
            }
            Text(String(appearances)).accessibilityIdentifier("fixture.thinking.appearances")
            Text(String(announcements)).accessibilityIdentifier("fixture.thinking.announcements")
            Button(paused ? "Resume" : "Pause") { paused.toggle() }
                .accessibilityIdentifier("fixture.thinking.pause")
            Button("Change progress") { change += 1 }
                .accessibilityIdentifier("fixture.thinking.change")
            Button(shown ? "Hide" : "Show") { shown.toggle() }
                .accessibilityIdentifier("fixture.thinking.show")
        }
        .buttonStyle(.bordered)
        .controlSize(.large)
        .padding(20)
        .background(LioTheme.paper)
    }
}

private struct LioRetryTimingFixture: View {
    let shell: ShellState
    @State private var sample = RetryTimingSample()
    @State private var prepared = false

    var body: some View {
        let sample = sample
        Group {
            if prepared {
                LioHome(language: shell.language.lio, service: LioService { _ in
                    AsyncStream { output in
                        Task { await sample.reply(output); output.finish() }
                    }
                }, isDemo: true) { RetryTimingSummary() }
            } else {
                Color.clear.onAppear {
                    UserDefaults.standard.removeObject(forKey: LioTimingLog.defaultsKey)
                    prepared = true
                }
            }
        }
    }
}

private actor RetryTimingSample {
    private var count = 0
    func reply(_ output: AsyncStream<LioEvent>.Continuation) {
        count += 1
        if count == 1 { output.yield(.failed(.unfinished)) }
        else { output.yield(.text("Here are some travel ideas.")); output.yield(.finished) }
    }
}

private struct RetryTimingSummary: View {
    var body: some View {
        Text(String(LioTimingLog().entries().count))
            .accessibilityIdentifier("fixture.timing.count")
    }
}
#endif
