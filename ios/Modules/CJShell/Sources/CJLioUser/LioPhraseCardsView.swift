#if os(iOS)
import AVFoundation
import SwiftUI

struct LioPhraseCardsView: View {
    let language: LioLanguage

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                ForEach(LioPhraseCategory.allCases) { category in
                    NavigationLink {
                        LioPhraseCategoryView(category: category, language: language)
                    } label: {
                        Label(category.title(in: language), systemImage: category.icon)
                            .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
                            .padding(.horizontal, 16)
                            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                            .foregroundStyle(LioTheme.ink)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.phrases.category." + category.rawValue)
                }
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Phrase Cards", "常用语卡片"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct LioPhraseCategoryView: View {
    let category: LioPhraseCategory
    let language: LioLanguage
    @State private var selected: LioTravelPhrase?

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                ForEach(category.phrases) { phrase in
                    Button {
                        selected = phrase
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(phrase.text(in: language))
                                .foregroundStyle(LioTheme.ink)
                            Text(language == .english ? phrase.chinese : phrase.english)
                                .font(.subheadline)
                                .foregroundStyle(LioTheme.inkSecondary)
                        }
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .padding(14)
                        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.phrases.card." + phrase.id)
                }
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(category.title(in: language))
        .navigationBarTitleDisplayMode(.inline)
        .fullScreenCover(item: $selected) { phrase in
            LioPhrasePosterView(phrase: phrase, language: language)
        }
    }
}

private struct LioPhrasePosterView: View {
    let phrase: LioTravelPhrase
    let language: LioLanguage
    @Environment(\.dismiss) private var dismiss
    @Environment(\.lioSpokenClip) private var spokenClip
    @State private var speaker = AVSpeechSynthesizer()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(phrase.chinese)
                    .font(.largeTitle.bold())
                Text(phrase.english)
                    .font(.title3)
                    .foregroundStyle(LioTheme.inkSecondary)
                if let spokenClip {
                    LioSpokenPlaybackControls(language: language, clip: spokenClip, choices: [
                        .init(id: "lio.phrases.read.zh-CN", title: language.text("Read Chinese", "朗读中文"),
                              phrase: .init(language: .chinese, text: phrase.chinese)),
                        .init(id: "lio.phrases.read.en-US", title: language.text("Read English", "朗读英文"),
                              phrase: .init(language: .english, text: phrase.english)),
                    ])
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        readButton(language.text("Read Chinese", "朗读中文"), phrase.chinese, locale: "zh-CN")
                        readButton(language.text("Read English", "朗读英文"), phrase.english, locale: "en-US")
                    }
                    .buttonStyle(.bordered)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(24)
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            HStack {
                Spacer()
                Button { dismiss() } label: {
                    Text(language.text("Done", "完成"))
                        .font(.body)
                        .padding(.horizontal, 12)
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier("lio.phrases.done")
            }
            .padding(.horizontal, 12)
            .background(LioTheme.paper)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .onDisappear { speaker.stopSpeaking(at: .immediate) }
    }

    private func readButton(_ title: String, _ text: String, locale: String) -> some View {
        Button {
            speaker.stopSpeaking(at: .immediate)
            let utterance = AVSpeechUtterance(string: text)
            utterance.voice = AVSpeechSynthesisVoice(language: locale)
            speaker.speak(utterance)
        } label: {
            Label(title, systemImage: "speaker.wave.2")
                .frame(minHeight: 44)
        }
        .accessibilityIdentifier("lio.phrases.read." + locale)
    }
}
#endif
