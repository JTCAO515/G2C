#if os(iOS)
import CJRunClient
import SwiftUI
import UIKit

/// The Tools tab (#1421): a two-column grid of tool cards. Hidden tools are not listed. Cards and pages come from
/// `LioToolRegistry` (#1724); routes from elsewhere in the app arrive through `LioRouter.toolsPath`.
struct LioToolsView: View {
    let language: LioLanguage
    let history: LioTranslationHistory?
    let relay: LioRelayTranslationClient?
    let currencyRelay: LioCurrencyRelayClient?
    let enabled: Bool
    let sessionIsCurrent: @MainActor () -> Bool
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @Environment(\.lioNearbyService) private var nearbyService
    @Environment(\.lioHotelFinder) private var hotelFinder
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.lioRoadbookDirectory) private var roadbookDirectory
    @Environment(\.lioSavedPlans) private var savedPlans
    @Environment(\.lioMenuService) private var menuService
    @Environment(\.lioToolServices) private var services
    @Environment(LioRouter.self) private var router: LioRouter?
    /// Pages open when no router is present (previews).
    @State private var localPath: [LioRoute] = []

    private var context: LioToolContext {
        var context = LioToolContext(language: language)
        context.services = services
        context.enabled = enabled
        context.sessionIsCurrent = sessionIsCurrent
        context.translationHistory = history
        context.translationRelay = relay
        context.currencyRelay = currencyRelay
        context.taxiEntry = taxiEntry
        context.nearbyService = nearbyService
        context.hotelFinder = hotelFinder
        context.roadbookDirectory = roadbookDirectory
        context.savedPlans = savedPlans
        context.menuService = menuService
        return context
    }

    private var path: Binding<[LioRoute]> {
        guard let router else { return $localPath }
        return Binding(get: { router.toolsPath }, set: { router.toolsPath = $0 })
    }

    private var columns: [GridItem] {
        let count = typeSize.isAccessibilitySize ? 1 : 2
        return Array(repeating: GridItem(.flexible(), spacing: LioTheme.Spacing.sm, alignment: .top), count: count)
    }

    var body: some View {
        let context = context
        let visible = LioToolCatalog.visible(context.availability())
        NavigationStack(path: path) {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    Text(LioToolCatalog.title(language))
                        .font(LioTheme.display(.largeTitle).bold())
                        .foregroundStyle(LioTheme.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityAddTraits(.isHeader)
                    LazyVGrid(columns: columns, spacing: LioTheme.Spacing.sm) {
                        ForEach(visible, id: \.self) { tool in
                            if let route = LioRoute(tool: tool) {
                                NavigationLink(value: route) {
                                    LioToolCard(tool: tool, language: language)
                                }
                                .buttonStyle(LioToolCardStyle())
                                .accessibilityElement(children: .ignore)
                                .accessibilityLabel(tool.accessibilityLabel(language))
                                .accessibilityAddTraits(.isButton)
                                .accessibilityIdentifier(tool.identifier)
                            }
                        }
                    }
                }
                .padding(.horizontal, LioTheme.Spacing.md)
                .padding(.vertical, 18)
            }
            .background(LioTheme.paper)
            .navigationTitle(LioToolCatalog.title(language))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: LioRoute.self) { route in
                page(route, context: context, visible: visible)
                    .toolbar(.visible, for: .navigationBar)
            }
        }
        .tint(LioTheme.vermilion)
    }

    /// The route's page; a tool this build does not show opens a short notice instead.
    @ViewBuilder private func page(_ route: LioRoute, context: LioToolContext, visible: [LioTool]) -> some View {
        if visible.contains(route.tool), let entry = LioToolRegistry.entry(for: route.tool) {
            entry.page(context, route)
        } else {
            LioToolUnavailableView(language: language)
        }
    }
}

/// Shown when a route names a tool this build or account does not have.
struct LioToolUnavailableView: View {
    let language: LioLanguage

    var body: some View {
        Text(language.text("This tool isn’t available in this version.", "这个版本还没有这个工具。"))
            .font(.body)
            .foregroundStyle(LioTheme.inkSecondary)
            .multilineTextAlignment(.center)
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(LioTheme.paper)
            .accessibilityIdentifier("lio.tools.unavailable")
    }
}

/// One tool card: tinted icon, name and a one-sentence summary on a `surface` card.
struct LioToolCard: View {
    let tool: LioTool
    let language: LioLanguage
    /// The icon's tile grows with the symbol (both follow `.title3`), so wide symbols such as `house.and.flag`
    /// stay inside it at accessibility text sizes.
    @ScaledMetric(relativeTo: .title3) private var iconTile: CGFloat = 36

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Image(systemName: tool.symbol)
                .font(.title3.weight(.semibold))
                .foregroundStyle(LioTheme.vermilion)
                .frame(width: iconTile, height: iconTile)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityHidden(true)
            Text(tool.name(language))
                .font(.headline)
                .foregroundStyle(LioTheme.ink)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Text(tool.summary(language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .multilineTextAlignment(.leading)
        .frame(maxWidth: .infinity, minHeight: 108, alignment: .topLeading)
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

private struct LioToolCardStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(LioTheme.Motion.animation(LioTheme.Motion.micro, reduceMotion: reduceMotion),
                       value: configuration.isPressed)
    }
}
#endif
