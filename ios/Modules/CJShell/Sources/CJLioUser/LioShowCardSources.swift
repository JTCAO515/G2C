#if os(iOS)
import AVFoundation
import SwiftUI

/// Show Cards as a tool of its own (#1742). Phrases and help cards are part of it, and every card is shown with
/// `LioShowCardSheet`: the one "show it to someone" screen. The cards with the traveller's own details (#1572)
/// stay behind Back to Hotel's switch (`G2CShowCardEnabled`, off by default), as before.
@MainActor enum LioShowCardTool {
    /// `section` is the part of the page a route asks for (`section=business`, #1765); nil opens it at the top.
    @ViewBuilder static func page(language: LioLanguage, roadbookDirectory: URL?,
                                  isCurrent: @escaping @MainActor () -> Bool,
                                  section: LioShowCardSection? = nil) -> some View {
        #if DEBUG
        if LioReturnHotelPreview.requested {
            LioShowCardsView(language: language, hotel: LioReturnHotelPreview.hotel, section: section)
        } else {
            built(language: language, roadbookDirectory: roadbookDirectory, isCurrent: isCurrent, section: section)
        }
        #else
        built(language: language, roadbookDirectory: roadbookDirectory, isCurrent: isCurrent, section: section)
        #endif
    }

    @ViewBuilder private static func built(language: LioLanguage, roadbookDirectory: URL?,
                                           isCurrent: @escaping @MainActor () -> Bool,
                                           section: LioShowCardSection?) -> some View {
        if LioReturnHotelTools.shownInTools {
            let store = LioReturnHotelTools.hotelStore(roadbookDirectory: roadbookDirectory, isCurrent: isCurrent)
            // A damaged hotel file reads as no hotel, as on Back to Hotel itself.
            LioShowCardsView(language: language, hotel: (try? store?.load()) ?? nil,
                             detailsStore: LioReturnHotelTools.detailsStore(roadbookDirectory: roadbookDirectory,
                                                                            isCurrent: isCurrent),
                             section: section)
        } else {
            LioShowCardsView(language: language, hotel: nil, detailScenes: false, section: section)
        }
    }
}

/// One phrase category (formerly a page of the Phrase Cards tool). A phrase opens full screen with read-aloud.
struct LioShowCardPhraseList: View {
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
        .toolbar(.hidden, for: .tabBar)
        .fullScreenCover(item: $selected) { phrase in
            LioShowCardSheet(language: language, content: .phrase(phrase), title: category.title(in: language),
                             identifierPrefix: "lio.phrases") {
                LioShowCardSpeech(language: language, chinese: phrase.chinese, english: phrase.english,
                                  identifierPrefix: "lio.phrases")
            }
        }
    }
}

/// The help cards (formerly Local Support's "Show a Local" page). Local Support links here; so does Show Cards.
struct LioShowCardHelpView: View {
    let language: LioLanguage
    @Environment(\.lioMedicalCard) private var medicalCard
    @State private var showing: LioShowCardHelp?
    @State private var showsMedicalCard = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                Text(language.text("Pick what you need, then turn the screen towards the other person.",
                                   "选你需要的那张，再把屏幕转给对方看。"))
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
                if let medicalCard, medicalCard.isCurrent() {
                    Button {
                        showsMedicalCard = true
                    } label: {
                        Label(language.text("Medical card", "医疗卡"), systemImage: "cross.case")
                            .frame(minHeight: 44)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.support.help-card.medical-card")
                }
                VStack(spacing: 0) {
                    ForEach(LioShowCardHelp.allCases) { help in
                        Button {
                            showing = help
                        } label: {
                            LioShowCardRow(title: help.title(language), detail: help.content.mainZH)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier(help.identifier)
                        if help != LioShowCardHelp.allCases.last {
                            Divider().padding(.leading, LioTheme.Spacing.md)
                        }
                    }
                }
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(LioTheme.Spacing.md)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Show a Local", "给当地人看"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
        .fullScreenCover(item: $showing) { help in
            LioShowCardSheet(language: language, content: help.content, title: help.title(language),
                             identifierPrefix: "lio.support.help-card")
        }
        .fullScreenCover(isPresented: $showsMedicalCard) {
            if let medicalCard {
                NavigationStack {
                    LioMedicalCardView(language: language, storage: medicalCard, opensDisplay: true)
                }
            }
        }
    }
}

/// A row in a show-card list: the title and, under it, the whole Chinese line (never cut short).
struct LioShowCardRow: View {
    let title: String
    var detail: String?
    var symbol: String?

    var body: some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            if let symbol {
                Image(systemName: symbol)
                    .foregroundStyle(LioTheme.vermilion)
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).foregroundStyle(LioTheme.ink)
                if let detail {
                    Text(detail)
                        .font(.footnote)
                        .foregroundStyle(LioTheme.inkSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, LioTheme.Spacing.md)
        .padding(.vertical, LioTheme.Spacing.xs)
        .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
        .contentShape(Rectangle())
    }
}

/// Read-aloud under a card (`LioShowCardSheet`'s accessory): the Chinese and the English, with the system voice.
struct LioShowCardSpeech: View {
    let language: LioLanguage
    let chinese: String
    let english: String
    /// Buttons are `<prefix>.read.zh-CN` and `<prefix>.read.en-US`.
    var identifierPrefix: String
    @State private var speaker = AVSpeechSynthesizer()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            read(language.text("Read Chinese", "朗读中文"), chinese, locale: "zh-CN")
            read(language.text("Read English", "朗读英文"), english, locale: "en-US")
        }
        .buttonStyle(.bordered)
        .onDisappear { speaker.stopSpeaking(at: .immediate) }
    }

    private func read(_ title: String, _ text: String, locale: String) -> some View {
        Button {
            speaker.stopSpeaking(at: .immediate)
            let utterance = AVSpeechUtterance(string: text)
            utterance.voice = AVSpeechSynthesisVoice(language: locale)
            speaker.speak(utterance)
        } label: {
            Label(title, systemImage: "speaker.wave.2")
                .frame(minHeight: 44)
        }
        .accessibilityIdentifier(identifierPrefix + ".read." + locale)
    }
}
#endif
