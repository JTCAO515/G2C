import Foundation

/// Cities offered for taxi place search. The relay searches within the chosen city,
/// so a pickup near one of these centres preselects it.
enum LioTaxiCity: String, CaseIterable, Codable, Identifiable, Sendable {
    case beijing, shanghai, chengdu, guangzhou, shenzhen, xian, hangzhou, chongqing

    var id: Self { self }

    var nameZH: String {
        switch self {
        case .beijing: "北京"
        case .shanghai: "上海"
        case .chengdu: "成都"
        case .guangzhou: "广州"
        case .shenzhen: "深圳"
        case .xian: "西安"
        case .hangzhou: "杭州"
        case .chongqing: "重庆"
        }
    }

    var nameEN: String {
        switch self {
        case .beijing: "Beijing"
        case .shanghai: "Shanghai"
        case .chengdu: "Chengdu"
        case .guangzhou: "Guangzhou"
        case .shenzhen: "Shenzhen"
        case .xian: "Xi'an"
        case .hangzhou: "Hangzhou"
        case .chongqing: "Chongqing"
        }
    }

    /// A well-known place used as the search field hint.
    var exampleZH: String {
        switch self {
        case .beijing: "天安门"
        case .shanghai: "外滩"
        case .chengdu: "宽窄巷子"
        case .guangzhou: "广州塔"
        case .shenzhen: "世界之窗"
        case .xian: "钟楼"
        case .hangzhou: "西湖"
        case .chongqing: "解放碑"
        }
    }

    func name(in language: LioLanguage) -> String {
        language == .chinese ? nameZH : nameEN
    }

    private var centre: (latitude: Double, longitude: Double) {
        switch self {
        case .beijing: (39.9042, 116.4074)
        case .shanghai: (31.2304, 121.4737)
        case .chengdu: (30.5728, 104.0668)
        case .guangzhou: (23.1291, 113.2644)
        case .shenzhen: (22.5431, 114.0579)
        case .xian: (34.3416, 108.9398)
        case .hangzhou: (30.2741, 120.1551)
        case .chongqing: (29.5630, 106.5516)
        }
    }

    /// The supported city whose centre lies within 120 km of the point, if any.
    /// WGS-84 and GCJ-02 differ by a few hundred metres, which does not matter at this scale.
    static func nearest(to point: LioTaxiPlace.Coordinate) -> LioTaxiCity? {
        allCases
            .map { ($0, $0.distanceKilometres(to: point)) }
            .filter { $0.1 <= 120 }
            .min { $0.1 < $1.1 }?.0
    }

    private func distanceKilometres(to point: LioTaxiPlace.Coordinate) -> Double {
        let radians = Double.pi / 180
        let lat1 = centre.latitude * radians, lat2 = point.latitude * radians
        let dLat = lat2 - lat1, dLng = (point.longitude - centre.longitude) * radians
        let a = sin(dLat / 2) * sin(dLat / 2) + cos(lat1) * cos(lat2) * sin(dLng / 2) * sin(dLng / 2)
        return 6_371 * 2 * atan2(a.squareRoot(), (1 - a).squareRoot())
    }
}

struct LioTaxiSearchQuery: Equatable, Sendable {
    static let maximumLength = 80

    let text: String
    let city: LioTaxiCity
    let near: LioTaxiPlace.Coordinate?
    /// English screens ask the relay for optional English names and addresses (TAXI.1 `locale`, approved by
    /// JT in #1459 and live in Hong Kong since #1450's build 55 readiness receipt).
    let english: Bool

    init(text: String, city: LioTaxiCity, near: LioTaxiPlace.Coordinate?, english: Bool = false) {
        self.text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        self.city = city
        self.near = near
        self.english = english
    }
}

/// Explicit notices for the place picker: what was searched, where, and what to try next.
enum LioTaxiSearchNotice {
    static func noMatches(for query: LioTaxiSearchQuery, language: LioLanguage) -> String {
        let city = query.city, typed = query.text
        return language.text(
            "No places found for “\(typed)” in \(city.nameEN). Check the city, try the Chinese name (for example “\(city.exampleZH)”), or add a street.",
            "在\(city.nameZH)没有找到“\(typed)”。请确认城市，或换个叫法（例如“\(city.exampleZH)”），也可以加上路名。"
        )
    }

    static func failure(_ error: Error, language: LioLanguage) -> String {
        if let error = error as? URLError,
           [.notConnectedToInternet, .networkConnectionLost, .dataNotAllowed].contains(error.code) {
            return language.text("You’re offline. Check your connection and search again.",
                                 "网络暂不可用，请检查连接后再搜索。")
        }
        switch error as? LioTaxiFailure {
        case .notEnabled:
            return language.text("Place search isn’t available for this account yet.", "此账号暂未开通地点搜索。")
        case .quotaExceeded:
            return language.text("Place search has reached its limit for now. Try again later.", "地点搜索次数已达上限，请稍后再试。")
        case .rateLimited:
            return language.text("Too many searches right now. Wait a moment, then search again.", "搜索太频繁，请稍等片刻再搜索。")
        case .outOfService:
            return language.text("Place search covers mainland China only. Choose a mainland city.", "地点搜索只支持中国大陆城市，请换一个城市。")
        case .signInRequired:
            return language.text("Sign in again, then search.", "请重新登录后再搜索。")
        case .timedOut:
            return language.text("Search took too long. Try again.", "搜索超时，请重试。")
        case .queryTooLong:
            return language.text("Use a shorter name.", "请输入更短的地点名称。")
        default:
            return language.text("Search isn’t available right now. Try again.", "搜索暂不可用，请重试。")
        }
    }
}
