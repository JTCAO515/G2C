#if os(iOS)
import MapKit
import SwiftUI
import UIKit

/// Nearby (#1421 item 5, #1428): places around the traveller from the Hong Kong NEARBY.1 relay,
/// on a map and in a list, with taxi, directions and a Chinese address card for each place.
struct LioNearbyService: Sendable {
    let currentLocation: @MainActor @Sendable () async throws -> LioTaxiPlace
    let search: @MainActor @Sendable (LioNearbyQuery) async throws -> [LioNearbyPOI]
    let reverse: @MainActor @Sendable (LioTaxiPlace.Coordinate) async throws -> String?
}

extension LioNearbyService {
    @MainActor static func internalBeta(relay: LioNearbyRelayClient) -> Self {
        LioNearbyService(currentLocation: {
            try relay.requireCurrentSession()
            do { return try await LioTaxiPickupLocation().pickup() }
            catch LioTaxiFailure.locationDenied { throw LioNearbyFailure.locationDenied }
        }, search: { query in
            try await relay.search(query)
        }, reverse: { center in
            try await relay.reverse(center)
        })
    }
}

private struct LioNearbyServiceKey: EnvironmentKey {
    static let defaultValue: LioNearbyService? = nil
}

extension EnvironmentValues {
    var lioNearbyService: LioNearbyService? {
        get { self[LioNearbyServiceKey.self] }
        set { self[LioNearbyServiceKey.self] = newValue }
    }
}

struct LioNearbyView: View {
    let language: LioLanguage
    let service: LioNearbyService
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @State private var here: LioTaxiPlace?
    @State private var address: String?
    @State private var categories = Set(LioNearbyPlace.Category.leisure)
    /// Essentials are searched one kind at a time (luggage storage only on its own).
    @State private var essential: LioNearbyPlace.Category?
    private let essentialsEnabled = LioNearbyPlace.essentialsEnabled
    @State private var radius = 1000
    @State private var nearest = false
    @State private var places: [LioNearbyPOI] = []
    @State private var phase = LioNearbyPhase.locating
    @State private var selected: LioNearbyPOI?
    @State private var camera: MapCameraPosition = .automatic

    private var query: LioNearbyQuery? {
        here.map { LioNearbyQuery(center: $0.coordinate, categories: essential.map { [$0] } ?? categories,
                                  radius: radius, nearest: nearest) }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                locationRow
                filters
                map
                content
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .tint(LioTheme.vermilion)
        .navigationTitle(language.text("Nearby", "附近"))
        .navigationBarTitleDisplayMode(.inline)
        .task { await locate() }
        .task(id: query) { await search() }
        .navigationDestination(item: $selected) { place in
            LioNearbyPlaceView(language: language, place: place, taxiEntry: taxiEntry)
        }
    }

    private var locationRow: some View {
        HStack(spacing: 8) {
            Image(systemName: "location.fill").foregroundStyle(LioTheme.vermilion).accessibilityHidden(true)
            Text(address ?? here?.addressZH ?? language.text("Finding where you are…", "正在确定你的位置…"))
                .font(.subheadline)
                .foregroundStyle(LioTheme.inkSecondary)
                .lineLimit(2)
            Spacer(minLength: 8)
            Button {
                Task { await locate() }
            } label: {
                Image(systemName: "arrow.clockwise").frame(width: 44, height: 44)
            }
            .accessibilityLabel(language.text("Update location", "重新定位"))
            .accessibilityIdentifier("lio.nearby.relocate")
        }
        .accessibilityIdentifier("lio.nearby.location")
    }

    private var filters: some View {
        VStack(alignment: .leading, spacing: 8) {
            if essentialsEnabled {
                Picker(language.text("Kind of places", "地点类型"), selection: Binding(
                    get: { essential != nil },
                    set: { essentials in essential = essentials ? (essential ?? .atm) : nil })) {
                    Text(language.text("Eat & explore", "吃喝玩逛")).tag(false)
                    Text(language.text("Essentials", "必需品")).tag(true)
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("lio.nearby.group")
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(essential == nil ? LioNearbyPlace.Category.leisure : LioNearbyPlace.Category.essentials,
                            id: \.self) { category in
                        let on = essential.map { $0 == category } ?? categories.contains(category)
                        Button {
                            if essential != nil { essential = category }
                            else if on { categories.remove(category) } else { categories.insert(category) }
                        } label: {
                            Text(category.title(language))
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(on ? LioTheme.onVermilion : LioTheme.ink)
                                .padding(.horizontal, 14)
                                .frame(minHeight: 36)
                                .background(on ? LioTheme.vermilion : LioTheme.surface, in: Capsule())
                                .overlay { if !on { Capsule().stroke(LioTheme.hairline) } }
                        }
                        .buttonStyle(.plain)
                        .frame(minHeight: 44)
                        .accessibilityAddTraits(on ? .isSelected : [])
                        .accessibilityIdentifier("lio.nearby.category." + category.rawValue)
                    }
                }
            }
            HStack(spacing: 12) {
                Picker(language.text("Distance", "范围"), selection: $radius) {
                    ForEach(LioNearbyQuery.radii, id: \.self) { value in
                        Text(value < 1000 ? "\(value) m" : "\(value / 1000) km").tag(value)
                    }
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("lio.nearby.radius")
                Picker(language.text("Order", "排序"), selection: $nearest) {
                    Text(language.text("Best", "推荐")).tag(false)
                    Text(language.text("Closest", "最近")).tag(true)
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 150)
                .accessibilityIdentifier("lio.nearby.sort")
            }
        }
    }

    private var map: some View {
        Map(position: $camera) {
            UserAnnotation()
            ForEach(places) { place in
                Marker(place.name, systemImage: symbol(place.category),
                       coordinate: CLLocationCoordinate2D(latitude: place.coordinate.latitude,
                                                          longitude: place.coordinate.longitude))
                .tint(LioTheme.vermilion)
            }
        }
        .frame(height: 220)
        .clipShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .overlay { RoundedRectangle(cornerRadius: LioTheme.Radius.card).stroke(LioTheme.hairline).allowsHitTesting(false) }
        .accessibilityLabel(language.text("Map of nearby places", "附近地点地图"))
        .accessibilityIdentifier("lio.nearby.map")
    }

    @ViewBuilder private var content: some View {
        switch phase {
        case .locating, .searching:
            ProgressView(phase == .locating ? language.text("Finding where you are…", "正在确定你的位置…")
                                            : language.text("Looking around…", "正在查找附近…"))
                .frame(maxWidth: .infinity, minHeight: 80)
        case .failed(let failure):
            VStack(alignment: .leading, spacing: 8) {
                Text(message(failure)).accessibilityIdentifier("lio.nearby.problem")
                if failure == .consentNeeded {
                    LioLocationConsentButton(language: language) { Task { await locate() } }
                }
                HStack {
                    if failure == .locationDenied {
                        Button(language.text("Open Settings", "打开设置")) {
                            if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                        }
                    }
                    Button(language.text("Try again", "重试")) { Task { here == nil ? await locate() : await search() } }
                }
                .frame(minHeight: 44)
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        case .ready:
            if let essential {
                // NEARBY.2 fixed wording: ATMs never claimed to take foreign cards; luggage found by name only.
                Text(essential.heading(language))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.nearby.essential-heading")
            }
            if places.isEmpty {
                Text(essential == nil && categories.isEmpty ? language.text("Choose at least one kind of place.", "请至少选择一类地点。")
                                        : language.text("Nothing found in this range. Try a larger distance.",
                                                        "这个范围内没有找到，试试扩大范围。"))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .frame(maxWidth: .infinity, minHeight: 80)
                    .accessibilityIdentifier("lio.nearby.empty")
            }
            ForEach(places) { place in
                Button { selected = place } label: { row(place) }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.nearby.place")
            }
            Text(language.text("Places from Gaode (AMap)", "地点信息来自高德"))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
        }
    }

    private func row(_ place: LioNearbyPOI) -> some View {
        HStack(alignment: .top, spacing: LioTheme.Spacing.sm) {
            Image(systemName: symbol(place.category))
                .foregroundStyle(LioTheme.vermilion)
                .frame(width: 36, height: 36)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(place.name).font(.headline)
                Text(details(place)).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                if let address = place.address {
                    Text(address).font(.footnote).foregroundStyle(LioTheme.inkSecondary).lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.forward").font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                .accessibilityHidden(true)
        }
        .padding(LioTheme.Spacing.sm)
        .frame(maxWidth: .infinity, minHeight: 60, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func details(_ place: LioNearbyPOI) -> String {
        var parts = [String]()
        if let category = place.category { parts.append(category.title(language)) }
        if let meters = place.meters { parts.append(meters < 1000 ? "\(meters) m" : String(format: "%.1f km", Double(meters) / 1000)) }
        if let rating = place.rating { parts.append("★ " + rating) }
        if let cost = place.cost { parts.append(language.text("about ", "人均") + cost) }
        return parts.joined(separator: " · ")
    }

    private func symbol(_ category: LioNearbyPlace.Category?) -> String {
        switch category {
        case .food: "fork.knife"
        case .coffee: "cup.and.saucer.fill"
        case .sights: "camera.fill"
        case .shopping: "bag.fill"
        case .atm: "banknote"
        case .pharmacy: "cross.case.fill"
        case .toilet: "toilet.fill"
        case .luggage: "suitcase.fill"
        case nil: "mappin"
        }
    }

    private func locate() async {
        let previous = here
        let previousPhase = phase
        phase = .locating
        do {
            let location = try await service.currentLocation()
            try Task.checkCancellation()
            here = location
            if location.coordinate == previous?.coordinate {
                // Same spot: the search task keyed by the query does not rerun, and the address is unchanged.
                switch phase.afterRelocatingToSameSpot(before: previousPhase) {
                case .keep: break
                case .show(let restored): phase = restored
                case .searchAgain: await search()
                }
                return
            }
            address = try? await service.reverse(location.coordinate)
        } catch is CancellationError {
            return
        } catch {
            phase = .failed(error as? LioNearbyFailure ?? .unavailable)
        }
    }

    private func search() async {
        guard let query else { return }
        phase = .searching
        do {
            let found = try await service.search(query)
            try Task.checkCancellation()
            places = found
            phase = .ready
            camera = .automatic
        } catch is CancellationError {
            return
        } catch {
            places = []
            phase = .failed(error as? LioNearbyFailure ?? .unavailable)
        }
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
}

/// One place: name, details, and the actions a traveller needs next.
struct LioNearbyPlaceView: View {
    let language: LioLanguage
    let place: LioNearbyPOI
    let taxiEntry: LioTaxiEntry?
    @State private var showsAddress = false
    @State private var directionsUnavailable = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(place.name).font(LioTheme.display(.title2).weight(.bold))
                    if let address = place.address { Text(address).foregroundStyle(LioTheme.inkSecondary) }
                    if let hours = place.hours {
                        Label(hours, systemImage: "clock").font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    }
                    HStack(spacing: 12) {
                        if let rating = place.rating { Label(rating, systemImage: "star.fill") }
                        if let cost = place.cost { Text(language.text("About \(cost) per person", "人均约 \(cost)")) }
                    }
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
                }
                if let taxiEntry {
                    NavigationLink {
                        LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                    recentStore: taxiEntry.recentStore, destination: place.taxiPlace)
                    } label: {
                        action(language.text("Taxi here", "打车去这里"), symbol: "car.fill", prominent: true)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.nearby.action.taxi")
                }
                Button(action: directions) {
                    action(language.text("Directions in AMap", "用高德地图导航"), symbol: "arrow.triangle.turn.up.right.diamond.fill")
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.nearby.action.directions")
                if directionsUnavailable {
                    Text(language.text("Install AMap or Apple Maps to get directions.", "请安装高德地图或苹果地图后再导航。"))
                        .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
                Button { showsAddress = true } label: {
                    action(language.text("Show the address in Chinese", "出示中文地址"), symbol: "character.bubble")
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.nearby.action.address")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .navigationTitle(place.name)
        .navigationBarTitleDisplayMode(.inline)
        .fullScreenCover(isPresented: $showsAddress) {
            LioNearbyAddressCard(language: language, place: place)
        }
    }

    private func action(_ title: String, symbol: String, prominent: Bool = false) -> some View {
        Label(title, systemImage: symbol)
            .font(.headline)
            .foregroundStyle(prominent ? LioTheme.onVermilion : LioTheme.ink)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(prominent ? LioTheme.vermilion : LioTheme.surface,
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .overlay {
                if !prominent {
                    RoundedRectangle(cornerRadius: LioTheme.Radius.card).stroke(LioTheme.hairline).allowsHitTesting(false)
                }
            }
    }

    /// AMap first (GCJ-02 coordinates, `dev=0`), then Apple Maps; nothing is sent to our servers.
    private func directions() {
        let lat = place.coordinate.latitude, lng = place.coordinate.longitude
        var amap = URLComponents(string: "iosamap://path")!
        amap.queryItems = [.init(name: "sourceApplication", value: "Go2China"), .init(name: "dlat", value: "\(lat)"),
                           .init(name: "dlon", value: "\(lng)"), .init(name: "dname", value: place.name),
                           .init(name: "dev", value: "0"), .init(name: "t", value: "0")]
        var apple = URLComponents(string: "https://maps.apple.com/")!
        apple.queryItems = [.init(name: "daddr", value: "\(lat),\(lng)"), .init(name: "q", value: place.name)]
        Task { @MainActor in
            if let url = amap.url, await UIApplication.shared.open(url) { return }
            if let url = apple.url, await UIApplication.shared.open(url) { return }
            directionsUnavailable = true
        }
    }
}

private struct LioNearbyAddressCard: View {
    let language: LioLanguage
    let place: LioNearbyPOI
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(place.name).font(LioTheme.display(.largeTitle).weight(.bold))
                    if let address = place.address { Text(address).font(.title2.weight(.semibold)) }
                    Text(language.text("Please take me here.", "请带我去这里。")).font(.title3)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(24)
            }
            .background(LioTheme.paper)
            .foregroundStyle(LioTheme.ink)
            .navigationTitle(language.text("Show the address", "出示中文地址"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button(language.text("Close", "关闭")) { dismiss() } }
            }
        }
        .onAppear { UIApplication.shared.isIdleTimerDisabled = true }
        .onDisappear { UIApplication.shared.isIdleTimerDisabled = false }
    }
}

#if DEBUG
extension LioNearbyService {
    static var previewFromArguments: LioNearbyService? {
        guard ProcessInfo.processInfo.arguments.contains("--lio-nearby-preview") else { return nil }
        let denied = ProcessInfo.processInfo.arguments.contains("--lio-nearby-preview-location-denied")
        return LioNearbyService(currentLocation: {
            if denied { throw LioNearbyFailure.locationDenied }
            return .init(nameZH: "王府井", nameEN: "Wangfujing", addressZH: "北京市东城区王府井大街",
                         coordinate: .init(latitude: 39.9110, longitude: 116.4102, referenceSystem: .wgs84))
        }, search: { query in
            let all: [LioNearbyPOI] = [
                .init(id: "1", name: "四季民福烤鸭店", address: "东华门大街", category: .food,
                      coordinate: .init(latitude: 39.9142, longitude: 116.4035, referenceSystem: .gcj02),
                      meters: 420, rating: "4.7", cost: "¥180", hours: "10:30-22:00", photo: nil),
                .init(id: "2", name: "街角咖啡", address: nil, category: .coffee,
                      coordinate: .init(latitude: 39.9100, longitude: 116.4120, referenceSystem: .gcj02),
                      meters: 260, rating: "4.5", cost: nil, hours: nil, photo: nil),
                .init(id: "3", name: "故宫博物院", address: "景山前街4号", category: .sights,
                      coordinate: .init(latitude: 39.9163, longitude: 116.3972, referenceSystem: .gcj02),
                      meters: 1250, rating: "4.9", cost: "¥60", hours: "08:30-17:00", photo: nil),
                .init(id: "4", name: "示例银行ATM(王府井)", address: "王府井大街", category: .atm,
                      coordinate: .init(latitude: 39.9125, longitude: 116.4108, referenceSystem: .gcj02),
                      meters: 150, rating: nil, cost: nil, hours: nil, photo: nil),
                .init(id: "5", name: "示例大药房", address: "金鱼胡同", category: .pharmacy,
                      coordinate: .init(latitude: 39.9131, longitude: 116.4117, referenceSystem: .gcj02),
                      meters: 310, rating: nil, cost: nil, hours: "08:00-22:00", photo: nil),
                .init(id: "6", name: "公共厕所(王府井步行街)", address: "王府井步行街", category: .toilet,
                      coordinate: .init(latitude: 39.9118, longitude: 116.4111, referenceSystem: .gcj02),
                      meters: 90, rating: nil, cost: nil, hours: nil, photo: nil),
                .init(id: "7", name: "示例行李寄存", address: "王府井大街", category: .luggage,
                      coordinate: .init(latitude: 39.9140, longitude: 116.4100, referenceSystem: .gcj02),
                      meters: 480, rating: nil, cost: nil, hours: nil, photo: nil),
            ]
            let matching = all.filter { $0.category.map(query.categories.contains) ?? false && ($0.meters ?? 0) <= query.radius }
            return query.nearest ? matching.sorted { ($0.meters ?? .max) < ($1.meters ?? .max) } : matching
        }, reverse: { _ in "北京市东城区王府井大街" })
    }
}
#endif
#endif
