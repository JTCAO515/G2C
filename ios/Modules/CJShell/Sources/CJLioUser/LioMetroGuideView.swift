#if os(iOS)
import CJRunClient
import SwiftUI

struct LioMetroGuideView: View {
    let language: LioLanguage
    @Environment(\.colorScheme) private var colorScheme
    @State private var city = LioMetroCity.beijing

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

                Link(destination: city.mapURL) {
                    Label(language.text("Official line map and stations", "官方线路图和车站"),
                          systemImage: "map")
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

                instruction(language.text("Buy a ticket", "买票"), text: city.buying(in: language),
                            icon: "ticket", id: "ticket")
                instruction(language.text("Security check", "安检"), text: city.security(in: language),
                            icon: "checkmark.shield", id: "security")
                instruction(language.text("Enter and exit", "进站与出站"), text: city.entering(in: language),
                            icon: "tram", id: "gates")
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Metro Guide", "地铁指南"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .principal) {
                RunReadableText(text: language.text("Metro Guide", "地铁指南"), style: .headline, color: LioTheme.ink)
                    .fixedSize()
                    .accessibilityAddTraits(.isHeader)
            }
        }
    }

    private func instruction(_ title: String, text: String, icon: String, id: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: icon)
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            RunReadableText(text: text, color: LioTheme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier("lio.metro." + id)
        }
        .foregroundStyle(LioTheme.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}
#endif
