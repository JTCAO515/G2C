/// Approved display-only copy. This placeholder grants no tool capability.
enum PluginPlaceholderCopy {
    static func title(_ language: ShellLanguage) -> String { language.text("DiDi Ride-hailing", "滴滴打车") }
    static func status(_ language: ShellLanguage) -> String { language.text("Coming soon", "即将推出") }
    static func detail(_ language: ShellLanguage) -> String {
        language.text("Request rides in China from your trip. Not connected yet.", "未来可在行程中直接叫车。目前尚未接入。")
    }
    static func footer(_ language: ShellLanguage) -> String {
        language.text("More plugins are planned. No tools are connected.", "更多插件将在后续版本提供。目前未接入任何工具。")
    }
    static func accessibilityLabel(_ language: ShellLanguage) -> String {
        [title(language), status(language), detail(language)].joined(separator: language == .chinese ? "，" : ", ")
    }
}

#if os(iOS)
import SwiftUI

struct PluginPlaceholderCard: View {
    let language: ShellLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Image(systemName: "car").font(.title2).accessibilityHidden(true)
            Text(PluginPlaceholderCopy.title(language)).font(.headline)
            Text(PluginPlaceholderCopy.status(language)).font(.subheadline)
            Text(PluginPlaceholderCopy.detail(language))
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PluginPlaceholderCopy.accessibilityLabel(language))
        .accessibilityAddTraits(.isStaticText)
        .accessibilityIdentifier("plugins.didi.placeholder")
    }
}
#endif
