#if os(iOS)
import CJRunClient
import SwiftUI

/// Metro guide (#1421): choose a city first, then read how to buy a ticket, pass security and use
/// the gates, with the operator's official line map. Only cities with verified guidance are listed.
/// Beijing, Shanghai and Guangzhou also open an interactive line map (#1450).
struct LioMetroGuideView: View {
    let language: LioLanguage
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(language.text("Choose a city", "选择城市"))
                    .font(LioTheme.display(.title2).weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                ForEach(LioMetroCity.allCases) { city in
                    NavigationLink {
                        LioMetroCityGuideView(language: language, city: city)
                    } label: {
                        cityCard(city)
                    }
                    .buttonStyle(.plain)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(city.name(in: language) + language.text(", ", "，") + city.summary(in: language))
                    .accessibilityAddTraits(.isButton)
                    .accessibilityIdentifier(city.identifier)
                }
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .modifier(LioMetroNavigationTitle(title: language.text("Metro Guide", "地铁指南"), colorScheme: colorScheme))
    }

    private func cityCard(_ city: LioMetroCity) -> some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            Text(city.nativeName.prefix(1))
                .font(LioTheme.display(.title2).weight(.bold))
                .foregroundStyle(LioTheme.vermilion)
                .frame(width: 48, height: 48)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(city.name(in: language)).font(.headline)
                    if language == .english {
                        Text(city.nativeName).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    }
                }
                Text(city.summary(in: language))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.forward")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityHidden(true)
        }
        .foregroundStyle(LioTheme.ink)
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

/// One city's guide. The city can still be switched here without going back.
struct LioMetroCityGuideView: View {
    let language: LioLanguage
    @State var city: LioMetroCity
    @Environment(\.colorScheme) private var colorScheme

    init(language: LioLanguage, city: LioMetroCity) {
        self.language = language
        _city = State(initialValue: city)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text(language.text("City", "城市"))
                        .foregroundStyle(LioTheme.ink)
                    Spacer(minLength: 8)
                    Menu {
                        ForEach(LioMetroCity.allCases) { option in
                            Button(option.name(in: language)) { city = option }
                        }
                    } label: {
                        Label(city.name(in: language), systemImage: "chevron.down")
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Rectangle())
                    }
                    .accessibilityIdentifier("lio.metro.city")
                }

                if city.mapResource != nil {
                    NavigationLink {
                        LioMetroMapScreen(language: language, city: city)
                    } label: {
                        interactiveMapCard
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.metro.interactive")
                }

                VStack(alignment: .leading, spacing: 4) {
                    Link(destination: city.mapURL) {
                        Label(language.text("Official line map and stations", "官方线路图和车站"),
                              systemImage: "map")
                            .font(.headline)
                            .foregroundStyle(LioTheme.ink)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.metro.map")
                    Link(destination: city.guideURL) {
                        Label(language.text("Official ticket guide", "官方票务指南"), systemImage: "arrow.up.right")
                            .foregroundStyle(LioTheme.ink)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.metro.source")
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))

                ForEach(Array(LioMetroGuideSection.allCases.enumerated()), id: \.offset) { index, section in
                    instruction(step: index + 1, section)
                }
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .modifier(LioMetroNavigationTitle(title: city.name(in: language) + language.text(" Metro", "地铁"),
                                          colorScheme: colorScheme))
    }

    /// #1450: the bundled, zoomable line map, drawn from the operator's own station data.
    private var interactiveMapCard: some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            Image(systemName: "point.3.connected.trianglepath.dotted")
                .font(.title2.weight(.semibold))
                .foregroundStyle(LioTheme.onVermilion)
                .frame(width: 48, height: 48)
                .background(LioTheme.vermilion, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(language.text("Interactive line map", "可交互线路图")).font(.headline)
                Text(language.text("Zoom in, tap a station, then take a taxi or get directions.",
                                   "缩放查看，点车站可打车或导航。"))
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.forward")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityHidden(true)
        }
        .foregroundStyle(LioTheme.ink)
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func instruction(step: Int, _ section: LioMetroGuideSection) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text("\(step)")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(LioTheme.onVermilion)
                    .frame(width: 24, height: 24)
                    .background(LioTheme.vermilion, in: Circle())
                    .accessibilityHidden(true)
                Label(section.title(in: language), systemImage: section.symbol)
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)
            }
            RunReadableText(text: section.text(for: city, in: language), color: LioTheme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier(section.identifier)
        }
        .foregroundStyle(LioTheme.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

private struct LioMetroNavigationTitle: ViewModifier {
    let title: String
    let colorScheme: ColorScheme

    func body(content: Content) -> some View {
        content
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(LioTheme.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(colorScheme, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    RunReadableText(text: title, style: .headline, color: LioTheme.ink)
                        .fixedSize()
                        .accessibilityAddTraits(.isHeader)
                }
            }
    }
}
#endif
