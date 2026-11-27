import Foundation

/// One place of the shared place library as the App reads it (#1992, 58.1 D-4): what the place page, the bubble
/// card, the canvas and the map all show. Fields follow `knowledge/places` (#1985, `placelib.py`): the full
/// library entry, the development pack's entries and the App's slim copy (`LioPlaces.v1.json`) all decode here.
///
/// The library has a lot of `null` (drafts and candidates are unfinished), so decoding is forgiving: only an `id`
/// and the Chinese name are required; every other field that is missing, empty or of the wrong type is left
/// out. Coordinates and links are checked: a coordinate must be a real GCJ-02 point and a link an `https` page.
struct LioPlace: Equatable, Identifiable, Sendable {
    /// Library categories. An unknown value (a later library version) is kept as `other`.
    enum Category: String, Sendable {
        case attraction, food, shopping, hotel, hub, other
    }

    /// How firmly a visit has to be booked, from `ticket.booking`.
    enum BookingRequirement: String, Sendable {
        case required, recommended
        /// `ticket.booking` is `"none"`: no booking is needed.
        case notNeeded = "none"
    }

    struct Ticket: Equatable, Sendable {
        let booking: BookingRequirement?
        let passportRequired: Bool?
        let priceCNY: Double?
        /// ISO weekdays, 1 = Monday ... 7 = Sunday. `nil`: the source says nothing; `[]`: no fixed closing day.
        let closedWeekdays: [Int]?
        let channelZH: String?
        let bookingURL: URL?
    }

    struct Metro: Equatable, Sendable {
        let stationZH: String
        let stationEN: String?
        let line: String?
        let exit: String?
    }

    /// An airport terminal or a station hall of a hub.
    struct Terminal: Equatable, Sendable {
        let name: String
        let noteZH: String?
    }

    let id: String
    let city: String?
    let category: Category
    /// `subcategory` (museum, park, ...) or `hub_type` (airport, rail).
    let kind: String?
    let nameZH: String
    let nameEN: String
    let aliasesZH: [String]
    let aliasesEN: [String]
    let addressZH: String?
    let addressEN: String?
    let districtZH: String?
    let nearestMetro: Metro?
    /// The checked GCJ-02 coordinate, when the library has one.
    let point: LioItinerary.Point?
    let introShortZH: String?
    let introShortEN: String?
    let introLongZH: String?
    let introLongEN: String?
    let hoursZH: String?
    let ticket: Ticket?
    let officialURL: URL?
    /// `YYYY-MM-DD` of the last check against the official source.
    let checkedOn: String?
    let visitMinutes: Int?
    /// Hubs only: the airport code, how to get into town, tips for a foreign traveller, terminals.
    let hubCode: String?
    let toCityZH: [String]
    let toCityEN: [String]
    let tipsZH: [String]
    let tipsEN: [String]
    let terminals: [Terminal]
    /// File name of the thumbnail in the App's slim copy. It is a name only: no picture is shown until its
    /// licence is on record (#1987), so the place page draws a placeholder either way.
    let thumb: String?

    func name(_ language: LioLanguage) -> String { language == .chinese ? nameZH : nameEN }

    /// The other language's name, shown under the first so it can be matched with signs and shown to a driver.
    func secondaryName(_ language: LioLanguage) -> String? {
        let other = language == .chinese ? nameEN : nameZH
        return other == name(language) ? nil : other
    }

    /// The one-line intro in `language`, falling back to the other language rather than showing nothing.
    func introShort(_ language: LioLanguage) -> String? {
        language == .chinese ? introShortZH ?? introShortEN : introShortEN ?? introShortZH
    }

    func introLong(_ language: LioLanguage) -> String? {
        let long = language == .chinese ? introLongZH ?? introLongEN : introLongEN ?? introLongZH
        return long ?? introShort(language)
    }

    /// Hub notes in `language`; the library often has the Chinese lines only, which are shown rather than hidden.
    func toCity(_ language: LioLanguage) -> [String] {
        language == .english && !toCityEN.isEmpty ? toCityEN : toCityZH
    }

    func tips(_ language: LioLanguage) -> [String] {
        language == .english && !tipsEN.isEmpty ? tipsEN : tipsZH
    }
}

// MARK: - Decoding

extension LioPlace: Decodable {
    fileprivate struct Key: CodingKey {
        let stringValue: String
        let intValue: Int? = nil
        init(_ value: String) { stringValue = value }
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { nil }
    }

    init(from decoder: Decoder) throws {
        let root = try decoder.container(keyedBy: Key.self)
        func text(_ key: String) -> String? { Self.clean(root.value(String.self, key)) }
        func texts(_ key: String) -> [String] { Self.lines(root.value([String].self, key)) }

        guard let id = text("id") else {
            throw DecodingError.dataCorruptedError(forKey: Key("id"), in: root, debugDescription: "the id is missing")
        }
        // The Chinese name is what a driver is shown, so a place without one is not usable; a missing English
        // name falls back to the Chinese one (as `LioTaxiPlace` does).
        guard let zh = text("name_zh") else {
            throw DecodingError.dataCorruptedError(forKey: Key("name_zh"), in: root, debugDescription: "the Chinese name is missing")
        }
        self.id = id
        city = text("city")
        category = text("category").flatMap(Category.init(rawValue:)) ?? .other
        kind = text("kind") ?? text("subcategory") ?? text("hub_type")
        nameZH = zh
        nameEN = text("name_en") ?? zh
        aliasesZH = texts("aliases_zh")
        aliasesEN = texts("aliases_en")
        addressZH = text("address_zh")
        addressEN = text("address_en")
        districtZH = text("district_zh")
        nearestMetro = root.value(MetroWire.self, "nearest_metro")?.metro
        point = Self.point(root)
        introShortZH = text("intro_short_zh")
        introShortEN = text("intro_short_en")
        introLongZH = text("intro_long_zh")
        introLongEN = text("intro_long_en")
        hoursZH = text("hours_zh")
        ticket = root.value(TicketWire.self, "ticket")?.ticket
        officialURL = Self.link(text("official_url"))
        checkedOn = Self.day(text("checked_on"))
        visitMinutes = root.value(Int.self, "visit_minutes").flatMap { $0 > 0 ? $0 : nil }
        hubCode = text("code")
        toCityZH = texts("to_city_zh")
        toCityEN = texts("to_city_en")
        tipsZH = texts("foreigner_tips_zh")
        tipsEN = texts("foreigner_tips_en")
        terminals = (root.value([Lossy<TerminalWire>].self, "terminals") ?? []).compactMap { $0.value?.terminal }
        thumb = text("thumb")
    }

    /// `location.gcj02` of a library entry, or `lat`/`lng` of the slim copy.
    private static func point(_ root: KeyedDecodingContainer<Key>) -> LioItinerary.Point? {
        struct Location: Decodable {
            struct Point: Decodable {
                let lat: Double?, lng: Double?
                init(from decoder: Decoder) throws {
                    let c = try decoder.container(keyedBy: Key.self)
                    lat = c.value(Double.self, "lat")
                    lng = c.value(Double.self, "lng")
                }
            }
            let gcj02: Point?
            init(from decoder: Decoder) throws {
                gcj02 = try decoder.container(keyedBy: Key.self).value(Point.self, "gcj02")
            }
        }
        var latitude: Double?, longitude: Double?
        if let location = root.value(Location.self, "location") {
            latitude = location.gcj02?.lat
            longitude = location.gcj02?.lng
        }
        if latitude == nil || longitude == nil {
            latitude = root.value(Double.self, "lat")
            longitude = root.value(Double.self, "lng")
        }
        guard let latitude, let longitude, latitude.isFinite, longitude.isFinite,
              (-90...90).contains(latitude), (-180...180).contains(longitude),
              !(latitude == 0 && longitude == 0) else { return nil }
        return LioItinerary.Point(latitude: latitude, longitude: longitude)
    }

    private struct MetroWire: Decodable {
        let station_zh: String?, station_en: String?, line: String?, exit: String?
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Key.self)
            station_zh = c.value(String.self, "station_zh")
            station_en = c.value(String.self, "station_en")
            line = c.value(String.self, "line")
            exit = c.value(String.self, "exit")
        }
        var metro: Metro? {
            guard let station = LioPlace.clean(station_zh) else { return nil }
            return Metro(stationZH: station, stationEN: LioPlace.clean(station_en), line: LioPlace.clean(line),
                         exit: LioPlace.clean(exit))
        }
    }

    private struct TicketWire: Decodable {
        let booking: String?
        let passport_required: Bool?
        let price_cny: Double?
        let closed_weekdays: [Int]?
        let booking_channel_zh: String?
        let booking_url: String?

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Key.self)
            booking = c.value(String.self, "booking")
            passport_required = c.value(Bool.self, "passport_required")
            price_cny = c.value(Double.self, "price_cny")
            closed_weekdays = c.value([Int].self, "closed_weekdays")
            booking_channel_zh = c.value(String.self, "booking_channel_zh")
            booking_url = c.value(String.self, "booking_url")
        }

        var ticket: Ticket? {
            let weekdays = closed_weekdays.map { Array(Set($0.filter { (1...7).contains($0) })).sorted() }
            let value = Ticket(booking: LioPlace.clean(booking).flatMap(BookingRequirement.init(rawValue:)),
                               passportRequired: passport_required, priceCNY: price_cny.flatMap { $0 >= 0 ? $0 : nil },
                               closedWeekdays: weekdays, channelZH: LioPlace.clean(booking_channel_zh),
                               bookingURL: LioPlace.link(LioPlace.clean(booking_url)))
            let empty = value.booking == nil && value.passportRequired == nil && value.priceCNY == nil
                && value.closedWeekdays == nil && value.channelZH == nil && value.bookingURL == nil
            return empty ? nil : value
        }
    }

    private struct TerminalWire: Decodable {
        let name: String?, note_zh: String?
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Key.self)
            name = c.value(String.self, "name")
            note_zh = c.value(String.self, "note_zh")
        }
        var terminal: Terminal? {
            LioPlace.clean(name).map { Terminal(name: $0, noteZH: LioPlace.clean(note_zh)) }
        }
    }

    // MARK: Cleaning

    fileprivate static func clean(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else { return nil }
        return trimmed
    }

    fileprivate static func lines(_ values: [String]?) -> [String] { (values ?? []).compactMap(clean) }

    /// A plain `https` page (the library accepts nothing else), or nil.
    fileprivate static func link(_ value: String?) -> URL? {
        guard let value, let url = URL(string: value), url.scheme?.lowercased() == "https",
              let host = url.host, !host.isEmpty, url.user == nil, url.password == nil else { return nil }
        return url
    }

    fileprivate static func day(_ value: String?) -> String? {
        guard let value, value.count == 10 else { return nil }
        let parts = value.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3, parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
              let month = Int(parts[1]), let dayOfMonth = Int(parts[2]), Int(parts[0]) != nil,
              (1...12).contains(month), (1...31).contains(dayOfMonth) else { return nil }
        return value
    }
}

private extension KeyedDecodingContainer where K == LioPlace.Key {
    /// The value under `key`, or nil when it is missing, null or of another type.
    func value<T: Decodable>(_ type: T.Type, _ key: String) -> T? {
        guard let key = K(stringValue: key) else { return nil }
        return try? decodeIfPresent(type, forKey: key)
    }
}

/// Decodes one array element, or nothing when it is malformed, so one bad entry cannot hide the others.
struct Lossy<Value: Decodable>: Decodable {
    let value: Value?
    init(from decoder: Decoder) throws { value = try? Value(from: decoder) }
}
