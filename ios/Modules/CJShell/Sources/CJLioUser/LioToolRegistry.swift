import Foundation
import SwiftUI
#if os(iOS)
import UIKit
#endif

/// A tool's stable name (#1724). The raw value is what routes and links carry, and the card's accessibility
/// identifier is `lio.tools.<raw value>`. Tools are declared once, in `LioToolRegistry.entries`.
struct LioTool: Hashable, Sendable, RawRepresentable, CaseIterable {
    let rawValue: String

    init(rawValue: String) { self.rawValue = rawValue }
    init(_ rawValue: String) { self.rawValue = rawValue }

    /// Every registered tool, in card order.
    static var allCases: [LioTool] { LioToolRegistry.entries.map(\.tool) }

    // The tools the rest of the app refers to by name. A new tool does not need a constant here.
    static let returnHotel = LioTool("return-hotel")
    static let arrival = LioTool("arrival")
    static let localSupport = LioTool("local-support")
    static let taxi = LioTool("taxi")
    static let hotels = LioTool("hotels")
    static let roadbook = LioTool("roadbook")
    static let transport = LioTool("transport")
    static let attractionBooking = LioTool("attraction-booking")
    static let menuOrder = LioTool("menu-order")
    static let nearby = LioTool("nearby")
    static let currency = LioTool("currency")
    static let metro = LioTool("metro-guide")
    static let payment = LioTool("payment-guide")
    static let translation = LioTool("translation")
    static let showCards = LioTool("show-cards")

    private var entry: LioToolEntry? { LioToolRegistry.entry(for: self) }

    var identifier: String { "lio.tools." + rawValue }
    var symbol: String { entry?.symbol ?? "square.grid.2x2" }
    func name(_ language: LioLanguage) -> String { entry.map { language.text($0.name.en, $0.name.zh) } ?? rawValue }
    /// One short sentence under the name; kept to two lines at the default text size.
    func summary(_ language: LioLanguage) -> String { entry.map { language.text($0.summary.en, $0.summary.zh) } ?? "" }

    func accessibilityLabel(_ language: LioLanguage) -> String {
        name(language) + language.text(", ", "，") + summary(language)
    }
}

/// One tool, declared in one place (#1724): its card, when it is shown, which route parameters it takes and the
/// page it opens. Adding a tool is adding one entry to `LioToolRegistry.entries`; the Tools tab, routes and links
/// pick it up from there. `LioHome` and the tab container do not change.
struct LioToolEntry: Sendable {
    struct Words: Sendable {
        let en: String
        let zh: String
    }

    /// When the card is shown.
    enum Gate: Sendable {
        /// Always.
        case always
        /// One of the switches tools had before the registry (`LioToolCatalog.Availability`'s named fields).
        case availability(@Sendable (LioToolCatalog.Availability) -> Bool)
        /// Only when this build's Info.plist sets the key to YES (Debug: or `--lio-tool-preview <raw value>`),
        /// and `requires` (if any) says the services it needs are there.
        case build(infoKey: String, requires: (@MainActor @Sendable (LioToolContext) -> Bool)? = nil)
    }

    typealias Page = @MainActor @Sendable (LioToolContext, LioRoute) -> AnyView

    let tool: LioTool
    let symbol: String
    let name: Words
    let summary: Words
    let gate: Gate
    /// Route parameters this tool reads; any other key in a route or link is dropped.
    let parameters: Set<String>
    let page: Page

    init<Content: View>(_ tool: LioTool, symbol: String, name: (en: String, zh: String),
                        summary: (en: String, zh: String), gate: Gate = .always, parameters: Set<String> = [],
                        @ViewBuilder page: @escaping @MainActor @Sendable (LioToolContext, LioRoute) -> Content) {
        self.tool = tool
        self.symbol = symbol
        self.name = Words(en: name.en, zh: name.zh)
        self.summary = Words(en: summary.en, zh: summary.zh)
        self.gate = gate
        self.parameters = parameters
        self.page = { context, route in AnyView(page(context, route)) }
    }
}

/// What a tool page may use (#1724): the language, the session and the services this build has. Services added
/// for new tools go in `services` (set by the host with `.lioToolServices(_:)`), so the tab container and
/// `LioHome` do not need a new parameter for each one.
@MainActor struct LioToolContext {
    var language: LioLanguage
    var services = LioToolServices()
    /// Info.plist values, read through here so tests can supply their own.
    var info: @MainActor (String) -> Any? = { Bundle.main.object(forInfoDictionaryKey: $0) }
    var arguments: [String] = ProcessInfo.processInfo.arguments
    #if os(iOS)
    var enabled = true
    var sessionIsCurrent: @MainActor () -> Bool = { true }
    var translationHistory: LioTranslationHistory?
    var translationRelay: LioRelayTranslationClient?
    var currencyRelay: LioCurrencyRelayClient?
    var taxiEntry: LioTaxiEntry?
    var nearbyService: LioNearbyService?
    var hotelFinder: LioHotelFinder?
    var roadbookDirectory: URL?
    var savedPlans: LioSavedPlansModel?
    var menuService: LioMenuService?
    #endif

    init(language: LioLanguage) { self.language = language }

    func infoFlag(_ key: String) -> Bool { info(key) as? String == "YES" }
}

/// Services for tools, keyed by type (#1724). The host adds a tool's client once; the tool's entry reads it.
public struct LioToolServices: Sendable {
    private var services: [ObjectIdentifier: any Sendable] = [:]

    public init() {}

    /// This set plus `service` (nothing changes when it is nil).
    public func with<Service: Sendable>(_ service: Service?) -> Self {
        guard let service else { return self }
        var copy = self
        copy.services[ObjectIdentifier(Service.self)] = service
        return copy
    }

    public func get<Service: Sendable>(_ type: Service.Type = Service.self) -> Service? {
        services[ObjectIdentifier(type)] as? Service
    }
}

private struct LioToolServicesKey: EnvironmentKey {
    static let defaultValue = LioToolServices()
}

extension EnvironmentValues {
    var lioToolServices: LioToolServices {
        get { self[LioToolServicesKey.self] }
        set { self[LioToolServicesKey.self] = newValue }
    }
}

public extension View {
    /// Services that registered tools read (#1724), from the signed-in host.
    func lioToolServices(_ services: LioToolServices) -> some View {
        environment(\.lioToolServices, services)
    }
}

enum LioToolRegistry {
    static func entry(for tool: LioTool, in entries: [LioToolEntry] = entries) -> LioToolEntry? {
        entries.first { $0.tool == tool }
    }

    /// Every tool, in card order. One entry per tool; this is the only place a tool is declared.
    static let entries: [LioToolEntry] = [
        LioToolEntry(.returnHotel, symbol: "house.and.flag",
                     name: ("Back to Hotel", "回酒店"), summary: ("Taxi back, show cards for locals", "打车回酒店、出示卡"),
                     gate: .availability { $0.returnHotel }) { context, _ in
            #if os(iOS)
            LioReturnHotelTools.page(language: context.language, roadbookDirectory: context.roadbookDirectory,
                                     taxiEntry: context.taxiEntry, isCurrent: context.sessionIsCurrent)
            #endif
        },
        LioToolEntry(.arrival, symbol: "airplane.arrival",
                     name: ("Arrival Mode", "落地模式"),
                     summary: ("Your first hours in China, step by step", "落地首日要做的事"),
                     gate: .availability { $0.arrival }) { context, _ in
            #if os(iOS)
            let trip = context.arrivalTrip
            LioArrivalView(language: context.language, hotels: trip?.hotels ?? [], arrival: trip?.arrival)
            #endif
        },
        LioToolEntry(.localSupport, symbol: "lifepreserver",
                     name: ("Local Support", "本地协助"),
                     summary: ("Emergency numbers, embassies, help cards", "急救、使领馆和求助卡")) { context, _ in
            #if os(iOS)
            LioLocalSupportView(language: context.language, directory: try? LocalSupportDirectory.bundled())
            #endif
        },
        LioToolEntry(.taxi, symbol: "car.fill",
                     name: ("Taxi", "打车"), summary: ("Find a place and open DiDi", "搜地点，用滴滴打车"),
                     gate: .availability { $0.taxi }) { context, _ in
            #if os(iOS)
            if let taxiEntry = context.taxiEntry {
                LioTaxiView(language: context.language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                            recentStore: taxiEntry.recentStore, destination: context.travelProfile().profile.taxiDestination)
            }
            #endif
        },
        LioToolEntry(.hotels, symbol: "bed.double",
                     name: ("Hotels", "酒店"), summary: ("Find hotels by city and dates", "按城市和日期找酒店"),
                     gate: .availability { $0.hotels }, parameters: ["city"]) { context, route in
            #if os(iOS)
            if let finder = context.hotelSearch {
                let (profile, today) = context.travelProfile()
                let search = profile.hotelSearch(routeCity: route["city"], today: today)
                LioHotelOffersView(language: context.language, finder: finder, city: search.city,
                                   checkIn: search.checkIn, nights: search.nights)
                    // "Set as my hotel" saves to Back to Hotel only while that tool is shown.
                    .environment(\.lioReturnHotelStore, LioReturnHotelTools.storeForHotelSearch(
                        shown: LioReturnHotelTools.shownInTools, roadbookDirectory: context.roadbookDirectory,
                        isCurrent: context.sessionIsCurrent))
            } else {
                context.hotelLinks
            }
            #endif
        },
        LioToolEntry(.roadbook, symbol: "book.closed",
                     name: ("Roadbook", "路书"), summary: ("Your trip day by day, offline", "按天离线看的旅行手册"),
                     gate: .availability { $0.roadbook }) { context, _ in
            #if os(iOS)
            LioRoadbookLibraryView(language: context.language, store: context.roadbookStore,
                                   candidates: context.roadbookCandidates, savedPlans: context.savedPlans)
            #endif
        },
        LioToolEntry(.transport, symbol: "train.side.front.car",
                     name: ("Intercity Travel", "城际交通"),
                     summary: ("Compare trains, flights and buses", "比较火车、飞机和大巴"),
                     gate: .availability { $0.transport }, parameters: ["from", "to"]) { context, route in
            #if os(iOS)
            if let service = LioTransportService.fromBuild() {
                let (profile, today) = context.travelProfile()
                let trip = profile.transport(routeFrom: route["from"], routeTo: route["to"], today: today)
                LioTransportView(language: context.language, service: service, from: trip.from, to: trip.to,
                                 date: trip.date)
            }
            #endif
        },
        LioToolEntry(.attractionBooking, symbol: "ticket",
                     name: ("Sight Bookings", "景点预约"),
                     summary: ("When tickets open, with reminders", "预约规则与放票提醒"),
                     gate: .availability { $0.attractionBooking }) { context, _ in
            #if os(iOS)
            let (profile, today) = context.travelProfile()
            let booking = profile.attractionBooking(today: today)
            LioAttractionBookingView(language: context.language, tripCityZH: booking.cityZH, visit: booking.visit)
            #endif
        },
        LioToolEntry(.menuOrder, symbol: "fork.knife",
                     name: ("Menu Helper", "点餐"), summary: ("Snap a menu, order in Chinese", "拍菜单，用中文点菜"),
                     gate: .availability { $0.menuOrder }) { context, _ in
            #if os(iOS)
            if let menuService = context.menuService {
                // Server memory is not read by Tools; the show-card allergies saved on this device are ticked (#1739).
                LioMenuOrderView(language: context.language, service: menuService, memoryNotes: nil,
                                 needs: context.travelProfile().profile.menuNeeds)
            }
            #endif
        },
        LioToolEntry(.nearby, symbol: "mappin.and.ellipse",
                     name: ("Nearby", "附近"), summary: ("Food, sights and shops around you", "身边的美食和景点"),
                     gate: .availability { $0.nearby }) { context, _ in
            #if os(iOS)
            if let nearbyService = context.nearbyService {
                LioNearbyView(language: context.language, service: nearbyService)
            }
            #endif
        },
        LioToolEntry(.currency, symbol: "yensign.circle",
                     name: ("Currency Converter", "汇率换算"),
                     summary: ("Convert yuan at ECB reference rates", "人民币外币参考换算"),
                     gate: .availability { $0.currency }) { context, _ in
            #if os(iOS)
            if let currencyRelay = context.currencyRelay {
                LioCurrencyView(language: context.language, load: currencyRelay.load)
            }
            #endif
        },
        LioToolEntry(.metro, symbol: "tram.fill",
                     name: ("Metro Guide", "地铁指南"), summary: ("Interactive line maps by city", "各城市可交互线路图")) { context, _ in
            #if os(iOS)
            LioMetroGuideView(language: context.language)
            #endif
        },
        LioToolEntry(.payment, symbol: "wallet.pass",
                     name: ("Payment Setup Guide", "支付开通指南"),
                     summary: ("Set up Alipay and Weixin Pay", "开通支付宝和微信支付")) { context, _ in
            #if os(iOS)
            LioPaymentGuideView(language: context.language)
            #endif
        },
        LioToolEntry(.translation, symbol: "character.bubble",
                     name: ("Translation", "翻译"), summary: ("Type, speak or snap a photo", "打字、说话或拍照翻译")) { context, _ in
            #if os(iOS)
            LioTextTranslationView(language: context.language, history: context.translationHistory,
                                   enabled: context.enabled, isCurrent: {
                UIApplication.shared.applicationState != .background && context.sessionIsCurrent()
            }, relay: context.translationRelay)
            #endif
        },
        // #1742: one tool for everything shown to someone. It took over the Phrase Cards card and slot; phrases and
        // help cards are always there, the cards with the traveller's details follow `G2CShowCardEnabled`.
        LioToolEntry(.showCards, symbol: "person.text.rectangle",
                     name: ("Show Cards", "出示卡"),
                     summary: ("Phrases and help cards in large Chinese", "常用语和求助，给对方看")) { context, _ in
            #if os(iOS)
            LioShowCardTool.page(language: context.language, roadbookDirectory: context.roadbookDirectory,
                                 isCurrent: context.sessionIsCurrent)
            #endif
        },
    ]
}

extension LioToolContext {
    /// Which gated tools this build shows (#1724): the switches tools had before the registry, then each
    /// `.build` entry's own Info.plist key and services.
    func availability(entries: [LioToolEntry] = LioToolRegistry.entries) -> LioToolCatalog.Availability {
        var available = LioToolCatalog.Availability()
        #if os(iOS)
        available.taxi = taxiEntry != nil
        available.currency = currencyRelay != nil
        available.nearby = nearbyService != nil
        available.hotels = hotelSearch != nil
        available.roadbook = LioRoadbookFeature.enabled(infoValue: info("G2CRoadbookEnabled"))
        available.transport = LioTransportService.fromBuild() != nil
        available.menuOrder = menuService != nil
        available.returnHotel = LioReturnHotelTools.shownInTools
        available.arrival = LioArrivalFeature.enabled(infoValue: info(LioArrivalFeature.infoKey))
        available.attractionBooking = LioAttractionBookingFeature.enabled(infoValue: info(LioAttractionBookingFeature.infoKey))
        #if DEBUG
        available.hotels = available.hotels || arguments.contains("--lio-hotels-preview")
        if LioRoadbookPreview.requested { available.roadbook = true }
        if LioArrivalPreview.requested { available.arrival = true }
        if LioAttractionBookingFeature.previewRequested { available.attractionBooking = true }
        #endif
        #endif
        for entry in entries {
            guard case .build(let key, let requires) = entry.gate else { continue }
            var on = infoFlag(key)
            #if DEBUG
            if let index = arguments.firstIndex(of: "--lio-tool-preview"), index + 1 < arguments.count,
               arguments[index + 1] == entry.tool.rawValue { on = true }
            #endif
            if on, requires?(self) ?? true { available.enabled.insert(entry.tool) }
        }
        return available
    }
}

#if os(iOS)
extension LioToolContext {
    /// Hotel search (#1510) only when the build enables it (`G2CHotelEnabled`, off by default), or with the
    /// Debug preview fixture (`--lio-hotel-search-preview`).
    var hotelSearch: LioHotelFinder? {
        #if DEBUG
        if arguments.contains("--lio-hotel-search-preview") { return .preview }
        #endif
        return hotelFinder
    }

    /// Offline copies live in the signed-in account's folder (#1553) and stop when the session changes.
    var roadbookStore: LioRoadbookStore? {
        #if DEBUG
        if LioRoadbookPreview.requested { return try? LioRoadbookStore.preview() }
        #endif
        guard let roadbookDirectory else { return nil }
        return LioRoadbookStore(directory: roadbookDirectory, isCurrent: sessionIsCurrent)
    }

    /// Roadbooks that can be made now: the account's saved plans (#1547). Debug previews show only
    /// preview roadbooks, because their copies are kept outside the account folder.
    var roadbookCandidates: [LioRoadbook] {
        #if DEBUG
        if LioRoadbookPreview.requested { return LioRoadbookPreview.library(language) }
        #endif
        return (savedPlans?.plans ?? []).map { LioRoadbook(savedPlan: $0) }
    }

    /// Arrival mode (#1595) uses the next dated saved plan, else the first one. Summaries usually carry no
    /// hotels or dates yet: the taxi step then asks for the hotel and the arrival day defaults to today.
    var arrivalTrip: (hotels: [LioRichItinerary.Hotel], arrival: LioArrivalDay?)? {
        #if DEBUG
        if LioArrivalPreview.requested { return (LioArrivalPreview.hotels, nil) }
        #endif
        guard let plan = LioToolCatalog.arrivalPlan(savedPlans?.plans ?? [], today: LioArrivalDay(date: .now)) else {
            return nil
        }
        return (plan.itinerary.hotels, plan.startDate.flatMap(LioArrivalDay.init))
    }

    @ViewBuilder var hotelLinks: some View {
        #if DEBUG
        let partial = arguments.contains("--lio-hotels-preview-partial")
        LioHotelsView(language: language, service: .preview(unapplied: partial ? [.guests] : []),
                      suggestedArea: LioHotelService.previewArea)
        #else
        EmptyView()
        #endif
    }
}
#endif
