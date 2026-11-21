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
    enum Price: Sendable {
        case range(minimum: Decimal, maximum: Decimal, currency: String)
        case description(String)
    }

    let id: String
    let nameZH: String
    let nameEN: String
    let price: Price
}

enum LioTaxiFailure: Error, Equatable {
    case locationDenied, outOfService, rateLimited, quotaExceeded, coordinateUnverified
    case signInRequired, notEnabled, unavailable
}

/// App-facing operations used by the preview and by a future Hong Kong adapter.
/// These values do not define the server's request or response formats.
struct LioTaxiService {
    let search: @MainActor (String) async throws -> [LioTaxiPlace]
    let currentPickup: @MainActor () async throws -> LioTaxiPlace
    let estimate: @MainActor (LioTaxiRoute) async throws -> [LioTaxiFare]
    let rideLink: @MainActor (LioTaxiRoute) async throws -> URL
    let openRideLink: @MainActor (URL) async -> Bool
    let openAppStore: @MainActor () -> Void
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

    static func preview(_ scenario: PreviewScenario = .available) -> LioTaxiService {
        LioTaxiService(
            search: { query in
                previewDestinations.filter {
                    $0.nameZH.localizedStandardContains(query) || $0.nameEN.localizedStandardContains(query)
                        || $0.addressZH?.localizedStandardContains(query) == true
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
                        {"category":"standard","name":"普通车型","currency":"CNY","price_display":"¥35–48",
                         "price_min_minor":3500,"price_max_minor":4800},
                        {"category":"comfort","name":"舒适车型","currency":"CNY","price_display":"¥52–65",
                         "price_min_minor":5200,"price_max_minor":6500}
                    ]}
                    """.utf8)
                    let fares = try LioTaxiWire.readFares(response)
                    let names = ["standard": "Standard", "comfort": "Comfort"]
                    return fares.map { fare in
                        LioTaxiFare(id: fare.id, nameZH: fare.nameZH, nameEN: names[fare.id] ?? fare.nameEN, price: fare.price)
                    }
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
