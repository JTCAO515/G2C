import Foundation

enum LioMetroCity: String, CaseIterable, Identifiable {
    case beijing, shanghai, guangzhou, chengdu

    var id: Self { self }

    func name(in language: LioLanguage) -> String {
        switch self {
        case .beijing: language.text("Beijing", "北京")
        case .shanghai: language.text("Shanghai", "上海")
        case .guangzhou: language.text("Guangzhou", "广州")
        case .chengdu: language.text("Chengdu", "成都")
        }
    }

    var mapURL: URL {
        switch self {
        case .beijing: URL(string: "https://map.bjsubway.com/mobile")!
        case .shanghai: URL(string: "https://service.shmetro.com/czxx/index.htm")!
        case .guangzhou: URL(string: "https://cs.gzmtr.com/ckfw/")!
        case .chengdu: URL(string: "https://www.chengdurail.com/index/jtxwt.htm")!
        }
    }

    var guideURL: URL {
        switch self {
        case .beijing:
            URL(string: "https://english.beijing.gov.cn/travellinginbeijing/transportation/beijingsubway/202512/t20251229_4374803.html")!
        case .shanghai: URL(string: "https://service.shmetro.com/cczn/index.htm")!
        case .guangzhou: URL(string: "https://cs.gzmtr.com/ckfw/pwzy_202001/")!
        case .chengdu: URL(string: "https://www.chengdurail.com/ckfw/pwzc.htm")!
        }
    }

    func buying(in language: LioLanguage) -> String {
        switch self {
        case .beijing:
            language.text(
                "At the ticket machine, switch to English and choose your destination. You can also show the station name to staff at the ticket counter.",
                "在售票机上切换到英文后选择目的站，也可以把站名出示给人工窗口的工作人员。"
            )
        case .shanghai:
            language.text(
                "Buy a single-ride ticket at a station machine or service counter. If you already use a Shanghai transport card, you can use it at the gates.",
                "可到车站售票机或服务中心购单程票。已有上海公共交通卡时，可在闸机刷卡进站。"
            )
        case .guangzhou:
            language.text(
                "Buy a single-journey ticket at a station machine: choose the line and your destination station, then pay. Staff at the customer service centre can help if you show the station name.",
                "在车站售票机选择线路和目的站后购买单程票。需要帮助时，可把站名出示给客服中心的工作人员。"
            )
        case .chengdu:
            language.text(
                "Buy a single-ride ticket on arrival. Select your destination on the machine, or show the station name at the service counter if you need help.",
                "进站时可买单程票。在售票机选择目的站，需要帮助时可把站名出示给服务中心。"
            )
        }
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
    /// The city's Chinese name, shown on its card in both languages so travellers can match signs.
    var nativeName: String { name(in: .chinese) }

    var identifier: String { "lio.metro.city." + rawValue }

    /// The bundled interactive map, for cities whose operator data has been checked (#1450).
    var mapResource: String? {
        switch self {
        case .beijing, .shanghai, .guangzhou: "LioMetroMap.\(rawValue).v1"
        case .chengdu: nil
        }
    }

    var taxiCity: LioTaxiCity {
        switch self {
        case .beijing: .beijing
        case .shanghai: .shanghai
        case .guangzhou: .guangzhou
        case .chengdu: .chengdu
        }
    }

    func summary(in language: LioLanguage) -> String {
        switch self {
        case .beijing, .guangzhou: language.text("Interactive line map, tickets and security", "可交互线路图、买票和安检")
        case .shanghai: language.text("Interactive line map, tickets and transport card", "可交互线路图、单程票和交通卡")
        case .chengdu: language.text("Tickets, security and the official map", "买票、安检和官方线路图")
        }
    }
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
