#if os(iOS)
import SwiftUI
import UIKit

private struct LioHotelFinderKey: EnvironmentKey {
    static let defaultValue: LioHotelFinder? = nil
}

extension EnvironmentValues {
    /// Set only when the build enables hotel search (`G2CHotelEnabled`); the Tools card is hidden otherwise.
    var lioHotelFinder: LioHotelFinder? {
        get { self[LioHotelFinderKey.self] }
        set { self[LioHotelFinderKey.self] = newValue }
    }
}

/// #1510: search hotels by city, area or landmark, dates, guests and price band, then show each hotel's
/// names, address, price, rating, nearest metro and whether it accepts international guests.
/// "Show the driver" reuses the taxi driver card; "Book" leaves the app — nothing is booked here.
struct LioHotelOffersView: View {
    private enum Phase {
        case idle, searching, ready(LioHotelResults), failed(String)
    }

    private struct Pending: Equatable {
        let id = UUID()
        let query: LioHotelQuery
    }

    private static let resultsAnchor = "lio.hotel-search.results"

    let language: LioLanguage
    let finder: LioHotelFinder
    @State private var city = ""
    @State private var landmark = ""
    @State private var checkIn = Date()
    @State private var checkOut = LioHotelSearch.calendar.date(byAdding: .day, value: 1, to: Date()) ?? Date()
    @State private var guests = 2
    @State private var price = LioHotelPriceBand.any
    @State private var phase = Phase.idle
    @State private var pending: Pending?
    @State private var problem: String?
    @State private var driverPlace: LioTaxiPlace?
    @State private var bookingNotice: String?
    @FocusState private var typing: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize

    private var stacked: Bool { LioHotelLayout.stacksControls(at: typeSize) }
    /// Label beside its control, or above it at accessibility text sizes.
    private var row: AnyLayout {
        stacked ? AnyLayout(VStackLayout(alignment: .leading, spacing: LioTheme.Spacing.xxs))
            : AnyLayout(HStackLayout(spacing: LioTheme.Spacing.xs))
    }

    /// #225: once under the list, and only when the hand-offs carry an affiliate ID.
    private var showsDisclosure: Bool {
        if case .ready(let found) = phase { return found.affiliateLinks }
        return false
    }

    var body: some View {
        ScrollViewReader { reader in
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    form
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.md) { results }
                        .id(Self.resultsAnchor)
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                        Text(language.text("Booking and payment happen on Trip.com, not in Go2China.",
                                           "预订和付款在 Trip.com 完成，不在 Go2China 内进行。"))
                        if showsDisclosure {
                            Text(LioHotelResults.disclosure(language))
                                .accessibilityIdentifier("lio.hotel-search.footer.disclosure")
                        }
                    }
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, LioTheme.Spacing.md)
                .padding(.vertical, 18)
            }
            .onChange(of: pending) { _, now in
                guard now == nil, case .ready = phase else { return }
                let motion = LioTheme.Motion.animation(LioTheme.Motion.change, reduceMotion: reduceMotion)
                withAnimation(motion) { reader.scrollTo(Self.resultsAnchor, anchor: .top) }
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .tint(LioTheme.vermilion)
        .navigationTitle(language.text("Hotels", "酒店"))
        .navigationBarTitleDisplayMode(.inline)
        .environment(\.calendar, LioHotelSearch.calendar)
        .environment(\.timeZone, LioHotelSearch.calendar.timeZone)
        .environment(\.locale, Locale(identifier: language == .chinese ? "zh_CN" : "en_US"))
        .task(id: pending) {
            guard let pending else { return }
            await run(pending)
        }
        .onDisappear {
            if pending != nil { phase = .idle }
            pending = nil
        }
        .fullScreenCover(item: $driverPlace) { place in
            LioTaxiDriverCard(language: language, place: place)
        }
    }

    // MARK: - Form

    private var form: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            field(language.text("City", "城市"), text: $city,
                  prompt: language.text("For example, Beijing", "例如：北京"), id: "lio.hotel-search.city")
            field(language.text("Area or landmark (optional)", "区域或地标（选填）"), text: $landmark,
                  prompt: language.text("For example, Wangfujing", "例如：王府井"), id: "lio.hotel-search.landmark")
            date(language.text("Check-in", "入住"), selection: $checkIn,
                 in: LioHotelSearch.calendar.startOfDay(for: Date())..., id: "lio.hotel-search.check-in")
            date(language.text("Checkout", "退房"), selection: $checkOut, in: checkIn..., id: "lio.hotel-search.check-out")
            Stepper(value: $guests, in: 1...LioHotelQuery.maximumGuests) {
                Text(language.text("Guests: \(guests)", "人数：\(guests)"))
            }
            .accessibilityLabel(language.text("Guests", "人数"))
            .accessibilityValue(String(guests))
            .accessibilityIdentifier("lio.hotel-search.guests")
            row {
                Text(language.text("Price a night", "每晚价格"))
                if !stacked { Spacer(minLength: LioTheme.Spacing.xs) }
                Picker(language.text("Price a night", "每晚价格"), selection: $price) {
                    ForEach(LioHotelPriceBand.allCases) { band in
                        Text(band.title(language)).tag(band)
                    }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("lio.hotel-search.price")
            }
            .frame(minHeight: 44)
            if let problem {
                Text(problem)
                    .font(.footnote)
                    .foregroundStyle(LioTheme.vermilion)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.hotel-search.problem")
            }
            Button(language.text("Search hotels", "搜索酒店")) { search() }
                .buttonStyle(LioPrimaryButtonStyle())
                .disabled(pending != nil)
                .accessibilityIdentifier("lio.hotel-search.search")
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func date(_ title: String, selection: Binding<Date>, in range: PartialRangeFrom<Date>,
                      id: String) -> some View {
        row {
            Text(title)
            if !stacked { Spacer(minLength: LioTheme.Spacing.xs) }
            DatePicker(title, selection: selection, in: range, displayedComponents: .date)
                .labelsHidden()
                .accessibilityIdentifier(id)
        }
        .frame(minHeight: 44)
    }

    private func field(_ title: String, text: Binding<String>, prompt: String, id: String) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
            Text(title).font(.subheadline.weight(.semibold))
            TextField(title, text: text, prompt: Text(prompt).foregroundStyle(LioTheme.inkSecondary))
                .focused($typing)
                .submitLabel(.search)
                .onSubmit { search() }
                .padding(.horizontal, LioTheme.Spacing.sm)
                .frame(minHeight: 44)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityIdentifier(id)
        }
    }

    // MARK: - Results

    @ViewBuilder private var results: some View {
        switch phase {
        case .idle:
            EmptyView()
        case .searching:
            ProgressView(language.text("Finding hotels…", "正在查找酒店…"))
                .frame(maxWidth: .infinity, minHeight: 80)
        case .failed(let message):
            VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                Text(message).accessibilityIdentifier("lio.hotel-search.failure")
                Button(language.text("Try again", "重试")) { search() }
                    .frame(minHeight: 44)
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        case .ready(let found):
            if let notice = found.notice(language) {
                Label(notice, systemImage: "info.circle")
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("lio.hotel-search.unapplied")
            }
            if found.offers.isEmpty {
                Text(language.text("No hotels found. Try another area or price.", "没有找到酒店，换个区域或价格试试。"))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .frame(maxWidth: .infinity, minHeight: 80)
                    .accessibilityIdentifier("lio.hotel-search.empty")
            }
            if let bookingNotice {
                Text(bookingNotice).font(.footnote).accessibilityIdentifier("lio.hotel-search.booking-notice")
            }
            ForEach(found.offers) { offer in
                card(offer)
            }
            Text(found.source.credit(language))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
        }
    }

    private func card(_ offer: LioHotelOffer) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            VStack(alignment: .leading, spacing: 2) {
                Text(offer.title(language)).font(.headline)
                if let subtitle = offer.subtitle(language) {
                    Text(subtitle).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
            }
            .accessibilityElement(children: .combine)
            if offer.rating != nil || offer.price != nil {
                HStack(spacing: LioTheme.Spacing.sm) {
                    if let rating = offer.rating {
                        Label(rating, systemImage: "star.fill")
                            .accessibilityLabel(language.text("Rating \(rating)", "评分 \(rating)"))
                    }
                    if let price = offer.priceText(language) { Text(price) }
                }
                .font(.subheadline)
            }
            if let metro = offer.metroText(language) {
                Label(metro, systemImage: "tram.fill").font(.subheadline)
            }
            Label(offer.address(language), systemImage: "mappin")
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
            foreignGuests(offer.foreignGuests)
            (stacked ? AnyLayout(VStackLayout(spacing: LioTheme.Spacing.xs))
                : AnyLayout(HStackLayout(spacing: LioTheme.Spacing.xs))) {
                Button(language.text("Show the driver", "给司机看")) { driverPlace = offer.taxiPlace }
                    .buttonStyle(LioSecondaryButtonStyle())
                    .accessibilityIdentifier("lio.hotel-search.driver")
                Button {
                    Task { await book(offer) }
                } label: {
                    Label(language.text("Book", "去预订"), systemImage: "arrow.up.right")
                        .labelStyle(.titleAndIcon)
                }
                .buttonStyle(LioPrimaryButtonStyle())
                .accessibilityLabel(language.text("Book on Trip.com", "去 Trip.com 预订"))
                .accessibilityIdentifier("lio.hotel-search.book")
            }
            .padding(.top, LioTheme.Spacing.xxs)
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityIdentifier("lio.hotel-search.hotel")
    }

    private func foreignGuests(_ answer: LioHotelOffer.ForeignGuests) -> some View {
        let symbol = switch answer {
        case .accepted: "checkmark.seal.fill"
        case .notAccepted: "xmark.octagon.fill"
        case .unknown: "questionmark.circle"
        }
        let tint = switch answer {
        case .accepted: LioTheme.jade
        case .notAccepted: LioTheme.vermilion
        case .unknown: LioTheme.inkSecondary
        }
        return Label(answer.label(language), systemImage: symbol)
            .font(.footnote.weight(.semibold))
            .foregroundStyle(tint)
            .padding(.horizontal, LioTheme.Spacing.xs)
            .padding(.vertical, LioTheme.Spacing.xxs)
            .background(LioTheme.surfaceSunken, in: Capsule())
            .accessibilityIdentifier("lio.hotel-search.foreign-guests")
    }

    // MARK: - Actions

    private func search() {
        guard pending == nil else { return }
        typing = false
        do {
            let query = try LioHotelQuery(city: city, landmark: landmark, checkIn: checkIn, checkOut: checkOut,
                                          guests: guests, price: price, language: language)
            problem = nil
            bookingNotice = nil
            phase = .searching
            pending = Pending(query: query)
        } catch {
            problem = error.message(language)
        }
    }

    private func run(_ request: Pending) async {
        do {
            let found = try await finder.search(request.query)
            guard !Task.isCancelled, pending == request else { return }
            phase = .ready(found)
        } catch is CancellationError {
            if pending == request { phase = .idle }
        } catch {
            guard pending == request else { return }
            phase = .failed((error as? LioHotelFailure ?? .unavailable).message(language))
        }
        if pending == request { pending = nil }
    }

    private func book(_ offer: LioHotelOffer) async {
        guard UIApplication.shared.applicationState == .active else { return }
        bookingNotice = nil
        if !(await finder.open(offer.booking)) {
            bookingNotice = language.text("Couldn’t open Trip.com. Try again.", "暂时无法打开 Trip.com，请重试。")
        }
    }
}

#if DEBUG
#Preview("Hotels · English") {
    NavigationStack { LioHotelOffersView(language: .english, finder: .preview) }
}

#Preview("酒店 · 中文") {
    NavigationStack { LioHotelOffersView(language: .chinese, finder: .preview) }
}
#endif
#endif
