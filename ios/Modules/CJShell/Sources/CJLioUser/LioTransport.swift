import Foundation

/// Intercity transport search (#1517 / #1519): compare trains, flights and buses between two cities.
/// Booking and payment always happen outside the app (12306, Trip.com, the bus station).
enum LioTransportMode: String, CaseIterable, Identifiable, Sendable {
    case rail, flight, bus

    var id: Self { self }

    var symbol: String {
        switch self {
        case .rail: "train.side.front.car"
        case .flight: "airplane"
        case .bus: "bus.fill"
        }
    }

    var identifier: String { "lio.transport.mode." + rawValue }

    func name(_ language: LioLanguage) -> String {
        switch self {
        case .rail: language.text("Train", "火车")
        case .flight: language.text("Flight", "飞机")
        case .bus: language.text("Bus", "大巴")
        }
    }

    /// What we can and cannot promise about seats and prices; we never show live availability.
    func availabilityNote(_ language: LioLanguage) -> String {
        switch self {
        case .rail: language.text("Seats left: check on 12306 before you go", "余票以 12306 为准")
        case .flight: language.text("Prices change often; check the final price when booking", "价格随时变动，以订票页为准")
        case .bus: language.text("Times and fares: check at the bus station", "班次和票价以车站为准")
        }
    }
}

/// A railway station or airport, named in both languages so travellers can match signs and show a driver.
struct LioTransportHub: Equatable, Hashable, Sendable {
    enum Kind: String, Sendable { case station, airport }

    let kind: Kind
    let nameZH: String
    let nameEN: String
    /// IATA code for airports.
    let code: String?
    /// Only when a data source supplies it; the static city table has none, so taxi hand-off is hidden there.
    let coordinate: LioTaxiPlace.Coordinate?

    init(kind: Kind, nameZH: String, nameEN: String, code: String? = nil, coordinate: LioTaxiPlace.Coordinate? = nil) {
        self.kind = kind
        self.nameZH = nameZH
        self.nameEN = nameEN
        self.code = code
        self.coordinate = coordinate
    }

    static func station(_ nameZH: String, _ nameEN: String) -> Self {
        Self(kind: .station, nameZH: nameZH, nameEN: nameEN)
    }

    static func airport(_ nameZH: String, _ nameEN: String, _ code: String) -> Self {
        Self(kind: .airport, nameZH: nameZH, nameEN: nameEN, code: code)
    }

    func name(in language: LioLanguage) -> String {
        language == .chinese ? nameZH : nameEN
    }

    func secondaryName(in language: LioLanguage) -> String? {
        language == .english ? nameZH : nil
    }

    func with(coordinate: LioTaxiPlace.Coordinate) -> Self {
        Self(kind: kind, nameZH: nameZH, nameEN: nameEN, code: code, coordinate: coordinate)
    }

    /// The Chinese request shown above the name on the shared driver sign (`LioDriverSign`).
    var driverRequestZH: String {
        kind == .airport ? "请送我到这个机场" : "请送我到这个火车站"
    }

    /// The English line under the Chinese name; airports keep their code, which is on every booking.
    var driverNameEN: String {
        code.map { "\(nameEN) (\($0))" } ?? nameEN
    }

    /// A taxi destination when the hub has a coordinate; the driver sees the Chinese name.
    var taxiPlace: LioTaxiPlace? {
        guard let coordinate else { return nil }
        return LioTaxiPlace(nameZH: nameZH, nameEN: nameEN, addressZH: nil, coordinate: coordinate)
    }
}

struct LioTransportCity: Equatable, Hashable, Identifiable, Sendable {
    let id: String
    let nameZH: String
    let nameEN: String
    let aliases: [String]
    /// Trip.com China train route page slug (checked 2026-11-25, e.g. `/trains/china/route/shanghai-to-beijing/`).
    let railSlug: String
    /// Trip.com flight search city code (metropolitan code where a city has several airports).
    let flightCityCode: String
    let stations: [LioTransportHub]
    let airports: [LioTransportHub]

    func name(in language: LioLanguage) -> String {
        language == .chinese ? nameZH : nameEN
    }

    var hubs: [LioTransportHub] { stations + airports }

    /// Matches a Chinese or English city name exactly (after trimming "市", "City", "中国" and punctuation).
    /// Places outside the table (including Hong Kong, Macao and Taiwan) are not guessed.
    static func resolve(_ text: String) -> LioTransportCity? {
        let key = normalized(text)
        guard !key.isEmpty else { return nil }
        return all.first { city in
            ([city.nameZH, city.nameEN, city.id] + city.aliases).contains { normalized($0) == key }
        }
    }

    private static func normalized(_ text: String) -> String {
        var value = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        for prefix in ["中国", "中國", "china "] where value.hasPrefix(prefix) {
            value.removeFirst(prefix.count)
        }
        for suffix in [" city", "city", "市"] where value.hasSuffix(suffix) && value.count > suffix.count {
            value.removeLast(suffix.count)
        }
        return value.filter { !$0.isWhitespace && !"'’‘-·.".contains($0) }
    }

    static let all: [LioTransportCity] = [
        LioTransportCity(id: "beijing", nameZH: "北京", nameEN: "Beijing", aliases: ["Peking"], railSlug: "beijing",
                         flightCityCode: "BJS",
                         stations: [.station("北京南站", "Beijing South Railway Station"),
                                    .station("北京西站", "Beijing West Railway Station"),
                                    .station("北京站", "Beijing Railway Station")],
                         airports: [.airport("北京首都国际机场", "Beijing Capital International Airport", "PEK"),
                                    .airport("北京大兴国际机场", "Beijing Daxing International Airport", "PKX")]),
        LioTransportCity(id: "shanghai", nameZH: "上海", nameEN: "Shanghai", aliases: [], railSlug: "shanghai",
                         flightCityCode: "SHA",
                         stations: [.station("上海虹桥站", "Shanghai Hongqiao Railway Station"),
                                    .station("上海站", "Shanghai Railway Station"),
                                    .station("上海南站", "Shanghai South Railway Station")],
                         airports: [.airport("上海浦东国际机场", "Shanghai Pudong International Airport", "PVG"),
                                    .airport("上海虹桥国际机场", "Shanghai Hongqiao International Airport", "SHA")]),
        LioTransportCity(id: "guangzhou", nameZH: "广州", nameEN: "Guangzhou", aliases: ["Canton"], railSlug: "guangzhou",
                         flightCityCode: "CAN",
                         stations: [.station("广州南站", "Guangzhou South Railway Station"),
                                    .station("广州东站", "Guangzhou East Railway Station"),
                                    .station("广州站", "Guangzhou Railway Station")],
                         airports: [.airport("广州白云国际机场", "Guangzhou Baiyun International Airport", "CAN")]),
        LioTransportCity(id: "shenzhen", nameZH: "深圳", nameEN: "Shenzhen", aliases: [], railSlug: "shenzhen",
                         flightCityCode: "SZX",
                         stations: [.station("深圳北站", "Shenzhen North Railway Station"),
                                    .station("福田站", "Futian Railway Station"),
                                    .station("深圳站", "Shenzhen Railway Station")],
                         airports: [.airport("深圳宝安国际机场", "Shenzhen Bao'an International Airport", "SZX")]),
        LioTransportCity(id: "chengdu", nameZH: "成都", nameEN: "Chengdu", aliases: [], railSlug: "chengdu",
                         flightCityCode: "CTU",
                         stations: [.station("成都东站", "Chengdu East Railway Station"),
                                    .station("成都西站", "Chengdu West Railway Station"),
                                    .station("成都南站", "Chengdu South Railway Station")],
                         airports: [.airport("成都天府国际机场", "Chengdu Tianfu International Airport", "TFU"),
                                    .airport("成都双流国际机场", "Chengdu Shuangliu International Airport", "CTU")]),
        LioTransportCity(id: "chongqing", nameZH: "重庆", nameEN: "Chongqing", aliases: ["Chungking"], railSlug: "chongqing",
                         flightCityCode: "CKG",
                         stations: [.station("重庆北站", "Chongqing North Railway Station"),
                                    .station("重庆西站", "Chongqing West Railway Station")],
                         airports: [.airport("重庆江北国际机场", "Chongqing Jiangbei International Airport", "CKG")]),
        LioTransportCity(id: "xian", nameZH: "西安", nameEN: "Xi'an", aliases: ["Sian"], railSlug: "xian",
                         flightCityCode: "SIA",
                         stations: [.station("西安北站", "Xi'an North Railway Station"),
                                    .station("西安站", "Xi'an Railway Station")],
                         airports: [.airport("西安咸阳国际机场", "Xi'an Xianyang International Airport", "XIY")]),
        LioTransportCity(id: "hangzhou", nameZH: "杭州", nameEN: "Hangzhou", aliases: [], railSlug: "hangzhou",
                         flightCityCode: "HGH",
                         stations: [.station("杭州东站", "Hangzhou East Railway Station"),
                                    .station("杭州西站", "Hangzhou West Railway Station"),
                                    .station("杭州站", "Hangzhou Railway Station")],
                         airports: [.airport("杭州萧山国际机场", "Hangzhou Xiaoshan International Airport", "HGH")]),
        LioTransportCity(id: "nanjing", nameZH: "南京", nameEN: "Nanjing", aliases: ["Nanking"], railSlug: "nanjing",
                         flightCityCode: "NKG",
                         stations: [.station("南京南站", "Nanjing South Railway Station"),
                                    .station("南京站", "Nanjing Railway Station")],
                         airports: [.airport("南京禄口国际机场", "Nanjing Lukou International Airport", "NKG")]),
        LioTransportCity(id: "wuhan", nameZH: "武汉", nameEN: "Wuhan", aliases: [], railSlug: "wuhan",
                         flightCityCode: "WUH",
                         stations: [.station("武汉站", "Wuhan Railway Station"),
                                    .station("汉口站", "Hankou Railway Station"),
                                    .station("武昌站", "Wuchang Railway Station")],
                         airports: [.airport("武汉天河国际机场", "Wuhan Tianhe International Airport", "WUH")]),
        LioTransportCity(id: "guilin", nameZH: "桂林", nameEN: "Guilin", aliases: [], railSlug: "guilin",
                         flightCityCode: "KWL",
                         stations: [.station("桂林北站", "Guilin North Railway Station"),
                                    .station("桂林西站", "Guilin West Railway Station"),
                                    .station("桂林站", "Guilin Railway Station")],
                         airports: [.airport("桂林两江国际机场", "Guilin Liangjiang International Airport", "KWL")]),
        LioTransportCity(id: "kunming", nameZH: "昆明", nameEN: "Kunming", aliases: [], railSlug: "kunming",
                         flightCityCode: "KMG",
                         stations: [.station("昆明南站", "Kunming South Railway Station"),
                                    .station("昆明站", "Kunming Railway Station")],
                         airports: [.airport("昆明长水国际机场", "Kunming Changshui International Airport", "KMG")]),
    ]
}

struct LioTransportQuery: Equatable, Sendable {
    enum Problem: Error, Equatable, Sendable {
        case unknownFrom, unknownTo, sameCity, pastDate

        func message(_ language: LioLanguage) -> String {
            switch self {
            case .unknownFrom:
                language.text("Choose a departure city from the list, e.g. Shanghai.", "请从列表选择出发城市，例如上海。")
            case .unknownTo:
                language.text("Choose a destination city from the list, e.g. Beijing.", "请从列表选择到达城市，例如北京。")
            case .sameCity:
                language.text("Departure and destination are the same city.", "出发和到达是同一个城市。")
            case .pastDate:
                language.text("Choose today or a later date.", "请选择今天或以后的日期。")
            }
        }
    }

    let from: LioTransportCity
    let to: LioTransportCity
    /// Travel day in China time, `YYYY-MM-DD`.
    let day: String

    var swapped: Self { Self(from: to, to: from, day: day) }

    static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        return calendar
    }()

    static func make(from: String, to: String, date: Date, today: Date = Date()) -> Result<Self, Problem> {
        guard let origin = LioTransportCity.resolve(from) else { return .failure(.unknownFrom) }
        guard let destination = LioTransportCity.resolve(to) else { return .failure(.unknownTo) }
        guard origin != destination else { return .failure(.sameCity) }
        let day = dayString(date)
        guard day >= dayString(today) else { return .failure(.pastDate) }
        return .success(Self(from: origin, to: destination, day: day))
    }

    static func dayString(_ date: Date) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    /// Noon China time on the given day.
    static func date(year: Int, month: Int, day: Int) -> Date {
        calendar.date(from: DateComponents(year: year, month: month, day: day, hour: 12))!
    }
}

struct LioTransportFare: Equatable, Hashable, Sendable {
    let classZH: String
    let classEN: String
    /// CNY fen.
    let priceMinor: Int

    func className(_ language: LioLanguage) -> String {
        language == .chinese ? classZH : classEN
    }
}

struct LioTransportOption: Equatable, Hashable, Identifiable, Sendable {
    let mode: LioTransportMode
    /// Train or flight number, e.g. `G2`, `MU5101`.
    let number: String
    let carrierZH: String?
    let carrierEN: String?
    let departure: LioTransportHub
    let arrival: LioTransportHub
    /// Local times `HH:mm`.
    let departTime: String
    let arriveTime: String
    let durationMinutes: Int
    let fares: [LioTransportFare]

    var id: String { [mode.rawValue, number, departTime].joined(separator: "|") }

    var lowestPriceMinor: Int? { fares.map(\.priceMinor).min() }

    /// Days after the departure day on which the service arrives, from the departure clock time plus the
    /// duration (so trips longer than a day are counted correctly).
    var arrivalDayOffset: Int {
        let parts = departTime.split(separator: ":").compactMap { Int($0) }
        // An unreadable departure time never guesses a day change.
        guard parts.count == 2, (0..<24).contains(parts[0]), (0..<60).contains(parts[1]) else { return 0 }
        return (parts[0] * 60 + parts[1] + durationMinutes) / 1440
    }

    var arrivesNextDay: Bool { arrivalDayOffset > 0 }

    func carrier(_ language: LioLanguage) -> String? {
        language == .chinese ? carrierZH : carrierEN
    }
}

enum LioTransportModeResult: Equatable, Sendable {
    case options([LioTransportOption])
    /// No timetable source for this mode yet: show the guide and booking links only.
    case guideOnly
    /// The source failed for this mode only; other modes still show.
    case unavailable

    var options: [LioTransportOption] {
        if case .options(let options) = self { return options }
        return []
    }

    var fastestMinutes: Int? { options.map(\.durationMinutes).min() }
    var lowestPriceMinor: Int? { options.compactMap(\.lowestPriceMinor).min() }
}

struct LioTransportResult: Equatable, Sendable {
    let query: LioTransportQuery
    let rail: LioTransportModeResult
    let flight: LioTransportModeResult
    let bus: LioTransportModeResult
    /// Debug preview data; the screen labels it as a sample.
    let isSample: Bool

    func result(for mode: LioTransportMode) -> LioTransportModeResult {
        switch mode {
        case .rail: rail
        case .flight: flight
        case .bus: bus
        }
    }
}

struct LioTransportService: Sendable {
    let search: @Sendable (LioTransportQuery) async throws -> LioTransportResult

    /// The first version without a timetable source (#1518 plan A): guide, stations and booking links only.
    static let guideOnly = LioTransportService { query in
        LioTransportResult(query: query, rail: .guideOnly, flight: .guideOnly, bus: .guideOnly, isSample: false)
    }
}

struct LioTransportBookingLink: Equatable, Sendable {
    enum Provider: Equatable, Sendable {
        case railway12306, tripCom

        func label(_ language: LioLanguage) -> String {
            switch self {
            case .railway12306: language.text("12306 (China Railway)", "12306 铁路官网")
            case .tripCom: "Trip.com"
            }
        }
    }

    let provider: Provider
    let url: URL
    /// True only for a server hand-off link that carries an affiliate ID (after the Trip.com credentials are
    /// handed over, #1368); the links built in the app are plain public pages.
    let affiliate: Bool

    init(provider: Provider, url: URL, affiliate: Bool = false) {
        self.provider = provider
        self.url = url
        self.affiliate = affiliate
    }
}

/// Booking copy (#225, wording confirmed by JT 2026-11-25; same as Hotels).
enum LioTransportCopy {
    static func disclosure(_ language: LioLanguage) -> String {
        language.text(
            "Some links are affiliate links. If you book through them, Go2China may earn a commission at no extra cost to you.",
            "部分链接为推广链接，你通过它预订时，Go2China 可能获得佣金，价格不受影响。"
        )
    }

    /// The disclosure appears once under the list, and only when a shown link really carries an affiliate ID.
    static func showsDisclosure(_ links: [LioTransportBookingLink]) -> Bool {
        links.contains(where: \.affiliate)
    }

    /// Always shown at the bottom, naming the platforms the page actually links to.
    static func footer(_ mode: LioTransportMode?, _ language: LioLanguage) -> String {
        switch mode {
        case .rail:
            language.text("Booking and payment happen on 12306 or Trip.com, not in Go2China.",
                          "预订和付款在 12306 或 Trip.com 完成，不在 Go2China 内进行。")
        case .flight:
            language.text("Booking and payment happen on Trip.com, not in Go2China.",
                          "预订和付款在 Trip.com 完成，不在 Go2China 内进行。")
        case .bus:
            language.text("Tickets are bought and paid for at the bus station, not in Go2China.",
                          "购票和付款在客运站完成，不在 Go2China 内进行。")
        case nil:
            language.text("Booking and payment happen on 12306, Trip.com or at the station, not in Go2China.",
                          "预订和付款在 12306、Trip.com 或车站完成，不在 Go2China 内进行。")
        }
    }
}

/// Plain public pages (no affiliate tag; that would need JT's approval, #1518).
enum LioTransportLinks {
    static func booking(_ mode: LioTransportMode, query: LioTransportQuery,
                        language: LioLanguage) -> [LioTransportBookingLink] {
        switch mode {
        case .rail:
            let official = language == .chinese ? "https://www.12306.cn/index/" : "https://www.12306.cn/en/index.html"
            let (origin, destination) = (query.from.railSlug, query.to.railSlug)
            let route = "https://www.trip.com/trains/china/route/\(origin)-to-\(destination)/"
            return [LioTransportBookingLink(provider: .railway12306, url: URL(string: official)!),
                    LioTransportBookingLink(provider: .tripCom, url: URL(string: route)!)]
        case .flight:
            var components = URLComponents(string: "https://www.trip.com/flights/showfarefirst")!
            components.queryItems = [
                URLQueryItem(name: "dcity", value: query.from.flightCityCode.lowercased()),
                URLQueryItem(name: "acity", value: query.to.flightCityCode.lowercased()),
                URLQueryItem(name: "ddate", value: query.day),
                URLQueryItem(name: "triptype", value: "ow"),
                URLQueryItem(name: "class", value: "y"),
                URLQueryItem(name: "quantity", value: "1"),
            ]
            return [LioTransportBookingLink(provider: .tripCom, url: components.url!)]
        case .bus:
            return []
        }
    }
}

enum LioTransportFormat {
    static func duration(_ minutes: Int, _ language: LioLanguage) -> String {
        let hours = minutes / 60
        let rest = minutes % 60
        switch (hours, rest) {
        case (0, _): return language.text("\(rest)m", "\(rest)分")
        case (_, 0): return language.text("\(hours)h", "\(hours)小时")
        default: return language.text("\(hours)h \(rest)m", "\(hours)小时\(rest)分")
        }
    }

    static func price(_ minor: Int) -> String {
        let yuan = minor / 100
        let fen = minor % 100
        if fen == 0 { return "¥\(yuan)" }
        if fen % 10 == 0 { return "¥\(yuan).\(fen / 10)" }
        return "¥\(yuan)." + String(format: "%02d", fen)
    }

    static func arrival(_ option: LioTransportOption, _ language: LioLanguage) -> String {
        let offset = option.arrivalDayOffset
        return offset > 0 ? "\(option.arriveTime) +\(offset)" : option.arriveTime
    }

    /// What VoiceOver reads for the arrival: the day change in words rather than "+1".
    static func arrivalSpoken(_ option: LioTransportOption, _ language: LioLanguage) -> String {
        let time = option.arriveTime
        switch option.arrivalDayOffset {
        case 0: return language.text("Arrives \(time)", "\(time) 到达")
        case 1: return language.text("Arrives \(time) the next day", "次日 \(time) 到达")
        case let days: return language.text("Arrives \(time), \(days) days later", "\(days) 天后 \(time) 到达")
        }
    }

    static func from(_ minor: Int, _ language: LioLanguage) -> String {
        language.text("from \(price(minor))", "\(price(minor)) 起")
    }
}

extension LioTransportService {
    /// The service for this build, or `nil` to hide the tool. Off unless Info.plist sets
    /// `G2CTransportEnabled = YES` (JT decides when); Debug can show sample data with `--lio-transport-preview`.
    static func fromBuild(arguments: [String] = ProcessInfo.processInfo.arguments,
                          info: [String: Any]? = Bundle.main.infoDictionary) -> LioTransportService? {
        #if DEBUG
        if arguments.contains("--lio-transport-preview") { return .preview }
        #endif
        guard info?["G2CTransportEnabled"] as? String == "YES" else { return nil }
        return .guideOnly
    }
}
