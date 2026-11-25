#if os(iOS)
import CJRunClient
import SwiftUI

/// Metro maps (#1421, #1450): choose a city and its interactive line map opens straight away. No ticket or
/// security steps (JT 2026-11-25): tickets cannot be bought from here, and riders tap a bank card or use
/// the transit code in Alipay or the operator's app at the gate.
struct LioMetroGuideView: View {
    let language: LioLanguage
    @State private var finding = false
    @State private var found: LioMetroCity?
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var typeSize

    /// Two columns like the Tools page (JT 2026-11-25); one at accessibility text sizes.
    private var columns: Int { typeSize.isAccessibilitySize ? 1 : 2 }

    /// The cities in rows. A plain (not lazy) grid: every card is laid out, so accessibility checks can
    /// find each one, including those still below the fold.
    private var rows: [[LioMetroCity]] {
        let cities = LioMetroCity.allCases
        return stride(from: 0, to: cities.count, by: columns).map { Array(cities[$0..<min($0 + columns, cities.count)]) }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(language.text("Choose a city", "选择城市"))
                    .font(LioTheme.display(.title2).weight(.semibold))
                    .foregroundStyle(LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                // Cities only, no regions (JT 2026-11-25): the best-known first, then the rest by pinyin.
                Grid(horizontalSpacing: LioTheme.Spacing.sm, verticalSpacing: LioTheme.Spacing.sm) {
                    ForEach(rows, id: \.self) { row in
                        GridRow(alignment: .top) {
                            ForEach(row) { city in
                                NavigationLink {
                                    LioMetroMapScreen(language: language, city: city)
                                } label: {
                                    LioMetroCityCard(city: city, language: language)
                                }
                                .buttonStyle(.plain)
                                .accessibilityElement(children: .ignore)
                                .accessibilityLabel(city.name(in: language) + language.text(", ", "，") + city.detail(in: language))
                                .accessibilityAddTraits(.isButton)
                                .accessibilityIdentifier(city.identifier)
                            }
                            if row.count < columns {
                                Color.clear.gridCellUnsizedAxes([.horizontal, .vertical])
                            }
                        }
                    }
                }
            }
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.vertical, 18)
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
            LioMetroMapScreen(language: language, city: city)
        }
    }
}

/// One city card, laid out like a Tools card: an icon, the city's name, and below it the
/// Chinese name (to match signs) in English or the province in Chinese. Text wraps instead of truncating.
private struct LioMetroCityCard: View {
    let city: LioMetroCity
    let language: LioLanguage

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            // The Tools card's icon well. A Chinese initial here failed the Dynamic Type audit (#1450).
            Image(systemName: "tram.fill")
                .font(.title3.weight(.semibold))
                .foregroundStyle(LioTheme.vermilion)
                .frame(width: 36, height: 36)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityHidden(true)
            Text(city.name(in: language))
                .font(.headline)
                .foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
            Text(city.detail(in: language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .multilineTextAlignment(.leading)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .padding(LioTheme.Spacing.md)
        .frame(maxHeight: .infinity, alignment: .top)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

/// Every metro city in list order, searchable by English or Chinese name or province.
private struct LioMetroCityFinder: View {
    let language: LioLanguage
    let onSelect: (LioMetroCity) -> Void
    @State private var text = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(LioMetroCity.cities(matching: text)) { city in
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
                .accessibilityIdentifier("lio.metro.find." + city.id)
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
