// Used only by the generated simulator acceptance project; no service or model calls.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
struct LioExplorationQuestionsFixture: View {
    let chinese: Bool
    @State private var draft: LioQuestionDraft
    @State private var sent = ""
    @State private var count = 0
    @State private var canSend = true

    init(chinese: Bool) {
        self.chinese = chinese
        func option(_ id: String, _ en: String, _ zh: String, _ send: String) -> LioQuestionOption {
            LioQuestionOption(id: id, displayText: chinese ? zh : en, sendText: send)
        }
        _draft = State(initialValue: LioQuestionDraft(messageID: "one", questions: [
            LioQuestionGroup(id: "interests", question: chinese ? "你想体验哪些？" : "What sounds interesting?", multiple: true,
                        options: [option("interests.history", "History", "历史文化", "Interests: History"),
                                  option("interests.food", "Food", "当地美食", "Interests: Food"),
                                  option("interests.nature", "Nature", "自然风光", "Interests: Nature")]),
            LioQuestionGroup(id: "pace", question: chinese ? "你喜欢什么节奏？" : "What pace suits you?", multiple: false,
                        options: [option("pace.slow", "Slow", "慢慢来", "Pace: Slow"),
                                  option("pace.balanced", "Balanced", "适中", "Pace: Balanced"),
                                  option("pace.active", "Active", "充实些", "Pace: Active")])
        ]))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                LioQuestionForm(draft: $draft, language: chinese ? .chinese : .english, canSend: canSend) { text in
                    sent = text
                    count += 1
                }
                Text(String(count)).accessibilityIdentifier("fixture.send-count")
                Text(sent).accessibilityIdentifier("fixture.sent").textSelection(.enabled)
                HStack {
                    Button(chinese ? "更新" : "Refresh") {
                        draft.apply(messageID: draft.messageID, questions: draft.questions)
                    }.accessibilityIdentifier("fixture.refresh")
                    Button(chinese ? "只读" : "Read only") { canSend = false }
                        .accessibilityIdentifier("fixture.read-only")
                }
                .buttonStyle(.bordered)
                .tint(LioTheme.vermilion)
            }
            .padding(16)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
    }
}

#endif
