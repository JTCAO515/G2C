import Foundation
import CJMessageHTTP
#if os(iOS)
import SwiftUI
import UIKit
#endif

/// One place to fill in through ROADBOOK.1 (contracts/api/ROADBOOK.1.md): only its public names and the city.
struct LioRoadbookPlaceQuery: Equatable, Sendable {
    let id: String
    let nameZH: String
    let nameEN: String?
    let city: String
    let poiID: String?
}

/// What the relay wrote for one place: eight short fields in both languages, checked on the server, plus
/// Gaode's nearest metro stations and restaurants (which have addresses, so taxi and driver card work).
struct LioRoadbookDetail: Codable, Equatable, Sendable {
    enum Field: String, CaseIterable, Sendable {
        case summary, whyGo = "why_go", timeNeeded = "time_needed", hoursBooking = "hours_booking", tickets,
             gettingThere = "getting_there", foodTip = "food_tip", notes

        func title(_ language: LioLanguage) -> String {
            switch self {
            case .summary: language.text("About", "简介")
            case .whyGo: language.text("Why go", "为什么值得去")
            case .timeNeeded: language.text("Time needed", "建议停留")
            case .hoursBooking: language.text("Hours and booking", "开放与预约")
            case .tickets: language.text("Tickets", "门票")
            case .gettingThere: language.text("Getting there", "怎么到达")
            case .foodTip: language.text("Food nearby", "周边餐饮")
            case .notes: language.text("Good to know", "注意事项")
            }
        }
    }

    struct Metro: Codable, Equatable, Sendable {
        let nameZH: String
        let distanceMetres: Int

        func text(_ language: LioLanguage) -> String {
            language.text("\(nameZH), about \(distanceMetres) m", "\(nameZH)（约 \(distanceMetres) 米）")
        }
    }

    struct Restaurant: Codable, Equatable, Sendable, Identifiable {
        var id: String { nameZH + "|" + addressZH }
        let nameZH: String
        let addressZH: String
        let latitude: Double
        let longitude: Double
        let distanceMetres: Int

        var taxiPlace: LioTaxiPlace {
            LioTaxiPlace(nameZH: nameZH, nameEN: nameZH, addressZH: addressZH,
                         coordinate: .init(latitude: latitude, longitude: longitude, referenceSystem: .gcj02))
        }
        var place: LioRichItinerary.Place {
            .init(nameZH: nameZH, nameEN: nameZH, address: addressZH, matched: true,
                  point: .init(latitude: latitude, longitude: longitude))
        }
    }

    let poiID: String
    /// "zh" / "en" → field raw value → text. Every field is present in both languages.
    let content: [String: [String: String]]
    let metro: [Metro]
    let restaurants: [Restaurant]

    func field(_ field: Field, _ language: LioLanguage) -> String {
        content[language == .chinese ? "zh" : "en"]?[field.rawValue] ?? ""
    }
}

enum LioRoadbookPlaceStatus: Equatable, Sendable {
    case ready(LioRoadbookDetail), limited, unavailable

    var detail: LioRoadbookDetail? {
        if case .ready(let detail) = self { return detail }
        return nil
    }
}

enum LioRoadbookFailure: Error, Equatable, Sendable {
    case signInRequired, notEnabled, limited, unavailable, timedOut

    func message(_ language: LioLanguage) -> String {
        switch self {
        case .signInRequired: language.text("Sign in to fill in place details.", "登录后可以补充景点信息。")
        case .notEnabled: language.text("Place details aren’t available for this account yet.", "此账号暂未开通景点信息补充。")
        case .limited: language.text("Today’s place details are used up. Try again tomorrow.", "今天的景点信息补充次数已用完，明天再试。")
        case .unavailable: language.text("Couldn’t fill in place details right now. Try again later.", "暂时无法补充景点信息，请稍后再试。")
        case .timedOut: language.text("Filling in place details took too long. Try again.", "补充景点信息超时，请重试。")
        }
    }
}

enum LioRoadbookWire {
    static let path = "v1/tools/roadbook/places"
    static let batchSize = 8

    private struct Place: Encodable {
        let id: String
        let name_zh: String
        let name_en: String?
        let city: String
        let poi_id: String?
    }

    private struct Request: Encodable {
        let version = "ROADBOOK.1"
        let request_id: String
        let places: [Place]
    }

    static func encode(_ places: [LioRoadbookPlaceQuery], requestID: UUID) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(Request(request_id: requestID.uuidString.lowercased(), places: places.map {
            Place(id: $0.id, name_zh: $0.nameZH, name_en: $0.nameEN, city: $0.city, poi_id: $0.poiID)
        }))
    }

    /// At most eight places per request, so a request finishes well within the relay's deadline.
    static func batches(_ places: [LioRoadbookPlaceQuery]) -> [[LioRoadbookPlaceQuery]] {
        stride(from: 0, to: places.count, by: batchSize).map { Array(places[$0..<min($0 + batchSize, places.count)]) }
    }

    private struct WireMetro: Decodable { let name_zh: String; let distance_m: Int }
    private struct WireRestaurant: Decodable {
        let name_zh: String
        let address_zh: String
        let lat: Double
        let lng: Double
        let distance_m: Int
    }
    private struct WirePlace: Decodable {
        let id: String
        let status: String
        let poi_id: String?
        let content: [String: [String: String]]?
        let metro: [WireMetro]?
        let restaurants: [WireRestaurant]?
    }
    private struct Reply: Decodable {
        let version: String
        let places: [WirePlace]
    }

    static func read(_ data: Data, asked: [String]) throws -> [String: LioRoadbookPlaceStatus] {
        guard let reply = try? JSONDecoder().decode(Reply.self, from: data), reply.version == "ROADBOOK.1",
              reply.places.map(\.id) == asked else { throw LioRoadbookFailure.unavailable }
        let fields = Set(LioRoadbookDetail.Field.allCases.map(\.rawValue))
        var result: [String: LioRoadbookPlaceStatus] = [:]
        for place in reply.places {
            switch place.status {
            case "limited": result[place.id] = .limited
            case "unavailable": result[place.id] = .unavailable
            case "ready":
                guard let poi = place.poi_id, !poi.isEmpty, let content = place.content,
                      Set(content.keys) == ["zh", "en"],
                      content.values.allSatisfy({ Set($0.keys) == fields && $0.values.allSatisfy { !$0.isEmpty } }),
                      let metro = place.metro, let restaurants = place.restaurants,
                      restaurants.allSatisfy({ (-90...90).contains($0.lat) && (-180...180).contains($0.lng) })
                else { throw LioRoadbookFailure.unavailable }
                result[place.id] = .ready(LioRoadbookDetail(
                    poiID: poi, content: content,
                    metro: metro.map { .init(nameZH: $0.name_zh, distanceMetres: $0.distance_m) },
                    restaurants: restaurants.map {
                        .init(nameZH: $0.name_zh, addressZH: $0.address_zh, latitude: $0.lat, longitude: $0.lng,
                              distanceMetres: $0.distance_m)
                    }))
            default:
                throw LioRoadbookFailure.unavailable
            }
        }
        return result
    }

    private struct ErrorBody: Decodable { let error: String }

    static func failure(status: Int, body: Data) -> LioRoadbookFailure {
        let code = (try? JSONDecoder().decode(ErrorBody.self, from: body))?.error
        switch (status, code) {
        case (401, _): return .signInRequired
        case (403, _): return .notEnabled
        case (429, _): return .limited
        default: return .unavailable
        }
    }
}

/// Holds the fill-in task for one roadbook screen and cancels it when the screen's state is released.
@MainActor final class LioRoadbookFillTask {
    var task: Task<Void, Never>?
    deinit { task?.cancel() }
}

/// What the roadbook screen needs from the relay.
struct LioRoadbookEnricher: Sendable {
    let enrich: @MainActor @Sendable ([LioRoadbookPlaceQuery]) async throws -> [String: LioRoadbookPlaceStatus]
}

@MainActor public struct LioRoadbookRelayClient {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)

    private let baseURL: URL
    private let isCurrent: @MainActor () -> Bool
    private let bearer: @MainActor () -> String?
    private let newRequestID: @MainActor () -> UUID
    private let exchange: Exchange

    init(baseURL: URL, isCurrent: @escaping @MainActor () -> Bool, bearer: @escaping @MainActor () -> String?,
         newRequestID: @escaping @MainActor () -> UUID = { UUID() }, exchange: @escaping Exchange) {
        self.baseURL = baseURL
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.newRequestID = newRequestID
        self.exchange = exchange
    }

    func enrich(_ places: [LioRoadbookPlaceQuery]) async throws -> [String: LioRoadbookPlaceStatus] {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else { throw LioRoadbookFailure.signInRequired }
        let url = baseURL.appending(path: LioRoadbookWire.path)
        var request = URLRequest(url: url, timeoutInterval: 180)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = try LioRoadbookWire.encode(places, requestID: newRequestID())
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await exchange(request)
        } catch {
            try requireCurrentSession()
            if (error as? URLError)?.code == .timedOut { throw LioRoadbookFailure.timedOut }
            throw LioRoadbookFailure.unavailable
        }
        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == url else { throw LioRoadbookFailure.unavailable }
        guard http.statusCode == 200 else { throw LioRoadbookWire.failure(status: http.statusCode, body: data) }
        return try LioRoadbookWire.read(data, asked: places.map(\.id))
    }

    private func requireCurrentSession() throws {
        guard isCurrent() else { throw CancellationError() }
        try Task.checkCancellation()
    }
}

#if os(iOS)
extension LioRoadbookRelayClient {
    /// Internal testers only, when the build enables the roadbook (`G2CRoadbookEnabled`, off by default);
    /// the relay decides per account (`ROADBOOK_INTERNAL_SUBJECTS`).
    public static func internalBeta(endpoint: MessageEndpoint, isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioRoadbookRelayClient? {
        guard endpoint.allowsDemoBetaActivation,
              LioRoadbookFeature.enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: "G2CRoadbookEnabled"))
        else { return nil }
        return LioRoadbookRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = 180
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: 0, uploadFinished: nil)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }
            let (stream, response) = try await session.bytes(for: request)
            let limit = endpoint.maximumResponseBytes
            guard response.expectedContentLength <= limit else { throw LioRoadbookFailure.unavailable }
            var body = Data()
            for try await byte in stream {
                guard body.count < limit else { throw LioRoadbookFailure.unavailable }
                body.append(byte)
            }
            return (body, response)
        }
    }
}

extension LioRoadbookEnricher {
    @MainActor public static func internalBeta(relay: LioRoadbookRelayClient) -> LioRoadbookEnricherBox {
        LioRoadbookEnricherBox(LioRoadbookEnricher(enrich: { places in try await relay.enrich(places) }))
    }
}

/// Public wrapper so the app host (`LioHome`) can inject the enricher without seeing its internals.
public struct LioRoadbookEnricherBox: Sendable {
    let enricher: LioRoadbookEnricher
    init(_ enricher: LioRoadbookEnricher) { self.enricher = enricher }
}

private struct LioRoadbookEnricherKey: EnvironmentKey { static let defaultValue: LioRoadbookEnricher? = nil }

extension EnvironmentValues {
    /// Fills in roadbook places through ROADBOOK.1; nil when the build or account does not offer it.
    var lioRoadbookEnricher: LioRoadbookEnricher? {
        get { self[LioRoadbookEnricherKey.self] }
        set { self[LioRoadbookEnricherKey.self] = newValue }
    }
}

extension View {
    /// The host's way to offer roadbook place details (nil hides the button).
    public func lioRoadbookEnricher(_ box: LioRoadbookEnricherBox?) -> some View {
        environment(\.lioRoadbookEnricher, box?.enricher)
    }
}
#endif

extension LioRoadbook {
    /// The same roadbook with these places filled in (newer details replace older ones).
    func with(details new: [String: LioRoadbookDetail]) -> LioRoadbook {
        var copy = self
        copy.details.merge(new) { _, newer in newer }
        return copy
    }

    /// Sights, food and free time not yet filled in, when the city is known. Hotels and travel are skipped.
    func placesToFillIn() -> [LioRoadbookPlaceQuery] {
        guard let city else { return [] }
        let kinds: Set<LioRichItinerary.Kind> = [.sight, .meal, .freeTime, .unspecified]
        return itinerary.days.flatMap(\.stops).filter { kinds.contains($0.kind) && details[$0.id] == nil }.map {
            LioRoadbookPlaceQuery(id: $0.id, nameZH: $0.place.nameZH,
                                  nameEN: $0.place.nameEN == $0.place.nameZH ? nil : $0.place.nameEN,
                                  city: city.nameZH, poiID: nil)
        }
    }
}
