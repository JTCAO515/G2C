// Synthetic-only entry for the generated simulator acceptance project.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private struct LioExplorationReplyFixture: View {
    let chinese: Bool
    let mode: Int
    @State private var questions: LioQuestionDraft
    @State private var count = 0
    @State private var sent = ""
    @State private var refreshed = false
    @State private var readOnly = false

    init(chinese: Bool) {
        let args = ProcessInfo.processInfo.arguments
        let mode = args.contains("--lio-exploration-legacy-acceptance") ? 1 : args.contains("--lio-exploration-profile-only-acceptance") ? 2 : 0
        self.chinese = chinese
        self.mode = mode
        let choices = [
            LioQuestionOption(id: "interests.history", displayText: chinese ? "历史" : "History", sendText: chinese ? "喜欢历史文化" : "I enjoy history"),
            LioQuestionOption(id: "interests.food", displayText: chinese ? "美食" : "Food", sendText: chinese ? "喜欢当地美食" : "I enjoy local food"),
            LioQuestionOption(id: "interests.nature", displayText: chinese ? "自然" : "Nature", sendText: chinese ? "喜欢自然风光" : "I enjoy nature")
        ]
        _questions = State(initialValue: LioQuestionDraft(messageID: "sample", questions: mode == 0 ? [
            LioQuestionGroup(id: "interests", question: chinese ? "你喜欢哪些体验？" : "Which experiences appeal to you?", multiple: true, options: choices)
        ] : []))
    }

    private var presentation: LioExplorationPresentation {
        let profile: [LioExplorationPresentation.ProfileEntry] = [
            .init(id: "pace", displayText: chinese ? "节奏轻松" : "Slow pace", state: .known),
            .init(id: "interests", displayText: chinese ? "安静的地方" : "Quiet places", state: .inferred)
        ]
        if mode != 0 {
            return .init(segments: [], profile: mode == 2 ? profile : [], notices: [], exits: [],
                         answer: chinese ? "**之前的回答**\n\n• 可以慢慢商量。" : "**Earlier reply**\n\n• We can explore ideas together.")
        }
        var segments: [LioExplorationPresentation.Segment] = [
            .init(purpose: .response, text: chinese ? "先按你的想法慢慢安排。" : "Let's shape a trip around you."),
            .init(purpose: .direction, text: chinese ? "先选些感兴趣的体验。" : "Let's start with your interests.")
        ]
        if refreshed { segments.append(.init(purpose: .summary, text: chinese ? "也可以直接开始安排。" : "We can also make a plan now.")) }
        return .init(segments: segments, profile: profile, notices: [
            .init(id: "weather-day-1", text: chinese ? "演示提醒：带件外套。" : "Sample reminder: bring a coat.", severity: .info,
                  source: LioSource(id: "weather", title: chinese ? "演示天气来源" : "Sample weather source", url: URL(string: "https://example.com/weather")))
        ], exits: [
            .init(id: "continue_refining", displayText: chinese ? "继续细化" : "Keep exploring", sendText: chinese ? "我们继续商量。" : "Let's keep exploring."),
            .init(id: "plan_now", displayText: chinese ? "直接出方案" : "Make a plan now", sendText: chinese ? "直接给我一个方案。" : "Please make a plan now.")
        ], answer: "Combined answer for an older reader")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                LioExplorationReplyView(presentation: presentation, questions: $questions,
                                        language: chinese ? .chinese : .english, canSend: !readOnly) { text in
                    count += 1
                    sent = text
                }
                Text(String(count)).accessibilityIdentifier("fixture.count")
                Text(sent).accessibilityIdentifier("fixture.sent")
                Button {
                    refreshed = true
                    questions.apply(messageID: questions.messageID, questions: questions.questions)
                } label: { Text(chinese ? "更新演示" : "Refresh sample").frame(minHeight: 44) }
                    .buttonStyle(.bordered).accessibilityIdentifier("fixture.refresh")
                Button { readOnly = true } label: { Text(chinese ? "只读演示" : "Read-only sample").frame(minHeight: 44) }
                    .buttonStyle(.bordered).accessibilityIdentifier("fixture.read-only")
            }
            .padding(16)
        }
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
        .background(LioTheme.paper)
    }
}

#endif
