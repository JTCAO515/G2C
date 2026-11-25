import Foundation

/// Third-party ticket links for a sight (#1593; M4 items 11 and 17, JT 2026-11-25). Until the affiliate
/// credentials are handed over these are plain public search pages with no affiliate ID, and only the
/// sight's public English name goes into the link, when the user taps it. Booking and payment happen on
/// the partner's site.
enum LioAttractionPartner: Sendable, Equatable {
    case tripCom

    struct Link: Sendable, Equatable {
        let partner: LioAttractionPartner
        let url: URL
    }

    /// Venues that stay on their official channels (JT 2026-11-25), whatever the rule table says.
    static let officialOnly = ["beijing.palace-museum", "beijing.national-museum", "beijing.mao-mausoleum",
                               "beijing.tiananmen-rostrum", "beijing.tiananmen-square", "xian.shaanxi-history-museum"]

    /// True once links carry an affiliate ID (server-side hand-off); the #225 disclosure follows it.
    static let affiliateLinks = false

    /// Search words that find the ticket listing better than the formal English name.
    private static let searchTerms = [
        "xian.qin-mausoleum-museum": "Terracotta Warriors",
        "chengdu.panda-base": "Chengdu Panda Base",
        "shanghai.museum-peoples-square": "Shanghai Museum",
    ]

    func name(_ language: LioLanguage) -> String {
        switch self {
        case .tripCom: "Trip.com"
        }
    }

    static func links(for rule: LioAttractionBookingRule) -> [Link] {
        guard rule.partnerLinks, !officialOnly.contains(rule.id) else { return [] }
        let term = searchTerms[rule.id] ?? rule.nameEN
        var trip = URLComponents(string: "https://www.trip.com/things-to-do/list")!
        trip.queryItems = [URLQueryItem(name: "keyword", value: term)]
        return trip.url.map { [Link(partner: .tripCom, url: $0)] } ?? []
    }

    static func disclosure(_ language: LioLanguage, affiliate: Bool = affiliateLinks) -> String? {
        affiliate ? LioHotelResults.disclosure(language) : nil
    }
}
