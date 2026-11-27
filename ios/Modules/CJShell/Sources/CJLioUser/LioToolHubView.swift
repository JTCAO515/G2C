#if os(iOS)
import SwiftUI

/// A hub card's page (#1980): the tools merged into one card, as rows that open each tool's own page. Eat & Play
/// holds nearby places, sight bookings and the menu helper; Money holds the payment guide and the currency
/// converter. The tools keep their ids, so routes and answer buttons reach them as before.
struct LioToolHubView: View {
    let language: LioLanguage
    let title: String
    let rows: [LioTool]

    /// The rows this build has, in the order given.
    @MainActor static func rows(_ tools: [LioTool], in context: LioToolContext) -> [LioTool] {
        let shown = Set(LioToolCatalog.visible(context.availability()))
        return tools.filter { shown.contains($0) }
    }

    var body: some View {
        ScrollView {
            VStack(spacing: LioTheme.Spacing.sm) {
                ForEach(rows, id: \.self) { tool in
                    if let route = LioRoute(tool: tool) {
                        NavigationLink(value: route) {
                            LioToolCard(tool: tool, language: language)
                        }
                        .buttonStyle(.plain)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(tool.accessibilityLabel(language))
                        .accessibilityAddTraits(.isButton)
                        .accessibilityIdentifier(tool.identifier)
                    }
                }
            }
            .padding(LioTheme.Spacing.md)
        }
        .background(LioTheme.paper)
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("lio.tools.hub")
    }
}
#endif
