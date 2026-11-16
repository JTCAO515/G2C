// Synthetic-only fixture for the existing exploration reply component.
private struct LioExitCapsuleFixture: View {
    let chinese: Bool
    @State private var questions = LioQuestionDraft(messageID: "synthetic-exits", questions: [])
    @State private var count = 0
    @State private var sent = ""

    var body: some View {
        let arguments = ProcessInfo.processInfo.arguments
        var exits: [LioExplorationPresentation.Exit] = [
            .init(id: "plan_now", displayText: chinese ? "先排行程" : "Plan now",
                  sendText: chinese ? "请先帮我安排三天行程" : "Please make a three-day plan"),
            .init(id: "explore", displayText: chinese ? "再看看方向" : "Explore more",
                  sendText: chinese ? "想先了解更多旅行方向" : "Show me more travel ideas")
        ]
        if arguments.contains("--three-exits") {
            exits.append(.init(id: "adjust", displayText: chinese ? "换个方向" : "Change direction",
                sendText: chinese ? "请帮我换一个旅行方向" : "Please change the travel direction"))
        }
        if arguments.contains("--empty-exits") { exits = [] }
        return ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                LioExplorationReplyView(presentation: .init(segments: [.init(purpose: .direction,
                    text: chinese ? "你可以先看看方向，或直接开始规划。" : "Explore a few ideas, or start planning.")],
                    profile: [], notices: [], exits: exits, answer: ""), questions: $questions,
                    language: chinese ? .chinese : .english, canSend: !arguments.contains("--disabled-exits")) { text in
                        count += 1; sent = text
                    }
                Text(String(count)).accessibilityIdentifier("fixture.exit.count")
                Text(sent).accessibilityIdentifier("fixture.exit.sent")
            }
            .padding(24)
        }
        .lioPage()
    }
}
