import Foundation

struct LioTaxiRoute: Equatable, Sendable {
    let pickup: LioTaxiPlace
    let destination: LioTaxiPlace
}

struct LioTaxiRequestState {
    enum Action {
        case estimate, handoff
    }

    struct Operation: Identifiable {
        let id = UUID()
        let action: Action
        let route: LioTaxiRoute
    }

    private(set) var current: Operation?

    mutating func start(_ action: Action, route: LioTaxiRoute) {
        guard current == nil else { return }
        current = Operation(action: action, route: route)
    }

    mutating func retire() { current = nil }

    func accepts(_ operation: Operation, route: LioTaxiRoute?) -> Bool {
        current?.id == operation.id && route == operation.route
    }
}

struct LioTaxiFare: Identifiable, Sendable {
    let id: String
    let nameZH: String
    let nameEN: String
    let priceDisplay: String
}

enum LioTaxiFailure: Error, Equatable {
    case locationDenied, outOfService, rateLimited, quotaExceeded, coordinateUnverified
    case signInRequired, notEnabled, timedOut, unavailable, queryTooLong
}

struct LioTaxiService: Sendable {
    let search: @MainActor @Sendable (LioTaxiSearchQuery) async throws -> [LioTaxiPlace]
    let currentPickup: @MainActor @Sendable () async throws -> LioTaxiPlace
    let estimate: @MainActor @Sendable (LioTaxiRoute) async throws -> [LioTaxiFare]
    let rideLink: @MainActor @Sendable (LioTaxiRoute) async throws -> URL
    let openRideLink: @MainActor @Sendable (URL) async throws -> Bool
    let openAppStore: @MainActor @Sendable () -> Void
}

#if DEBUG
extension LioTaxiService {
    enum PreviewScenario {
        case available, locationDenied, estimateUnavailable, missingApp, rateLimited, signedOut
    }

    static let previewDestinations: [LioTaxiPlace] = [
        .init(nameZH: "故宫博物院", nameEN: "Palace Museum", addressZH: "景山前街4号",
              coordinate: .init(latitude: 39.9163, longitude: 116.3972, referenceSystem: .gcj02)),
        .init(nameZH: "颐和园", nameEN: "Summer Palace", addressZH: "新建宫门路19号",
              coordinate: .init(latitude: 39.9998, longitude: 116.2754, referenceSystem: .gcj02)),
    ]

    /// Fixture search results for the #1421 acceptance places in Beijing, Shanghai and Chengdu.
    static let previewSearchPlaces: [LioTaxiCity: [LioTaxiPlace]] = [
        .beijing: previewDestinations + [
            .init(nameZH: "天安门", nameEN: "Tian'anmen", addressZH: "北京市东城区东长安街",
                  coordinate: .init(latitude: 39.9087, longitude: 116.3975, referenceSystem: .gcj02)),
        ],
        .shanghai: [
            .init(nameZH: "外滩", nameEN: "The Bund", addressZH: "上海市黄浦区中山东一路",
                  addressEN: "Zhongshan East 1st Rd, Huangpu, Shanghai",
                  coordinate: .init(latitude: 31.2400, longitude: 121.4905, referenceSystem: .gcj02)),
        ],
        .chengdu: [
            .init(nameZH: "宽窄巷子", nameEN: "Kuanzhai Alley", addressZH: "四川省成都市青羊区长顺街",
                  coordinate: .init(latitude: 30.6638, longitude: 104.0537, referenceSystem: .gcj02)),
        ],
    ]

    static var previewFromArguments: LioTaxiService? {
        let arguments = ProcessInfo.processInfo.arguments
        guard arguments.contains("--lio-taxi-preview") else { return nil }
        if arguments.contains("--lio-taxi-preview-location-denied") { return preview(.locationDenied) }
        if arguments.contains("--lio-taxi-preview-estimate-fails") { return preview(.estimateUnavailable) }
        if arguments.contains("--lio-taxi-preview-no-app") { return preview(.missingApp) }
        if arguments.contains("--lio-taxi-preview-rate-limited") { return preview(.rateLimited) }
        if arguments.contains("--lio-taxi-preview-signed-out") { return preview(.signedOut) }
        return preview()
    }

    @MainActor static var previewRecents: LioTaxiRecentPlaces {
        LioTaxiRecentPlaces(directory: FileManager.default.temporaryDirectory
            .appendingPathComponent("lio-taxi-preview", isDirectory: true))
    }

    static func preview(_ scenario: PreviewScenario = .available) -> LioTaxiService {
        LioTaxiService(
            search: { query in
                (previewSearchPlaces[query.city] ?? []).filter {
                    $0.nameZH.localizedStandardContains(query.text) || $0.nameEN.localizedStandardContains(query.text)
                        || $0.addressZH?.localizedStandardContains(query.text) == true
                }
            },
            currentPickup: {
                if scenario == .locationDenied { throw LioTaxiFailure.locationDenied }
                return .init(nameZH: "北京站", nameEN: "Beijing Railway Station", addressZH: "北京站街",
                             coordinate: .init(latitude: 39.9028, longitude: 116.427, referenceSystem: .wgs84))
            },
            estimate: { route in
                _ = try LioTaxiWire.encode(route)
                switch scenario {
                case .rateLimited:
                    throw LioTaxiWire.failure(status: 429, body: Data(#"{"error":"rate_limited"}"#.utf8))
                case .signedOut:
                    throw LioTaxiWire.failure(status: 401, body: Data(#"{"error":"sign_in_required"}"#.utf8))
                case .estimateUnavailable:
                    throw LioTaxiWire.failure(status: 502, body: Data(#"{"error":"supplier_unavailable"}"#.utf8))
                default:
                    let response = Data("""
                    {"version":"TAXI.1","observed_at":"2026-11-21T00:00:00Z","vehicles":[
                        {"category":"1","name":"快车","currency":"CNY","price_display":"¥35–48",
                         "price_min_minor":3500,"price_max_minor":4800},
                        {"category":"8","name":"专车","currency":"CNY","price_display":"¥52–65",
                         "price_min_minor":5200,"price_max_minor":6500},
                        {"category":"314","name":"惊喜特价","currency":"CNY","price_display":"29"},
                        {"category":"260","name":"滴滴轻享","currency":"CNY","price_display":"31-36"},
                        {"category":"16","name":"六座专车","currency":"CNY","price_display":"88"},
                        {"category":"4","name":"豪华车","currency":"CNY","price_display":"126"}
                    ]}
                    """.utf8)
                    return try LioTaxiWire.readFares(response)
                }
            },
            rideLink: { route in
                _ = try LioTaxiWire.encode(route)
                let response = Data(#"{"version":"TAXI.1","url":"https://example.invalid/ride-preview","link_type":"https"}"#.utf8)
                return try LioTaxiWire.readLink(response) { type, url in
                    type == .https && url.host == "example.invalid" && url.path == "/ride-preview"
                }
            },
            openRideLink: { _ in scenario != .missingApp },
            openAppStore: {}
        )
    }
}
#endif
