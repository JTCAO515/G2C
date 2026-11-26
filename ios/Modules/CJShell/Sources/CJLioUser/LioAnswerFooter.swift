import Foundation
import SwiftUI

/// #1753 (W4-9): one line under each finished answer saying it was written by AI. Behind `G2CAIDisclosureEnabled`,
/// off unless the build says YES (approved by the coordinator under JT's pre-authorisation, 2026-11-26).
enum LioAIDisclosureFeature {
    static let infoKey = "G2CAIDisclosureEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-ai-disclosure-preview")
        #else
        return false
        #endif
    }

    static func text(_ language: LioLanguage) -> String {
        language.text("AI-generated and may be wrong. Double-check anything important.",
                      "由 AI 生成，可能有误，重要信息请自行确认。")
    }
}

#if os(iOS)
/// What follows a finished answer: the AI line, when the build shows it.
struct LioAnswerFooter: View {
    let language: LioLanguage
    let showsDisclosure: Bool

    var body: some View {
        if showsDisclosure {
            // One wrapping text element (the symbol is inline), so it grows with Dynamic Type instead of clipping.
            (Text(Image(systemName: "sparkles")) + Text(" ")
                + Text(LioAIDisclosureFeature.text(language)))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityLabel(LioAIDisclosureFeature.text(language))
                .accessibilityIdentifier("lio.answer.ai-disclosure")
        }
    }
}
#endif
