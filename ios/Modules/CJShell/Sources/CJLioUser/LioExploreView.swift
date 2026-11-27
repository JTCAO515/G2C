#if os(iOS)
import SwiftUI

/// Explore (#2005): restaurants, sights and shops near the traveller that are also in our place library, best first.
/// The search is AMap's (`LioNearbyService`, the same relay as Nearby); only results that are places we have collected
/// are shown, so this is a short list of recommendations rather than everything around. Sight booking and the menu
/// helper open from here. "Add to trip" goes through the host's `lioAddPlaceToTrip`.
struct LioExploreView: View {
    let language: LioLanguage
    let service: LioNearbyService
    var catalog: LioPlaceCatalog = .current

    private enum Phase: Equatable {
        case locating, searching, ready
        case failed(LioNearbyFailure)
    }

    @Environment(\.lioAddPlaceToTrip) private var addToTrip
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dismiss) private var dismiss
    @Environment(LioRouter.self) private var router: LioRouter?
    @State private var kinds = Set(LioExploreGuide.Kind.allCases)
    @State private var radius = 1000
    @State private var here: LioTaxiPlace?
    @State private var phase = Phase.locating
    @State private var items: [LioExploreGuide.Item] = []
    @State private var opened: LioPlaceCatalog.Entry?
    @State private var addedID: String?

    /// Only the kinds Explore offers count: a library of hotels alone is an empty guide here.
    private var libraryIsEmpty: Bool {
        !catalog.entries.contains { LioExploreGuide.Kind($0.place.category) != nil }
    }

    private var query: LioNearbyQuery? {
        guard let here, !kinds.isEmpty, !libraryIsEmpty else { return nil }
        return LioExploreGuide.query(center: here.coordinate, kinds: kinds, radius: radius)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) { pageContent }
                .padding(LioTheme.Spacing.md)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
        .navigationTitle(language.text("Explore", "吃喝玩"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .overlay(alignment: .bottom) {
            if addedID != nil {
                LioAddedToTripNotice(language: language).padding(.bottom, LioTheme.Spacing.lg).transition(.opacity)
            }
        }
        .sheet(item: $opened) { entry in
            NavigationStack {
                LioPlacePage(placeID: entry.id, language: language, repository: catalog.repository,
                             onAddToTrip: placePageAction)
            }
        }
        .task { if !libraryIsEmpty { await locate() } }
        .task(id: query) { await search() }
    }

    @ViewBuilder private var pageContent: some View {
        if catalog.isDevelopment { LioDevelopmentDataBanner(language: language) }
        if libraryIsEmpty {
            note(libraryEmptyText, id: "lio.explore.library-empty")
        } else {
            filters
            content
        }
        entries
    }

    private var libraryEmptyText: String {
        language.text("We’re still collecting places worth recommending. Nothing to show yet.",
                      "值得推荐的地点还在收录中，暂时没有可看的。")
    }

    /// "Add to trip" on the place page: the host's action, then the notice here.
    private var placePageAction: (@MainActor (LioPlace) -> Void)? {
        guard let add = addToTrip else { return nil }
        return { place in
            if add(place) { showAdded(place.id) }
        }
    }

    // MARK: Filters

    private var kindList: [LioExploreGuide.Kind] { LioExploreGuide.Kind.allCases }

    private var filters: some View {
        VStack(alignment: .leading, spacing: 4) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: LioTheme.Spacing.xs) {
                    ForEach(kindList, id: \.self) { kind in
                        LioFilterChip(title: kind.title(language), selected: kinds.contains(kind),
                                      identifier: "lio.explore.kind." + kind.identifier) {
                            if kinds.contains(kind) { kinds.remove(kind) } else { kinds.insert(kind) }
                        }
                    }
                }
            }
            Picker(language.text("Distance", "距离"), selection: $radius) {
                ForEach([1000, 3000], id: \.self) { value in Text("\(value / 1000) km").tag(value) }
            }
            .pickerStyle(.segmented)
            .frame(maxWidth: 220)
            .accessibilityIdentifier("lio.explore.radius")
        }
    }

    // MARK: Results

    @ViewBuilder private var content: some View {
        switch phase {
        case .locating, .searching:
            ProgressView(phase == .locating ? language.text("Finding where you are…", "正在确定你的位置…")
                                            : language.text("Looking around…", "正在查找附近…"))
                .frame(maxWidth: .infinity, minHeight: 80)
        case .failed(let failure):
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                Text(message(failure)).accessibilityIdentifier("lio.explore.problem")
                if failure == .consentNeeded {
                    LioLocationConsentButton(language: language) { Task { await locate() } }
                }
                Button(language.text("Try again", "重试")) { Task { here == nil ? await locate() : await search() } }
                    .frame(minHeight: 44)
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        case .ready:
            if kinds.isEmpty {
                note(language.text("Choose at least one kind of place.", "请至少选择一类地点。"), id: "lio.explore.choose")
            } else if items.isEmpty {
                VStack(spacing: LioTheme.Spacing.sm) {
                    note(language.text("No places in our guide nearby.", "附近暂无收录地点。"), id: "lio.explore.empty")
                    Button(language.text("Search another area", "换个地方找")) { searchAnotherArea() }
                        .buttonStyle(LioSecondaryButtonStyle())
                        .accessibilityIdentifier("lio.explore.change-area")
                }
            } else {
                ForEach(items) { item in card(item) }
            }
        }
    }

    private func card(_ item: LioExploreGuide.Item) -> some View {
        let place = item.entry.place
        return VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Button { opened = item.entry } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(place.name(language)).font(.headline).multilineTextAlignment(.leading)
                    if let other = place.secondaryName(language) {
                        Text(other).font(.subheadline).foregroundStyle(LioTheme.inkSecondary).multilineTextAlignment(.leading)
                    }
                    Text(([item.kind.title(language)] + distance(item.metres)).joined(separator: " · "))
                        .font(.subheadline.weight(.semibold)).foregroundStyle(LioTheme.jade)
                    if let intro = place.introShort(language) {
                        Text(intro).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                            .multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.explore.open." + item.id)
            if let addToTrip {
                Button {
                    if addToTrip(place) { showAdded(place.id) }
                } label: {
                    Label(LioPlaceCopy.addToTrip.text(language), systemImage: "plus.circle")
                }
                .buttonStyle(LioSecondaryButtonStyle(fullWidth: false))
                .accessibilityIdentifier("lio.explore.add." + item.id)
            }
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func distance(_ metres: Int?) -> [String] {
        guard let metres else { return [] }
        return [metres < 1000 ? "\(metres) m" : String(format: "%.1f km", Double(metres) / 1000)]
    }

    private func note(_ text: String, id: String) -> some View {
        Text(text)
            .foregroundStyle(LioTheme.inkSecondary)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity, minHeight: 80)
            .accessibilityIdentifier(id)
    }

    // MARK: Sight booking and the menu helper

    /// The tools Explore opens: shown only when this build has them and the router can open them.
    private var entries: some View {
        let shown = visibleTools
        let all: [(tool: LioTool, symbol: String, title: String, id: String)] = [
            (.attractionBooking, "ticket", language.text("Sight booking", "景点预约"), "lio.explore.booking"),
            (.menuOrder, "fork.knife", language.text("Order from a menu", "点餐"), "lio.explore.menu"),
        ]
        let tools = all.filter { shown.contains($0.tool) }
        return Group {
            if router?.toolsShown == true, !tools.isEmpty {
                VStack(spacing: LioTheme.Spacing.xs) {
                    ForEach(tools, id: \.id) { entry in
                        Button {
                            if let route = LioRoute(tool: entry.tool), router?.open(route) == true { dismiss() }
                        } label: {
                            Label(entry.title, systemImage: entry.symbol)
                        }
                        .buttonStyle(LioSecondaryButtonStyle())
                        .accessibilityIdentifier(entry.id)
                    }
                }
            }
        }
    }

    private var visibleTools: Set<LioTool> {
        var context = LioToolContext(language: language)
        context.taxiEntry = taxiEntry
        return Set(LioToolCatalog.visible(context.availability()))
    }

    // MARK: Loading

    private func locate() async {
        phase = .locating
        do {
            let location = try await service.currentLocation()
            try Task.checkCancellation()
            here = location
        } catch is CancellationError {
            return
        } catch {
            phase = .failed(error as? LioNearbyFailure ?? .unavailable)
        }
    }

    private func search() async {
        guard let query else {
            if here != nil { items = []; phase = .ready }
            return
        }
        phase = .searching
        do {
            let found = try await service.search(query)
            try Task.checkCancellation()
            items = LioExploreGuide.intersect(found, with: catalog, kinds: kinds)
            phase = .ready
        } catch is CancellationError {
            return
        } catch {
            items = []
            phase = .failed(error as? LioNearbyFailure ?? .unavailable)
        }
    }

    /// "Search another area": a wider circle first, then ask for the location again.
    private func searchAnotherArea() {
        if radius < 3000 { radius = 3000 } else { Task { await locate() } }
    }

    private func message(_ failure: LioNearbyFailure) -> String {
        switch failure {
        case .locationDenied: language.text("Allow location access to see places near you.", "请允许使用位置，才能查看你附近的地点。")
        case .signInRequired: language.text("Sign in again, then try again.", "请重新登录后重试。")
        case .notEnabled: language.text("Nearby isn’t available for this account yet.", "此账号暂未开通附近。")
        case .quotaExceeded: language.text("Nearby has reached its lookup limit for now. Try again later.", "附近的查找次数已达上限，请稍后再试。")
        case .rateLimited: language.text("Too many lookups right now. Try again later.", "查找太频繁，请稍后再试。")
        case .timedOut: language.text("This took too long. Try again.", "查找超时，请重试。")
        case .unavailable: language.text("Nearby isn’t available right now. Try again.", "附近暂时不可用，请重试。")
        case .consentNeeded: language.text("Use your location to see places around you.", "使用你的位置，才能显示周围的地点。")
        }
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
