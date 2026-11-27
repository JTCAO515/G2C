import Foundation

/// Airport and railway-station facts for the 大交通 page (#2007), from the place library's `category=hub`
/// entries (`knowledge/places`, #1985), bundled as `LioTransportHubs.v1.json`. Nothing is fetched.
///
/// The bundled pack says whether it is a `draft` (Codex research, not yet reviewed by JT) or `approved`
/// (generated from the reviewed library). A draft is shown only in Debug and in builds whose Info.plist sets
/// `G2CTransportHubsDraftEnabled = YES` (internal TestFlight, so JT can review on the phone), and every entry
/// then carries a 待核 badge. An approved pack is always shown.
struct LioHubPlace: Decodable, Equatable, Identifiable, Sendable {
    struct Terminal: Decodable, Equatable, Sendable {
        let name: String
        let noteZh: String?
        let noteEn: String?
    }

    enum Kind: String, Decodable, Sendable { case airport, rail }

    let id: String
    let city: String
    let hubType: Kind
    let nameZh: String
    let nameEn: String
    /// IATA code for airports.
    let code: String?
    let terminals: [Terminal]?
    let toCityZh: [String]?
    let toCityEn: [String]?
    let foreignerTipsZh: [String]?
    let foreignerTipsEn: [String]?
    let officialUrl: String?
    let checkedOn: String?

    func name(_ language: LioLanguage) -> String { language == .chinese ? nameZh : nameEn }
    func secondaryName(_ language: LioLanguage) -> String? { language == .english ? nameZh : nil }

    /// English first in the English UI; the Chinese text when no English was written (the pack says so by
    /// leaving the English field out).
    func toCity(_ language: LioLanguage) -> [String] {
        let english = toCityEn ?? []
        return language == .english && !english.isEmpty ? english : (toCityZh ?? [])
    }

    func tips(_ language: LioLanguage) -> [String] {
        let english = foreignerTipsEn ?? []
        return language == .english && !english.isEmpty ? english : (foreignerTipsZh ?? [])
    }

    func terminalNote(_ terminal: Terminal, _ language: LioLanguage) -> String? {
        language == .english ? (terminal.noteEn ?? terminal.noteZh) : terminal.noteZh
    }

    /// The official page, only when it is a plain https URL.
    var officialURL: URL? {
        guard let officialUrl, let url = URL(string: officialUrl), url.scheme == "https", url.host != nil else {
            return nil
        }
        return url
    }

    var driverRequestZH: String { hubType == .airport ? "请送我到这个机场" : "请送我到这个火车站" }
    var driverNameEN: String { code.map { "\(nameEn) (\($0))" } ?? nameEn }
}

struct LioHubPack: Decodable, Equatable, Sendable {
    enum Status: String, Decodable, Sendable { case draft, approved }

    static let version = "g2c-transport-hubs.1"
    static let cityOrder = ["beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", "chongqing"]
    static let maximumBytes = 512 * 1024

    let version: String
    let status: Status
    let places: [LioHubPlace]

    static let empty = LioHubPack(version: version, status: .draft, places: [])

    /// Decode and check once, where the file enters the app. A pack with a wrong version, a duplicate id, an
    /// airport without a 3-letter code or a place outside the six cities is rejected whole; a pack nobody
    /// reviewed must not half-load.
    static func decode(_ data: Data) -> LioHubPack? {
        guard data.count <= maximumBytes else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let pack = try? decoder.decode(LioHubPack.self, from: data), pack.version == version else { return nil }
        var seen = Set<String>()
        for place in pack.places {
            guard seen.insert(place.id).inserted, cityOrder.contains(place.city),
                  !place.nameZh.isEmpty, !place.nameEn.isEmpty,
                  place.hubType != .airport || place.code?.range(of: #"^[A-Z]{3}$"#, options: .regularExpression) != nil
            else { return nil }
        }
        return pack
    }

    static func bundled() -> LioHubPack {
        guard let url = Bundle.module.url(forResource: "LioTransportHubs.v1", withExtension: "json"),
              let data = try? Data(contentsOf: url), let pack = decode(data) else { return .empty }
        return pack
    }

    static let draftInfoKey = "G2CTransportHubsDraftEnabled"

    /// Whether this build may show the pack: approved always; a draft only in Debug or when the build turns the
    /// draft switch on. The switch must come off `release.on` before any external TestFlight group.
    func isVisible(isDebug: Bool, draftFlagOn: Bool) -> Bool {
        guard !places.isEmpty else { return false }
        return status == .approved || isDebug || draftFlagOn
    }

    static func draftFlagOn(info: [String: Any]? = Bundle.main.infoDictionary) -> Bool {
        info?[draftInfoKey] as? String == "YES"
    }

    /// Cities that have hubs, in the app's city order.
    var cities: [String] { Self.cityOrder.filter { id in places.contains { $0.city == id } } }

    func hubs(in city: String, kind: LioHubPlace.Kind) -> [LioHubPlace] {
        places.filter { $0.city == city && $0.hubType == kind }
    }

    func airport(code: String) -> LioHubPlace? {
        places.first { $0.hubType == .airport && $0.code == code }
    }
}

enum LioTransportHubsBuild {
    static var isDebug: Bool {
        #if DEBUG
        true
        #else
        false
        #endif
    }
}
