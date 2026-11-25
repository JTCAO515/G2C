/// The Tools tab (formerly "插件"): one card per tool with an icon, a name and one sentence.
/// Tools whose service is not enabled for this build are left out rather than shown disabled.
enum LioTool: CaseIterable, Sendable {
    case arrival, localSupport, taxi, hotels, roadbook, transport, nearby, currency, metro, payment, translation, phrases

    var symbol: String {
        switch self {
        case .arrival: "airplane.arrival"
        case .localSupport: "lifepreserver"
        case .taxi: "car.fill"
        case .nearby: "mappin.and.ellipse"
        case .currency: "yensign.circle"
        case .metro: "tram.fill"
        case .payment: "wallet.pass"
        case .translation: "character.bubble"
        case .phrases: "text.bubble"
        case .hotels: "bed.double"
        case .roadbook: "book.closed"
        case .transport: "train.side.front.car"
        }
    }

    var identifier: String {
        switch self {
        case .arrival: "lio.tools.arrival"
        case .localSupport: "lio.tools.local-support"
        case .taxi: "lio.tools.taxi"
        case .nearby: "lio.tools.nearby"
        case .currency: "lio.tools.currency"
        case .metro: "lio.tools.metro-guide"
        case .payment: "lio.tools.payment-guide"
        case .translation: "lio.tools.translation"
        case .phrases: "lio.tools.phrase-cards"
        case .hotels: "lio.tools.hotels"
        case .roadbook: "lio.tools.roadbook"
        case .transport: "lio.tools.transport"
        }
    }

    func name(_ language: LioLanguage) -> String {
        switch self {
        case .arrival: language.text("Arrival Mode", "落地模式")
        case .localSupport: language.text("Local Support", "本地协助")
        case .taxi: language.text("Taxi", "打车")
        case .nearby: language.text("Nearby", "附近")
        case .currency: language.text("Currency Converter", "汇率换算")
        case .metro: language.text("Metro Guide", "地铁指南")
        case .payment: language.text("Payment Setup Guide", "支付开通指南")
        case .translation: language.text("Translation", "翻译")
        case .phrases: language.text("Phrase Cards", "常用语卡片")
        case .hotels: language.text("Hotels", "酒店")
        case .roadbook: language.text("Roadbook", "路书")
        case .transport: language.text("Intercity Travel", "城际交通")
        }
    }

    /// One short sentence under the name; kept to two lines at the default text size.
    func summary(_ language: LioLanguage) -> String {
        switch self {
        case .arrival: language.text("Your first hours in China, step by step", "落地首日要做的事")
        case .localSupport: language.text("Emergency numbers, embassies, help cards", "急救、使领馆和求助卡")
        case .taxi: language.text("Find a place and open DiDi", "搜地点，用滴滴打车")
        case .nearby: language.text("Food, sights and shops around you", "身边的美食和景点")
        case .currency: language.text("Convert yuan at ECB reference rates", "人民币外币参考换算")
        case .metro: language.text("Interactive line maps by city", "各城市可交互线路图")
        case .payment: language.text("Set up Alipay and Weixin Pay", "开通支付宝和微信支付")
        case .translation: language.text("Type, speak or snap a photo", "打字、说话或拍照翻译")
        case .phrases: language.text("Show or play common phrases", "常用语大字给对方看")
        case .hotels: language.text("Find hotels by city and dates", "按城市和日期找酒店")
        case .roadbook: language.text("Your trip day by day, offline", "按天离线看的旅行手册")
        case .transport: language.text("Compare trains, flights and buses", "比较火车、飞机和大巴")
        }
    }

    func accessibilityLabel(_ language: LioLanguage) -> String {
        name(language) + language.text(", ", "，") + summary(language)
    }
}

enum LioToolCatalog {
    struct Availability: Equatable, Sendable {
        var taxi = false
        var currency = false
        var hotels = false
        var nearby = false
        /// #1515: `G2CRoadbookEnabled`, off unless the build says YES.
        var roadbook = false
        /// #1519: `G2CTransportEnabled`, off unless the build says YES.
        var transport = false
        /// `G2CArrivalModeEnabled`, off unless the build says YES; JT decides when to turn it on.
        var arrival = false
    }

    static func title(_ language: LioLanguage) -> String {
        language.text("Tools", "工具")
    }

    static func visible(_ availability: Availability) -> [LioTool] {
        LioTool.allCases.filter { tool in
            switch tool {
            case .taxi: availability.taxi
            case .nearby: availability.nearby
            case .currency: availability.currency
            case .hotels: availability.hotels
            case .roadbook: availability.roadbook
            case .transport: availability.transport
            case .arrival: availability.arrival
            case .localSupport, .metro, .payment, .translation, .phrases: true
            }
        }
    }
}
