#if os(iOS)
import SwiftUI

/// Back to Hotel (#1573): the stay hotel with one tap to take a DiDi back (#1451) or show the driver (#1550),
/// plus the show cards (#1572). Without a hotel the traveller picks one from the trip or searches for it.
struct LioReturnHotelView: View {
    let language: LioLanguage
    let store: LioReturnHotelStore?
    /// Taxi search and the DiDi hand-off; nil when taxi is not available in this build.
    let taxiEntry: LioTaxiEntry?
    @State private var hotel: LioStayHotel?
    @State private var room = ""
    @State private var sheet: Sheet?
    @State private var notice: String?

    private enum Sheet: String, Identifiable {
        case taxi, driver, choose
        var id: Self { self }
    }

    init(language: LioLanguage, store: LioReturnHotelStore?, taxiEntry: LioTaxiEntry?, initialHotel: LioStayHotel? = nil) {
        self.language = language
        self.store = store
        self.taxiEntry = taxiEntry
        _hotel = State(initialValue: initialHotel)
        _room = State(initialValue: initialHotel?.roomNumber ?? "")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                if let hotel {
                    hotelCard(hotel)
                } else {
                    emptyState
                }
                if let notice {
                    Text(notice).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
                NavigationLink {
                    LioShowCardsView(language: language, hotel: hotel)
                } label: {
                    Label(language.text("Show cards: front desk, pharmacy, restaurant…", "出示卡：前台、药店、餐厅……"),
                          systemImage: "person.text.rectangle")
                        .frame(maxWidth: .infinity, minHeight: 50, alignment: .leading)
                        .padding(.horizontal, LioTheme.Spacing.md)
                        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.return-hotel.show-cards")
            }
            .padding(LioTheme.Spacing.md)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .navigationTitle(language.text("Back to Hotel", "回酒店"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
        .task {
            guard hotel == nil, let store else { return }
            do {
                hotel = try store.load()
                room = hotel?.roomNumber ?? ""
            } catch {
                notice = language.text("Your saved hotel could not be read. Set it again.", "已保存的酒店打不开了，请重新设置。")
            }
        }
        .sheet(item: $sheet) { sheet in
            switch sheet {
            case .taxi:
                if let taxiEntry, let hotel {
                    NavigationStack {
                        LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                    recentStore: taxiEntry.recentStore, destination: hotel.place)
                    }
                }
            case .driver:
                if let hotel {
                    LioDriverSign(language: language, nameZH: hotel.place.nameZH, nameEN: hotel.place.nameEN,
                                  addressZH: hotel.place.addressZH, requestZH: LioStayHotel.driverRequestZH,
                                  identifierPrefix: "lio.return-hotel.driver-sign")
                }
            case .choose:
                LioStayHotelPicker(language: language, tripPlaces: taxiEntry?.tripPlaces ?? [],
                                   search: taxiEntry?.service.search) { place, source in
                    save(LioStayHotel(place: place, roomNumber: nil, source: source))
                    self.sheet = nil
                }
            }
        }
    }

    private func hotelCard(_ hotel: LioStayHotel) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: 4) {
                Text(language.text("Your hotel", "我住的酒店")).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                Text(hotel.place.name(in: language)).font(LioTheme.display(.title2).weight(.bold))
                    .accessibilityIdentifier("lio.return-hotel.name")
                if let secondary = hotel.place.secondaryName(in: language) {
                    Text(secondary).font(.headline)
                }
                if let address = hotel.place.address(in: language) {
                    Text(address).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            HStack {
                Text(language.text("Room", "房间号")).foregroundStyle(LioTheme.inkSecondary)
                TextField(language.text("Optional", "选填"), text: $room)
                    .keyboardType(.numbersAndPunctuation)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { save(LioStayHotel(place: hotel.place, roomNumber: room, source: hotel.source)) }
                    .accessibilityIdentifier("lio.return-hotel.room")
            }
            .frame(minHeight: 44)
            if taxiEntry != nil {
                Button {
                    sheet = .taxi
                } label: {
                    Label(language.text("Take a taxi back", "打车回酒店"), systemImage: "car.fill")
                }
                .buttonStyle(LioPrimaryButtonStyle())
                .accessibilityIdentifier("lio.return-hotel.taxi")
            }
            Button {
                sheet = .driver
            } label: {
                Label(language.text("Show the driver", "给司机看"), systemImage: "text.viewfinder")
            }
            .buttonStyle(LioSecondaryButtonStyle())
            .accessibilityIdentifier("lio.return-hotel.driver")
            Button(language.text("Change hotel", "更换酒店")) { sheet = .choose }
                .foregroundStyle(LioTheme.vermilion)
                .frame(minHeight: 44)
                .accessibilityIdentifier("lio.return-hotel.change")
        }
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            Image(systemName: "bed.double").font(.largeTitle).foregroundStyle(LioTheme.vermilion)
                .accessibilityHidden(true)
            Text(language.text("Where are you staying?", "你住在哪家酒店？")).font(LioTheme.display(.title2).weight(.bold))
            Text(language.text("Set your hotel once. Then one tap gets a taxi back or shows the driver where to go.",
                               "设置一次，之后一键打车回酒店，或把地址给司机看。"))
                .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            Button {
                sheet = .choose
            } label: {
                Label(language.text("Set my hotel", "设置我的酒店"), systemImage: "plus")
            }
            .buttonStyle(LioPrimaryButtonStyle())
            .accessibilityIdentifier("lio.return-hotel.set")
            Text(language.text("You can also tap “Set as my hotel” on a hotel search result.",
                               "也可以在酒店搜索结果里点「设为我的酒店」。"))
                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func save(_ new: LioStayHotel) {
        hotel = new
        room = new.roomNumber ?? ""
        guard let store else { return }
        do {
            try store.save(new)
            notice = nil
        } catch {
            notice = language.text("Not saved on this device; it is kept only until you leave this page.",
                                   "未能保存到本机，只在离开本页前有效。")
        }
    }
}

/// Picks the stay hotel: places from the trip (likely hotels first), or a search through the taxi relay.
struct LioStayHotelPicker: View {
    let language: LioLanguage
    let tripPlaces: [LioTaxiPlace]
    let search: (@MainActor @Sendable (LioTaxiSearchQuery) async throws -> [LioTaxiPlace])?
    let choose: (LioTaxiPlace, LioStayHotel.Source) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var city = LioTaxiCity.beijing
    @State private var results: [LioTaxiPlace] = []
    @State private var searching = false
    @State private var failed = false

    var body: some View {
        NavigationStack {
            List {
                if let search {
                    Section(language.text("Search for your hotel", "搜索你的酒店")) {
                        Picker(language.text("City", "城市"), selection: $city) {
                            ForEach(LioTaxiCity.allCases) { Text(language == .chinese ? $0.nameZH : $0.nameEN).tag($0) }
                        }
                        TextField(language.text("Hotel name or address", "酒店名或地址"), text: $query)
                            .submitLabel(.search)
                            .onSubmit { run(search) }
                            .accessibilityIdentifier("lio.return-hotel.search")
                        if searching { ProgressView() }
                        if failed {
                            Text(language.text("Search is not available right now.", "暂时无法搜索。"))
                                .foregroundStyle(LioTheme.inkSecondary)
                        }
                        rows(results, source: .manual)
                    }
                }
                Section(language.text("From your trip", "来自你的行程")) {
                    if tripPlaces.isEmpty {
                        Text(language.text("No places from your trip yet.", "行程里还没有地点。"))
                            .foregroundStyle(LioTheme.inkSecondary)
                    }
                    rows(LioReturnHotel.candidates(from: tripPlaces), source: .trip)
                }
            }
            .navigationTitle(language.text("Set my hotel", "设置我的酒店"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Cancel", "取消")) { dismiss() }
                }
            }
        }
        .tint(LioTheme.vermilion)
    }

    private func rows(_ places: [LioTaxiPlace], source: LioStayHotel.Source) -> some View {
        ForEach(places) { place in
            Button {
                choose(place, source)
            } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(place.name(in: language)).foregroundStyle(LioTheme.ink)
                        if let address = place.address(in: language) {
                            Text(address).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        }
                    }
                    Spacer()
                    if LioReturnHotel.looksLikeStay(place) {
                        Image(systemName: "bed.double").foregroundStyle(LioTheme.vermilion).accessibilityHidden(true)
                    }
                }
                .frame(minHeight: 44)
            }
            .accessibilityIdentifier("lio.return-hotel.choice")
        }
    }

    private func run(_ search: @escaping @MainActor @Sendable (LioTaxiSearchQuery) async throws -> [LioTaxiPlace]) {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        searching = true
        failed = false
        Task {
            defer { searching = false }
            do {
                results = try await search(LioTaxiSearchQuery(text: text, city: city, near: nil, english: language == .english))
            } catch {
                results = []
                failed = true
            }
        }
    }
}
#endif

#if DEBUG && os(iOS)
/// Debug launch arguments for #1571 screenshots: `--lio-return-hotel-preview` shows the entry with a saved hotel;
/// add `--lio-return-hotel-empty` for the first-run state.
enum LioReturnHotelPreview {
    static var requested: Bool { ProcessInfo.processInfo.arguments.contains("--lio-return-hotel-preview") }

    static var hotel: LioStayHotel? {
        guard !ProcessInfo.processInfo.arguments.contains("--lio-return-hotel-empty") else { return nil }
        return LioStayHotel(place: LioTaxiPlace(nameZH: "北京王府井希尔顿酒店", nameEN: "Hilton Beijing Wangfujing",
                                                addressZH: "北京市东城区王府井东街8号",
                                                addressEN: "8 Wangfujing East Street, Dongcheng, Beijing",
                                                coordinate: .init(latitude: 39.9139, longitude: 116.4143, referenceSystem: .gcj02)),
                            roomNumber: "1208", source: .hotelSearch)
    }

    @MainActor static var taxiEntry: LioTaxiEntry {
        LioTaxiEntry(service: .preview(), recentStore: LioTaxiService.previewRecents,
                     tripPlaces: LioTaxiService.previewDestinations)
    }
}
#endif
