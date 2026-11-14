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
#endif
