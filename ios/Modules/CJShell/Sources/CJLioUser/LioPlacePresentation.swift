import Foundation

/// What the place page says about one place, in one language (#1992). It is plain data so the wording, the
/// buttons that apply and the nearby list can be tested without a screen; `LioPlacePage` only lays it out.
struct LioPlacePresentation {
    let place: LioPlace
    let language: LioLanguage
    /// True when the place was read from the unreviewed development pack (Debug builds only, see
    /// `LioPlaceRepository.isDevelopmentData`). The page then says so.
    let developmentData: Bool

    init(_ place: LioPlace, language: LioLanguage, developmentData: Bool = false) {
        self.place = place
        self.language = language
        self.developmentData = developmentData
    }

    private func copy(_ key: LioPlaceCopy) -> String { key.text(language) }

    // MARK: Development data

    /// "Dev data" / "开发数据" for a place from the development pack; nil for any other place.
    var developmentLabel: String? { developmentData ? copy(.devData) : nil }
    /// What the label means, read out with it by VoiceOver.
    var developmentNote: String? { developmentData ? copy(.devDataNote) : nil }

    // MARK: Names and kind

    var title: String { place.name(language) }
    var subtitle: String? { place.secondaryName(language) }
    var intro: String? { place.introLong(language) }
    /// The one line shown on a bubble card; the page shows the long intro instead.
    var oneLiner: String? { place.introShort(language) }

    var symbol: String {
        switch place.category {
        case .attraction: "camera"
        case .food: "fork.knife"
        case .shopping: "bag"
        case .hotel: "bed.double"
        case .hub: place.kind == "airport" ? "airplane" : "tram"
        case .other: "mappin"
        }
    }

    /// "Museum", "Airport", ... from the subcategory or hub type, else the category.
    var kindLabel: String {
        let table: [String: (String, String)] = [
            "history": ("Historic site", "历史古迹"), "museum": ("Museum", "博物馆"), "park": ("Park", "公园"),
            "street": ("Street", "街区"), "landmark": ("Landmark", "地标"), "experience": ("Experience", "体验"),
            "airport": ("Airport", "机场"), "rail": ("Train station", "火车站"),
        ]
        if let kind = place.kind, let words = table[kind] { return language.text(words.0, words.1) }
        switch place.category {
        case .attraction: return language.text("Sight", "景点")
        case .food: return language.text("Food", "餐饮")
        case .shopping: return language.text("Shopping", "购物")
        case .hotel: return language.text("Stay", "住宿")
        case .hub: return language.text("Transport hub", "交通枢纽")
        case .other: return language.text("Place", "地点")
        }
    }

    // MARK: Opening and booking

    /// "Booking required · Closed Mondays": the hint shown first, or nil when the library says neither.
    var statusLine: String? {
        let parts = [bookingText, closedText].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    var bookingText: String? {
        switch place.ticket?.booking {
        case .required: copy(.bookingRequired)
        case .recommended: copy(.bookingRecommended)
        case .notNeeded: copy(.bookingNone)
        case nil: nil
        }
    }

    /// "Closed Mondays" / "周一闭馆"; nil when the source does not say.
    var closedText: String? {
        guard let days = place.ticket?.closedWeekdays else { return nil }
        if days.isEmpty { return copy(.noFixedClosingDay) }
        let names = days.map { Self.weekday($0, language) }
        return language == .chinese ? names.joined(separator: "、") + "闭馆" : "Closed " + names.joined(separator: ", ")
    }

    static func weekday(_ number: Int, _ language: LioLanguage) -> String {
        let english = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]
        let chinese = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        guard (1...7).contains(number) else { return "" }
        return language == .chinese ? chinese[number - 1] : english[number - 1]
    }

    /// The opening-hours block: the text as published (the library has it in Chinese only) and the closing days.
    var hours: [String] {
        [place.hoursZH, closedText].compactMap { $0 }
    }

    /// True when `hours` shows Chinese text on an English page, so the page can say so.
    var hoursAreChineseOnly: Bool { language == .english && place.hoursZH != nil }

    /// The tickets block: whether to book, the passport, the price and the channel.
    var tickets: [String] {
        guard let ticket = place.ticket else { return [] }
        var lines: [String] = []
        if let booking = bookingText { lines.append(booking) }
        if ticket.passportRequired == true { lines.append(copy(.passportRequired)) }
        if let price = ticket.priceCNY {
            let number = price == price.rounded() ? String(Int(price)) : String(price)
            lines.append(price == 0 ? language.text("Free", "免费") : "¥\(number)")
        }
        return lines
    }

    /// How to book: the channel's name (Chinese, as the library has it) and its official page.
    var bookingChannel: String? { place.ticket?.channelZH }
    var bookingURL: URL? { place.ticket?.bookingURL }

    var officialURL: URL? { place.officialURL }
    var checkedText: String? { place.checkedOn.map { LioPlaceCopy.checkedOn($0, language) } }

    // MARK: How to get there

    /// The address and the nearest metro for a place; for a hub, how to get into town and the tips as well.
    var directions: [String] {
        var lines: [String] = []
        if let address = place.addressZH { lines.append(address) }
        if let metro = place.nearestMetro {
            var text = language == .english ? metro.stationEN ?? metro.stationZH : metro.stationZH
            if let line = metro.line { text += " · " + line }
            if let exit = metro.exit { text += " · " + language.text("Exit \(exit)", "\(exit)口") }
            lines.append(copy(.metroLabel) + language.text(": ", "：") + text)
        }
        lines += place.toCity(language)
        return lines
    }

    var terminals: [String] {
        place.terminals.map { terminal in terminal.noteZH.map { "\(terminal.name): \($0)" } ?? terminal.name }
    }

    var tips: [String] { place.tips(language) }

    // MARK: Actions

    /// The place as a trip stop, which is what `LioPlaceActions` (the trip's buttons, #1740) reads.
    /// A place counts as checked when the library gives a coordinate or an address. Booking is offered for a
    /// sight only when it is required or recommended, or when a booking rule names it.
    var stop: LioRichItinerary.Stop {
        let kind: LioRichItinerary.Kind
        switch place.category {
        case .attraction:
            let booking = place.ticket?.booking
            kind = booking == .required || booking == .recommended ? .sight : .unspecified
        case .food: kind = .meal
        case .hotel: kind = .hotel
        case .hub: kind = .transport
        case .shopping, .other: kind = .unspecified
        }
        let checked = place.point != nil || place.addressZH != nil
        return LioRichItinerary.Stop(
            id: place.id, kind: kind, text: oneLiner ?? "", time: nil,
            place: LioRichItinerary.Place(nameZH: place.nameZH, nameEN: place.nameEN, address: place.addressZH,
                                          matched: checked, point: place.point),
            note: nil, tip: nil)
    }

    /// Which of taxi, driver card, directions and booking apply to this place. `available` says whether a tool
    /// can be opened here (shown in this build, and a router is present).
    func actions(available: (LioTool) -> Bool) -> LioPlaceActions {
        LioPlaceActions(stop: stop, available: available)
    }

    // MARK: Nearby

    /// Recorded places to eat within walking distance, nearest first. Only places the library has.
    func nearbyFood(in repository: LioPlaceRepository, limit: Int = 3) -> [LioPlaceRepository.Neighbour] {
        repository.nearby(place, category: .food, limit: limit)
    }

    /// "350 m" / "1.2 km".
    static func distanceText(_ metres: Double) -> String {
        let rounded = Int((metres / 10).rounded()) * 10
        return rounded < 1_000 ? "\(rounded) m" : String(format: "%.1f km", metres / 1_000)
    }
}
