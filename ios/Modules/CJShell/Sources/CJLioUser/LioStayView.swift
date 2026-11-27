#if os(iOS)
import SwiftUI

private struct LioAddPlaceToTripKey: EnvironmentKey {
    static let defaultValue: (@MainActor (LioPlace) -> Bool)? = nil
}

extension EnvironmentValues {
    /// What "Add to trip" does for a place from the place library (#2004, #2005): the host adds it to the traveller's
    /// saved trip and says whether that worked. Without it the button is not shown.
    var lioAddPlaceToTrip: (@MainActor (LioPlace) -> Bool)? {
        get { self[LioAddPlaceToTripKey.self] }
        set { self[LioAddPlaceToTripKey.self] = newValue }
    }
}

/// The notice shown for a moment after "Add to trip" (G4: "Added to your trip").
struct LioAddedToTripNotice: View {
    let language: LioLanguage

    var body: some View {
        Label(language.text("Added to your trip", "已加入行程"), systemImage: "checkmark.circle.fill")
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(LioTheme.onVermilion)
            .padding(.horizontal, LioTheme.Spacing.md)
            .frame(minHeight: 44)
            .background(LioTheme.vermilion, in: Capsule())
            .accessibilityIdentifier("lio.place.added")
    }
}

/// A banner for places that come from the development pack: unreviewed candidates, only ever in Debug builds.
struct LioDevelopmentDataBanner: View {
    let language: LioLanguage

    var body: some View {
        Label(language.text("Development data, not reviewed", "开发数据，未经人审"), systemImage: "wrench.and.screwdriver")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(LioTheme.inkSecondary)
            .padding(LioTheme.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
            .accessibilityIdentifier("lio.places.development-banner")
    }
}

/// A filter chip: a selected one is vermilion, the rest sit on the surface with a hairline.
struct LioFilterChip: View {
    let title: String
    let selected: Bool
    let identifier: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(selected ? LioTheme.onVermilion : LioTheme.ink)
                .padding(.horizontal, 14)
                .frame(minHeight: 36)
                .background(selected ? LioTheme.vermilion : LioTheme.surface, in: Capsule())
                .overlay { if !selected { Capsule().stroke(LioTheme.hairline) } }
        }
        .buttonStyle(.plain)
        .frame(minHeight: 44)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(identifier)
    }
}

/// Stay (#2004): only the hotels we have collected for foreign travellers, by price and star rating. No web-wide
/// search: what is not in the library is not here. A hotel opens its place page, and "Add to trip" goes through the
/// host's `lioAddPlaceToTrip`.
struct LioStayView: View {
    let language: LioLanguage
    var catalog: LioPlaceCatalog = .current

    @Environment(\.lioAddPlaceToTrip) private var addToTrip
    @Environment(\.colorScheme) private var colorScheme
    @State private var filter = LioStayFilter()
    @State private var opened: LioPlaceCatalog.Entry?
    @State private var addedID: String?

    private var results: [LioPlaceCatalog.Entry] { filter.apply(to: catalog) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) { content }
                .padding(LioTheme.Spacing.md)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
        .navigationTitle(language.text("Stay", "住"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .overlay(alignment: .bottom) {
            if addedID != nil {
                LioAddedToTripNotice(language: language).padding(.bottom, LioTheme.Spacing.lg)
                    .transition(.opacity)
            }
        }
        .sheet(item: $opened) { entry in
            NavigationStack {
                LioPlacePage(placeID: entry.id, language: language, repository: catalog.repository,
                             onAddToTrip: placePageAction)
            }
        }
    }

    @ViewBuilder private var content: some View {
        if catalog.isDevelopment { LioDevelopmentDataBanner(language: language) }
        if catalog.hotels.isEmpty {
            empty(libraryEmptyText, id: "lio.stay.library-empty")
        } else {
            filters
            resultList
        }
    }

    private var libraryEmptyText: String {
        language.text("We’re still collecting hotels for foreign travellers. Nothing to show yet.",
                      "适合外国游客的酒店还在收录中，暂时没有可看的。")
    }

    @ViewBuilder private var resultList: some View {
        let shown = results
        if shown.isEmpty {
            VStack(spacing: LioTheme.Spacing.sm) {
                empty(language.text("No hotels match your filters.", "没找到符合条件的酒店。"), id: "lio.stay.empty")
                Button(language.text("Change filters", "调整筛选")) { filter = LioStayFilter() }
                    .buttonStyle(LioSecondaryButtonStyle())
                    .accessibilityIdentifier("lio.stay.reset")
            }
        } else {
            ForEach(shown) { entry in card(entry) }
        }
    }

    /// "Add to trip" on the place page: the host's action, then the notice here.
    private var placePageAction: (@MainActor (LioPlace) -> Void)? {
        guard let add = addToTrip else { return nil }
        return { place in
            if add(place) { showAdded(place.id) }
        }
    }

    // MARK: Filters

    private var filters: some View {
        VStack(alignment: .leading, spacing: 4) {
            cityChips
            priceChips
            if LioStayFilter.offersStars(in: catalog) { starChips }
        }
    }

    private var cityChips: some View {
        let cities: [LioStayFilter.City] = LioStayFilter.cities
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: LioTheme.Spacing.xs) {
                LioFilterChip(title: language.text("All cities", "全部城市"), selected: filter.city == nil,
                              identifier: "lio.stay.city.all") { filter.city = nil }
                ForEach(cities) { city in
                    LioFilterChip(title: language.text(city.en, city.zh), selected: filter.city == city.id,
                                  identifier: "lio.stay.city." + city.id) { filter.city = city.id }
                }
            }
        }
        .accessibilityIdentifier("lio.stay.filters.city")
    }

    private var priceChips: some View {
        let bands: [LioPlaceCatalog.PriceBand] = LioPlaceCatalog.PriceBand.allCases
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: LioTheme.Spacing.xs) {
                LioFilterChip(title: language.text("Any price", "不限价位"), selected: filter.band == nil,
                              identifier: "lio.stay.band.any") { filter.band = nil }
                ForEach(bands, id: \.rawValue) { band in
                    LioFilterChip(title: band.title(language), selected: filter.band == band,
                                  identifier: "lio.stay.band." + band.rawValue) { filter.band = band }
                }
            }
        }
        .accessibilityIdentifier("lio.stay.filters.price")
    }

    private var starChips: some View {
        let stars: [Int] = [3, 4, 5]
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: LioTheme.Spacing.xs) {
                LioFilterChip(title: language.text("Any rating", "不限星级"), selected: filter.minimumStar == nil,
                              identifier: "lio.stay.star.any") { filter.minimumStar = nil }
                ForEach(stars, id: \.self) { star in
                    LioFilterChip(title: starTitle(star), selected: filter.minimumStar == star,
                                  identifier: "lio.stay.star.\(star)") { filter.minimumStar = star }
                }
            }
        }
        .accessibilityIdentifier("lio.stay.filters.star")
    }

    private func starTitle(_ star: Int) -> String {
        language == .english ? "\(star)★ and up" : "\(star) 星及以上"
    }

    private func empty(_ text: String, id: String) -> some View {
        Text(text)
            .foregroundStyle(LioTheme.inkSecondary)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity, minHeight: 80)
            .accessibilityIdentifier(id)
    }

    // MARK: Cards

    private func card(_ entry: LioPlaceCatalog.Entry) -> some View {
        let place = entry.place
        return VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Button { opened = entry } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(place.name(language)).font(.headline).multilineTextAlignment(.leading)
                    if let other = place.secondaryName(language) {
                        Text(other).font(.subheadline).foregroundStyle(LioTheme.inkSecondary).multilineTextAlignment(.leading)
                    }
                    if let line = facts(entry) {
                        Text(line).font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.jade)
                    }
                    if let intro = place.introShort(language) {
                        Text(intro).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                            .multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.stay.open." + entry.id)
            if let addToTrip {
                Button {
                    if addToTrip(place) { showAdded(place.id) }
                } label: {
                    Label(LioPlaceCopy.addToTrip.text(language), systemImage: "plus.circle")
                }
                .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
                .accessibilityIdentifier("lio.stay.add." + entry.id)
            }
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    /// "★★★★ · ¥1,000–2,000 a night", with whatever of the two the library has.
    private func facts(_ entry: LioPlaceCatalog.Entry) -> String? {
        var parts: [String] = []
        if let star = entry.extras.star { parts.append(String(repeating: "★", count: star)) }
        if let band = entry.extras.priceBand { parts.append(band.title(language) + language.text(" a night", " / 晚")) }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private func showAdded(_ id: String) {
        withAnimation(LioTheme.Motion.change) { addedID = id }
        Task {
            try? await Task.sleep(for: .seconds(2))
            if addedID == id { withAnimation(LioTheme.Motion.change) { addedID = nil } }
        }
    }
}
#endif
