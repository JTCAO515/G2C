import CJStrictJSON
import Foundation

/// What kind of trip the traveller said this is, in the trip settings (#1765). Kept only on this phone, in the trip
/// home's own file; nothing is read from the server's scene packs or switches. A profile written before this field
/// existed has none and is a leisure trip.
enum LioTripPurpose: String, Codable, CaseIterable, Sendable {
    case leisure, business
}

/// `G2CTripBusinessEnabled` in the build's Info.plist (#1765); off unless it says YES. With it off the trip settings
/// do not offer "Business" and the checklist is exactly as before. JT decides which build turns it on.
enum LioTripBusinessFeature {
    static let infoKey = "G2CTripBusinessEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool { enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) }
}

/// The Guangzhou business entries (#1759), bundled as `LioBusinessGuangzhou.v1.json`: a byte-identical copy of
/// `knowledge/business/guangzhou.v1.json`, which the fact data line keeps and validates. Never edit the copy by
/// hand; copy the source over it (`LioTripBusinessTests` fails while they differ).
struct LioBusinessCatalogue: Decodable, Equatable, Sendable {
    static let version = "g2c-business-knowledge.1"

    struct Entry: Decodable, Equatable, Sendable {
        let id: String
        let topic: String
        let title: LioArrivalText
        let textZH: String
        let textEN: String
        let sourceURLs: [URL]
        let checkedOn: LioTripDay
        let expiresOn: LioTripDay

        private enum CodingKeys: String, CodingKey {
            // Keys arrive converted from snake case: `source_urls` is `sourceUrls`.
            case id, topic, title, textZH = "textZh", textEN = "textEn", sourceURLs = "sourceUrls", checkedOn, expiresOn
        }

        var text: LioTripText { LioTripText(en: textEN, zh: textZH) }
        var titleText: LioTripText { LioTripText(en: title.en, zh: title.zh) }
    }

    let version: String
    let city: String
    let entries: [Entry]

    func entry(topic: String) -> Entry? { entries.first { $0.topic == topic } }

    static func bundled() throws -> Self {
        guard let url = Bundle.module.url(forResource: "LioBusinessGuangzhou.v1", withExtension: "json") else {
            throw CocoaError(.fileNoSuchFile)
        }
        return try decode(Data(contentsOf: url))
    }

    /// Rejected as a whole unless every entry has its texts, an https official page and a check day before its review day.
    static func decode(_ data: Data) throws -> Self {
        var reader = StrictJSONReader<LioBusinessJSONPolicy>(bytes: Array(data))
        try reader.check()
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let catalogue = try decoder.decode(Self.self, from: data)
        let ids = catalogue.entries.map(\.id)
        guard catalogue.version == version, !catalogue.entries.isEmpty, Set(ids).count == ids.count,
              catalogue.entries.allSatisfy({ entry in
                  !entry.title.zh.isEmpty && !entry.title.en.isEmpty && !entry.textZH.isEmpty && !entry.textEN.isEmpty
                      && !entry.sourceURLs.isEmpty && entry.sourceURLs.allSatisfy(isOfficialPage)
                      && entry.checkedOn < entry.expiresOn
              }) else { throw CocoaError(.fileReadCorruptFile) }
        return catalogue
    }

    /// An https page with no credentials or custom port, as `knowledge/business/validate.py` requires of the source.
    static func isOfficialPage(_ url: URL) -> Bool {
        url.scheme == "https" && url.user == nil && url.password == nil && url.port == nil && url.host?.isEmpty == false
            && !url.path.isEmpty && url.path != "/" && url.fragment == nil
    }
}

/// The business scene pack's flows (`backend/cj_api/scene_packs/business.json`, S line), bundled as
/// `LioBusinessFlows.v1.json`. The file holds the pack's `scene_pack` name and its `flows` array exactly as the pack
/// has them; `LioTripBusinessTests` fails while they differ. Never edit it by hand: copy the pack's `flows` over it.
struct LioBusinessFlows: Decodable, Equatable, Sendable {
    struct Flow: Decodable, Equatable, Sendable {
        let id: String
        let title: LioArrivalText
        let steps: [LioArrivalText]
    }

    let scenePack: String
    let flows: [Flow]

    static let tradeFairPreparation = "trade-fair-preparation"

    func flow(_ id: String) -> Flow? { flows.first { $0.id == id } }

    static func bundled() throws -> Self {
        guard let url = Bundle.module.url(forResource: "LioBusinessFlows.v1", withExtension: "json") else {
            throw CocoaError(.fileNoSuchFile)
        }
        return try decode(Data(contentsOf: url))
    }

    static func decode(_ data: Data) throws -> Self {
        var reader = StrictJSONReader<LioBusinessJSONPolicy>(bytes: Array(data))
        try reader.check()
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let flows = try decoder.decode(Self.self, from: data)
        guard flows.scenePack == "business",
              flows.flows.allSatisfy({ flow in
                  !flow.steps.isEmpty && flow.steps.allSatisfy { !$0.zh.isEmpty && !$0.en.isEmpty }
              }) else { throw CocoaError(.fileReadCorruptFile) }
        return flows
    }
}

/// What the trip home's business items are made of: the sourced entries and the scene pack's preparation steps.
/// Nil in the checklist input when `G2CTripBusinessEnabled` is off or the bundled files cannot be read.
struct LioTripBusinessGuide: Equatable, Sendable {
    let catalogue: LioBusinessCatalogue
    let flows: LioBusinessFlows

    static func bundled() -> Self? {
        guard let catalogue = try? LioBusinessCatalogue.bundled(), let flows = try? LioBusinessFlows.bundled() else { return nil }
        return Self(catalogue: catalogue, flows: flows)
    }

    /// The trade fair preparation step the item reuses, by its position in the scene pack (1-based).
    func step(_ number: Int) -> LioTripText? {
        guard let steps = flows.flow(LioBusinessFlows.tradeFairPreparation)?.steps, steps.indices.contains(number - 1) else {
            return nil
        }
        return LioTripText(en: steps[number - 1].en, zh: steps[number - 1].zh)
    }
}

/// One business item on the trip home (#1765). Facts come only from the bundled entries, each shown with its official
/// pages and the day it was checked; from its review day on (`expires_on`, Beijing calendar) the item says only
/// "go by the official notice" with the same links, as Arrival Mode does for rules overdue for review.
///
/// The scene pack's five preparation steps map to: 1 the organizer's pre-registration page (`registration`),
/// 2 the existing hotel task, 3 `phrases` (Translation), 4 the existing payment task, 5 `venue` (Taxi).
/// Visas are only the official channels: the app never works out a visa type, visa-free entry or transit.
struct LioTripBusinessTask: Equatable, Sendable {
    enum Item: String, CaseIterable, Sendable {
        case registration, visa, venue, phrases, meeting, cards

        var key: String { "business." + rawValue }
    }

    /// What "Go" does. Tools open through the registry's routes; the organizer's pages open in the browser.
    enum Action: Equatable, Sendable {
        case officialPage(URL)
        case route(LioRoute)
    }

    /// The sourced entry an item rests on.
    struct Source: Equatable, Sendable {
        let urls: [URL]
        let checkedOn: LioTripDay
        /// Today (Beijing) is on or after the entry's review day: only "check the official notice" is said.
        let officialOnly: Bool
    }

    let item: Item
    /// Sourced wording (an entry's title or a scene pack step); nil means the item's fixed label.
    let title: LioTripText?
    /// The entry's text; nil for items that state no facts, and for entries past their review day.
    let text: LioTripText?
    let source: Source?
    /// Nil when there is nothing to open: the business cards item, the visa item (its links are the way), or a tool
    /// this build does not show.
    let action: Action?

    /// The show-cards route that lands on its Business section (#1766).
    static func meetingRoute(entries: [LioToolEntry] = LioToolRegistry.entries) -> LioRoute? {
        LioRoute(tool: .showCards, parameters: [LioShowCardSection.routeKey: LioShowCardSection.business.rawValue],
                 entries: entries)
    }

    /// The business items for this trip, or none unless the traveller chose a business trip and the guide is bundled.
    /// `routable` says which tools the router can open in this build. Entries are Guangzhou's: they are left out when
    /// the trip's first city is another one.
    static func tasks(guide: LioTripBusinessGuide?, profile: LioTripProfile?, now: Date,
                      routable: Set<LioTool>) -> [(stage: LioTripStage, task: Self)] {
        guard let guide, profile?.purpose == .business else { return [] }
        // The entries' days are Beijing days, like Arrival Mode's rules; the clock is the checklist's own.
        let today = LioTripDay(date: now, timeZone: LioTripChecklist.beijing)
        let cityMatches = profile?.cityID.map { $0 == guide.catalogue.city } ?? true
        func entry(_ topic: String) -> LioBusinessCatalogue.Entry? { cityMatches ? guide.catalogue.entry(topic: topic) : nil }
        func source(_ entry: LioBusinessCatalogue.Entry) -> Source {
            Source(urls: entry.sourceURLs, checkedOn: entry.checkedOn, officialOnly: today >= entry.expiresOn)
        }
        func sourced(_ item: Item, _ entry: LioBusinessCatalogue.Entry, title: LioTripText?, action: Action?) -> Self {
            let source = source(entry)
            return Self(item: item, title: title, text: source.officialOnly ? nil : entry.text, source: source, action: action)
        }
        func route(_ tool: LioTool, _ parameters: [String: String] = [:]) -> Action? {
            guard routable.contains(tool), let route = LioRoute(tool: tool, parameters: parameters) else { return nil }
            return .route(route)
        }

        var result: [(stage: LioTripStage, task: Self)] = []
        if let registration = entry("trade_fair_registration") {
            let page = registration.sourceURLs.first.map(Action.officialPage)
            result.append((.beforeTrip, sourced(.registration, registration, title: registration.titleText, action: page)))
        }
        if let visa = entry("visa_channel") {
            result.append((.beforeTrip, sourced(.visa, visa, title: nil, action: nil)))
        }
        if let phrases = guide.step(3) {
            result.append((.beforeTrip, Self(item: .phrases, title: phrases, text: nil, source: nil,
                                                       action: route(.translation))))
        }
        result.append((.beforeTrip, Self(item: .cards, title: nil, text: nil, source: nil, action: nil)))
        if let venue = entry("venue_transport") {
            result.append((.inChina, sourced(.venue, venue, title: guide.step(5), action: route(.taxi))))
        }
        let meeting = routable.contains(.showCards) ? meetingRoute().map(Action.route) : nil
        result.append((.inChina, Self(item: .meeting, title: nil, text: nil, source: nil, action: meeting)))
        return result
    }
}

/// The section of the Show Cards page a route lands on (#1765): `go2china://tool/show-cards?section=business`.
enum LioShowCardSection: String, Sendable {
    case business

    static let routeKey = "section"

    init?(route: LioRoute) {
        guard route.tool == .showCards, let value = route[Self.routeKey] else { return nil }
        self.init(rawValue: value)
    }
}

private enum LioBusinessJSONPolicy: StrictJSONPolicy {
    static var failure: CocoaError { CocoaError(.fileReadCorruptFile) }
    static var requiresObjectRoot: Bool { true }
    static var maximumDepth: Int { 8 }
}
