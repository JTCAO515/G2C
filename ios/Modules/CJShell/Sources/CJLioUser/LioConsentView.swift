#if os(iOS)
import SwiftUI

/// The first-launch consent page (#1747): shown over the home screen until the traveller has answered, so nothing
/// is sent before then. Three answers, none preselected. Declining stays on the page and says why; Leave goes back
/// to the sign-in page. The wording is `LioConsentCopy`.
struct LioConsentView: View {
    let language: LioLanguage
    let consent: LioConsent
    let leave: () -> Void
    @State private var declined = false
    @State private var couldNotSave = false
    @Environment(\.openURL) private var openURL

    private static let policy = URL(string: "https://go2china.space/privacy")!

    var body: some View {
        // A navigation bar (no title) keeps the text from running under the status bar while it scrolls.
        NavigationStack {
            page
                .navigationBarTitleDisplayMode(.inline)
                .toolbarBackground(LioTheme.paper, for: .navigationBar)
                .toolbarBackground(.visible, for: .navigationBar)
        }
        .interactiveDismissDisabled()
    }

    private var page: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                Text(LioConsentCopy.title(language))
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("lio.consent.title")
                ForEach(LioConsentCopy.items(language).indices, id: \.self) { index in
                    let item = LioConsentCopy.items(language)[index]
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                        Text(item.heading).font(.headline).foregroundStyle(LioTheme.ink)
                        Text(item.body).font(.body).foregroundStyle(LioTheme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("lio.consent.item.\(index)")
                }
                if declined {
                    declinedBlock
                } else {
                    choices
                }
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(LioTheme.paper.ignoresSafeArea())
        .alert(language.text("Could not save your choice. Try again.", "没能保存你的选择，请再试一次。"), isPresented: $couldNotSave) {
            Button(language.text("OK", "好")) {}
        }
    }

    private var choices: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            filled(LioConsentCopy.agreeWithAI(language), id: "lio.consent.agree-ai") { answer(ai: true) }
            outlined(LioConsentCopy.agreeWithoutAI(language), id: "lio.consent.agree") { answer(ai: false) }
            Button { declined = true } label: {
                Text(LioConsentCopy.decline(language))
                    .font(.body.weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.consent.decline")
        }
        .padding(.top, LioTheme.Spacing.sm)
    }

    private var declinedBlock: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            Text(LioConsentCopy.declined(language))
                .font(.body.weight(.semibold))
                .foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("lio.consent.declined")
            outlined(LioConsentCopy.readPolicy(language), id: "lio.consent.policy") { openURL(Self.policy) }
            filled(LioConsentCopy.leave(language), id: "lio.consent.leave") { leave() }
            // Changing one's mind is allowed: the three answers come back.
            Button { declined = false } label: {
                Text(language.text("Back", "返回"))
                    .font(.body).foregroundStyle(LioTheme.inkSecondary)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.consent.back")
        }
        .padding(.top, LioTheme.Spacing.sm)
    }

    private func answer(ai: Bool) {
        if !consent.agree(aiProcessing: ai) { couldNotSave = true }
    }

    private func filled(_ title: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.body.weight(.semibold))
                .foregroundStyle(LioTheme.onVermilion)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 48)
                .padding(.horizontal, LioTheme.Spacing.sm)
                .background(LioTheme.vermilion, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }

    private func outlined(_ title: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.body.weight(.semibold))
                .foregroundStyle(LioTheme.vermilion)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 48)
                .padding(.horizontal, LioTheme.Spacing.sm)
                .overlay(RoundedRectangle(cornerRadius: LioTheme.Radius.card).stroke(LioTheme.vermilion, lineWidth: 1.5))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }
}

/// Me → Privacy (#1747): AI processing, on or off. Turning it off says what stops and that sent requests cannot be
/// recalled; turning it back on confirms the recipient and place once.
struct LioPrivacyView: View {
    let language: LioLanguage
    let consent: LioConsent
    @State private var confirmingOff = false
    @State private var confirmingOn = false
    @State private var couldNotSave = false

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                    Text(LioConsentCopy.aiTitle(language)).font(.headline).foregroundStyle(LioTheme.ink)
                    Text(consent.aiProcessing ? LioConsentCopy.aiOnDetail(language) : LioConsentCopy.aiOffDetail(language))
                        .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("lio.privacy.ai-detail")
                    Button {
                        if consent.aiProcessing { confirmingOff = true } else { confirmingOn = true }
                    } label: {
                        Text(consent.aiProcessing ? LioConsentCopy.turnOff(language) : LioConsentCopy.turnOn(language))
                            .font(.body.weight(.semibold))
                            .foregroundStyle(LioTheme.vermilion)
                            .frame(minHeight: 44, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.privacy.ai-toggle")
                }
                .padding(.vertical, 4)
            }
            .lioRow()
        }
        .lioPage()
        .navigationTitle(LioConsentCopy.privacyTitle(language))
        .navigationBarTitleDisplayMode(.inline)
        .alert(LioConsentCopy.turnOffConfirm(language), isPresented: $confirmingOff) {
            Button(LioConsentCopy.turnOff(language), role: .destructive) { change(to: false) }
            Button(LioConsentCopy.cancel(language), role: .cancel) {}
        }
        .alert(LioConsentCopy.turnOnConfirm(language), isPresented: $confirmingOn) {
            Button(LioConsentCopy.turnOn(language)) { change(to: true) }
            Button(LioConsentCopy.cancel(language), role: .cancel) {}
        }
        .alert(language.text("Could not save your choice. Try again.", "没能保存你的选择，请再试一次。"), isPresented: $couldNotSave) {
            Button(language.text("OK", "好")) {}
        }
    }

    private func change(to on: Bool) {
        if !consent.setAIProcessing(on) { couldNotSave = true }
    }
}

/// What a stopped AI feature shows (#1747).
struct LioAIOffNotice: View {
    let language: LioLanguage

    var body: some View {
        HStack(alignment: .top, spacing: LioTheme.Spacing.xs) {
            Image(systemName: "sparkles").foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
            Text(LioConsentCopy.aiOff(language))
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lio.consent.ai-off")
    }
}
#endif
