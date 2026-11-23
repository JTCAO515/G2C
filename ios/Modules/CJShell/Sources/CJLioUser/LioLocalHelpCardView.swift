#if os(iOS)
import SwiftUI

private enum LioLocalHelpMessage: String, CaseIterable, Identifiable {
    case assistance, interpreter, medical, police

    var id: Self { self }

    func title(in language: LioLanguage) -> String {
        switch self {
        case .assistance: language.text("General help", "一般求助")
        case .interpreter: language.text("Language help", "语言协助")
        case .medical: language.text("Medical help", "就医求助")
        case .police: language.text("Police help", "警方协助")
        }
    }

    func message(in language: LioLanguage) -> String {
        switch self {
        case .assistance:
            language.text("I need help. Could you assist me, please?", "我需要帮助，可以帮我一下吗？")
        case .interpreter:
            language.text("I don't speak Chinese. Could you help me find someone who speaks English?",
                          "我不会说中文，可以帮我找一位会说英语的人吗？")
        case .medical:
            language.text("I need to see a doctor. Could you show me where to go?",
                          "我需要看医生，可以告诉我该去哪里吗？")
        case .police:
            language.text("I need help. Could you contact the police for me?",
                          "我需要帮助，可以帮我联系警方吗？")
        }
    }
}

struct LioLocalHelpCardView: View {
    let language: LioLanguage
    @State private var message = LioLocalHelpMessage.assistance

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Menu {
                    ForEach(LioLocalHelpMessage.allCases) { option in
                        Button(option.title(in: language)) { message = option }
                    }
                } label: {
                    Label(message.title(in: language), systemImage: "chevron.down")
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier("lio.support.help-card.message")
                Text(message.message(in: .chinese))
                    .font(.largeTitle.bold())
                    .accessibilityIdentifier("lio.support.help-card.chinese")
                Text(message.message(in: .english))
                    .font(.title3)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.support.help-card.english")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(24)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Show a Local", "给当地人看"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
    }
}
#endif
