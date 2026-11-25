#if os(iOS)
import CJRunClient
import SwiftUI

/// Metro guide (#1421): choose a city first, then read how to buy a ticket, pass security and use
/// the gates. Every bundled city (#1450) opens an interactive line map; the cities whose
/// operator guidance was checked also link the official map and ticket guide.
struct LioMetroGuideView: View {
    let language: LioLanguage
    @State private var finding = false
    @State private var found: LioMetroCity?
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(language.text("Choose a city", "选择城市"))
                    .font(LioTheme.display(.title2).weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                ForEach(LioMetroRegion.allCases, id: \.self) { region in
                    let cities = LioMetroCity.cities(in: region)
                    if !cities.isEmpty {
                        Text(region.name(in: language))
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(LioTheme.inkSecondary)
                            .padding(.top, LioTheme.Spacing.xs)
                            .accessibilityAddTraits(.isHeader)
                        ForEach(cities) { city in
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
                }
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .modifier(LioMetroNavigationTitle(title: language.text("Metro Guide", "地铁指南"), colorScheme: colorScheme))
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { finding = true } label: {
                    Label(language.text("Find a city", "查找城市"), systemImage: "magnifyingglass")
                }
                .accessibilityIdentifier("lio.metro.city.find")
            }
        }
        .sheet(isPresented: $finding) {
            LioMetroCityFinder(language: language) { city in
                finding = false
                found = city
            }
        }
        .navigationDestination(item: $found) { city in
            LioMetroCityGuideView(language: language, city: city)
        }
    }

    private func cityCard(_ city: LioMetroCity) -> some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            // White on vermilion: the theme guarantees this pair's contrast (the audit failed 天 on sunken).
            Text(city.nativeName.prefix(1))
                .font(LioTheme.display(.title2).weight(.bold))
                .foregroundStyle(LioTheme.onVermilion)
                .frame(width: 48, height: 48)
                .background(LioTheme.vermilion, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
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
                    .lineLimit(nil)
                    .frame(maxWidth: .infinity, alignment: .leading)
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

/// Every metro city, searchable by English or Chinese name or province.
private struct LioMetroCityFinder: View {
    let language: LioLanguage
    let onSelect: (LioMetroCity) -> Void
    @State private var text = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                ForEach(LioMetroRegion.allCases, id: \.self) { region in
                    let cities = LioMetroCity.cities(in: region, matching: text)
                    if !cities.isEmpty {
                        Section(region.name(in: language)) {
                            ForEach(cities) { city in
                                Button { onSelect(city) } label: {
                                    HStack {
                                        Text(city.name(in: language)).foregroundStyle(LioTheme.ink)
                                        Spacer(minLength: 8)
                                        Text(language == .english ? city.nameZH : city.provinceZH)
                                            .foregroundStyle(LioTheme.inkSecondary)
                                    }
                                    .frame(minHeight: 44)
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
            .searchable(text: $text, placement: .navigationBarDrawer(displayMode: .always),
                        prompt: language.text("City or province", "城市或省份"))
            .navigationTitle(language.text("Find a city", "查找城市"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(language.text("Close", "关闭")) { dismiss() } }
            }
        }
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
                        // Region first, then its cities: 41 in one menu would run off the screen.
                        ForEach(LioMetroRegion.allCases, id: \.self) { region in
                            Menu(region.name(in: language)) {
                                ForEach(LioMetroCity.cities(in: region)) { option in
                                    Button(option.name(in: language)) { city = option }
                                }
                            }
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

                if let guide = city.guide {
                VStack(alignment: .leading, spacing: 4) {
                    Link(destination: guide.mapURL) {
                        Label(language.text("Official line map and stations", "官方线路图和车站"),
                              systemImage: "map")
                            .font(.headline)
                            .foregroundStyle(LioTheme.ink)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.metro.map")
                    Link(destination: guide.guideURL) {
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
                }

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
