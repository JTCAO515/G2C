#if os(iOS)
import SwiftUI
import CJRunClient

/// The host supplies the explicit consent action. Presenting or dismissing
/// this view does not perform an invitation exchange.
public struct DemoV2ConsentView: View {
    let language: ShellLanguage
    let canAgree: Bool
    let onAgree: () -> Void
    let onBack: () -> Void

    public init(language: ShellLanguage, canAgree: Bool, onAgree: @escaping () -> Void, onBack: @escaping () -> Void) {
        self.language = language
        self.canAgree = canAgree
        self.onAgree = onAgree
        self.onBack = onBack
    }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                ShellCardHeading(title: language.text("Use fictional trip details", "请使用虚构旅行信息"), symbol: "hand.raised")
                RunReadableText(text: language.text(
                    "This is an internal demo. Please use fictional trip details and leave out personal information. Placeholder pending #225.",
                    "本次为内部演示。请使用虚构的旅行信息，勿填写个人信息。待 #225 定案后替换。"))
                    .accessibilityIdentifier("demo.invite.consent")
                Button(action: onAgree) {
                    ShellActionLabel(title: language.text("Agree and continue", "同意并继续"), symbol: "checkmark")
                }
                .buttonStyle(ShellActionButtonStyle(emphasized: true))
                .disabled(!canAgree)
                .accessibilityIdentifier("demo.invite.signin")
                Button(action: onBack) {
                    ShellActionLabel(title: language.text("Back", "返回"), symbol: "arrow.left")
                }
                .buttonStyle(ShellActionButtonStyle())
            }
            .shellCard()
            .padding(16)
        }
        .navigationTitle(language.text("Internal demo consent", "内部演示同意"))
        .navigationBarTitleDisplayMode(.inline)
    }
}
#endif
