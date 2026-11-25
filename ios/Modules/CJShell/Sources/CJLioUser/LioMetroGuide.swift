import Foundation

/// The parts of mainland China a city belongs to, in the order the city list shows them.
enum LioMetroRegion: String, CaseIterable, Codable, Sendable {
    case north, northeast, east, central, south, southwest, northwest

    func name(in language: LioLanguage) -> String {
        switch self {
        case .north: language.text("North", "华北")
        case .northeast: language.text("Northeast", "东北")
        case .east: language.text("East", "华东")
        case .central: language.text("Central", "华中")
        case .south: language.text("South", "华南")
        case .southwest: language.text("Southwest", "西南")
        case .northwest: language.text("Northwest", "西北")
        }
    }
}

/// A mainland city with a metro (#1421, #1450). The list is the bundled maps themselves; every listed city
/// has an interactive map. A few also have an operator-checked written guide with official links.
struct LioMetroCity: Hashable, Identifiable, Sendable {
    let id: String
    let nameZH: String
    let nameEN: String
    let provinceZH: String
    let region: LioMetroRegion

    var rawValue: String { id }

    func name(in language: LioLanguage) -> String { language.text(nameEN, nameZH) }

    /// The city's Chinese name, shown on its card in both languages so travellers can match signs.
    var nativeName: String { nameZH }

    var identifier: String { "lio.metro.city." + id }

    /// The bundled interactive map in `Resources/Metro`.
    var mapResource: String? { "LioMetroMap.\(id).v1" }

    /// Taxi place search covers only some cities; elsewhere the station sheet offers directions only.
    var taxiCity: LioTaxiCity? { LioTaxiCity(rawValue: id) }

    /// Operator-checked guide details, for the cities that have them.
    var guide: LioMetroCityGuide? { LioMetroCityGuide.known[id] }

    func summary(in language: LioLanguage) -> String {
        if id == "shanghai" { return language.text("Interactive line map, tickets and transport card", "线路图 · 单程票 · 交通卡") }
        if guide != nil { return language.text("Interactive line map, tickets and security", "线路图 · 买票 · 安检") }
        return language.text("Interactive line map", "可交互线路图")
    }

    func buying(in language: LioLanguage) -> String {
        guide?.buying(language) ?? language.text(
            "Buy a single-journey ticket at a station machine: choose your destination station, then pay. Staff at the service centre can help if you show the station name.",
            "在车站售票机选择目的站后购买单程票。需要帮助时，可把站名出示给服务中心的工作人员。"
        )
    }

    func entering(in language: LioLanguage) -> String {
        language.text(
            "At the gate, follow the sign for your ticket or card. Keep the same ticket or card for the exit. On the platform, check the line's final station to confirm you're boarding in the right direction.",
            "按闸机提示使用车票或交通卡，保留同一凭证以便出站。在站台看列车终点站，确认乘坐方向。"
        )
    }

    func security(in language: LioLanguage) -> String {
        language.text(
            "Allow a little extra time for station security. Follow staff instructions for your bags and other belongings before going to the gates.",
            "预留一点安检时间。过闸前按工作人员指引接受随身物品检查。"
        )
    }
}

extension LioMetroCity {
    /// Every city in the bundled catalogue, grouped by region in catalogue order.
    static let allCases: [LioMetroCity] = catalogue()

    static func named(_ id: String) -> LioMetroCity? { allCases.first { $0.id == id } }

    /// The bundled source notice for the maps (`Resources/Metro/NOTICE.md`).
    static var noticeURL: URL? { Bundle.module.url(forResource: "NOTICE", withExtension: "md", subdirectory: "Metro") }

    static func cities(in region: LioMetroRegion, matching query: String = "") -> [LioMetroCity] {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return allCases.filter { city in
            city.region == region && (text.isEmpty || city.nameZH.localizedStandardContains(text)
                || city.nameEN.localizedStandardContains(text) || city.provinceZH.localizedStandardContains(text)
                || city.id.localizedStandardContains(text))
        }
    }

    /// The catalogue is whatever maps are bundled: each map file carries its city's entry, so removing a
    /// city means deleting its one file and regenerating `Resources/Metro/NOTICE.md`, with no code change.
    /// A file whose entry does not read is left out rather than emptying the list; the data tests fail on it.
    static func catalogue() -> [LioMetroCity] {
        let entries = mapFiles.compactMap { try? read(entry: Data(contentsOf: $0)) }
        // One entry per city: a second file naming the same city is ignored instead of crashing the list.
        let order = Dictionary(entries.map { ($0.city.id, $0.order) }, uniquingKeysWith: { first, _ in first })
        var seen = Set<String>()
        return sorted(entries.map(\.city).filter { seen.insert($0.id).inserted }, order: order)
    }

    /// The bundled map files, one per city, in file-name order.
    static var mapFiles: [URL] {
        (Bundle.module.urls(forResourcesWithExtension: "json", subdirectory: "Metro") ?? [])
            .filter { $0.lastPathComponent.hasPrefix("LioMetroMap.") }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    private struct Header: Decodable {
        struct Info: Decodable {
            let nameZH, nameEN, provinceZH: String
            let region: LioMetroRegion
            let order: Int
        }
        let city: String
        let cityInfo: Info
    }

    /// Checks one map file's city entry at the boundary: an id, names in both languages, a known region.
    static func read(entry data: Data) throws -> (city: LioMetroCity, order: Int) {
        guard let header = try? JSONDecoder().decode(Header.self, from: data) else { throw LioMetroMapFailure.unreadable }
        let info = header.cityInfo
        guard !header.city.isEmpty, !info.nameZH.isEmpty, !info.nameEN.isEmpty, !info.provinceZH.isEmpty else {
            throw LioMetroMapFailure.invalid("city entry")
        }
        return (.init(id: header.city, nameZH: info.nameZH, nameEN: info.nameEN, provinceZH: info.provinceZH,
                      region: info.region), info.order)
    }

    /// Region order first, then the catalogue's own order within a region.
    static func sorted(_ cities: [LioMetroCity], order: [String: Int]) -> [LioMetroCity] {
        cities.sorted {
            let a = LioMetroRegion.allCases.firstIndex(of: $0.region) ?? 0, b = LioMetroRegion.allCases.firstIndex(of: $1.region) ?? 0
            return (a, order[$0.id] ?? 0, $0.id) < (b, order[$1.id] ?? 0, $1.id)
        }
    }
}

/// Written-guide details checked on each operator's own site (#1421).
struct LioMetroCityGuide: Sendable {
    let mapURL: URL
    let guideURL: URL
    let buyingEN: String
    let buyingZH: String

    func buying(_ language: LioLanguage) -> String { language.text(buyingEN, buyingZH) }

    static let known: [String: LioMetroCityGuide] = [
        "beijing": .init(
            mapURL: URL(string: "https://map.bjsubway.com/mobile")!,
            guideURL: URL(string: "https://english.beijing.gov.cn/travellinginbeijing/transportation/beijingsubway/202512/t20251229_4374803.html")!,
            buyingEN: "At the ticket machine, switch to English and choose your destination. You can also show the station name to staff at the ticket counter.",
            buyingZH: "在售票机上切换到英文后选择目的站，也可以把站名出示给人工窗口的工作人员。"),
        "shanghai": .init(
            mapURL: URL(string: "https://service.shmetro.com/czxx/index.htm")!,
            guideURL: URL(string: "https://service.shmetro.com/cczn/index.htm")!,
            buyingEN: "Buy a single-ride ticket at a station machine or service counter. If you already use a Shanghai transport card, you can use it at the gates.",
            buyingZH: "可到车站售票机或服务中心购单程票。已有上海公共交通卡时，可在闸机刷卡进站。"),
        "guangzhou": .init(
            mapURL: URL(string: "https://cs.gzmtr.com/ckfw/")!,
            guideURL: URL(string: "https://cs.gzmtr.com/ckfw/pwzy_202001/")!,
            buyingEN: "Buy a single-journey ticket at a station machine: choose the line and your destination station, then pay. Staff at the customer service centre can help if you show the station name.",
            buyingZH: "在车站售票机选择线路和目的站后购买单程票。需要帮助时，可把站名出示给客服中心的工作人员。"),
        "shenzhen": .init(
            mapURL: URL(string: "https://www.szmc.net/map/")!,
            guideURL: URL(string: "https://www.szmc.net/shentieyunying/yunyingzixun/piaowuxinxi/ditiepiaojiajizhengce/")!,
            buyingEN: "Buy a single-journey token at a station machine: choose your destination station, then pay. Keep the token for the exit gate. Staff at the service centre can help if you show the station name.",
            buyingZH: "在车站售票机选择目的站后购买单程票，出站时投入闸机，请妥善保管。需要帮助时，可把站名出示给客服中心的工作人员。"),
        "xian": .init(
            mapURL: URL(string: "https://m.xianrail.com/metroRoute")!,
            guideURL: URL(string: "https://m.xianrail.com/operations")!,
            buyingEN: "Buy a single-journey ticket at a station machine: choose your destination station, then pay. Staff at the service centre can help if you show the station name.",
            buyingZH: "在车站售票机选择目的站后购买单程票。需要帮助时，可把站名出示给服务中心的工作人员。"),
        "chengdu": .init(
            mapURL: URL(string: "https://www.chengdurail.com/index/jtxwt.htm")!,
            guideURL: URL(string: "https://www.chengdurail.com/ckfw/pwzc.htm")!,
            buyingEN: "Buy a single-ride ticket on arrival. Select your destination on the machine, or show the station name at the service counter if you need help.",
            buyingZH: "进站时可买单程票。在售票机选择目的站，需要帮助时可把站名出示给服务中心。"),
    ]
}

/// The three steps of the written guide, in the order a traveller meets them.
enum LioMetroGuideSection: CaseIterable {
    case ticket, security, gates

    var identifier: String {
        switch self {
        case .ticket: "lio.metro.ticket"
        case .security: "lio.metro.security"
        case .gates: "lio.metro.gates"
        }
    }

    var symbol: String {
        switch self {
        case .ticket: "ticket"
        case .security: "checkmark.shield"
        case .gates: "tram"
        }
    }

    func title(in language: LioLanguage) -> String {
        switch self {
        case .ticket: language.text("Buy a ticket", "买票")
        case .security: language.text("Security check", "安检")
        case .gates: language.text("Enter and exit", "进站与出站")
        }
    }

    func text(for city: LioMetroCity, in language: LioLanguage) -> String {
        switch self {
        case .ticket: city.buying(in: language)
        case .security: city.security(in: language)
        case .gates: city.entering(in: language)
        }
    }
}
