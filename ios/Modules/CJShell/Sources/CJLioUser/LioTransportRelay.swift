import Foundation
#if os(iOS)
import CJMessageHTTP
#endif

/// App half of TRANSPORT.1 (#1521, contracts/api/TRANSPORT.1.md): one POST per search with the caller's own
/// bearer; trains and flights come back with a status each, and seats are never claimed (12306 decides).
enum LioTransportRelayFailure: Error, Equatable {
    case signInRequired
    case unavailableForAccount
    case quotaExceeded
    case offline
    case timedOut
    case unavailable
    /// A flight-number lookup the supplier could not answer (FLIGHTS.1 502/503/504).
    case lookupUnavailable

    func message(_ language: LioLanguage) -> String {
        switch self {
        case .signInRequired:
            language.text("Sign in again to compare trains and flights.", "请重新登录后再比较火车和飞机。")
        case .unavailableForAccount:
            language.text("Intercity search isn't available for this account yet.", "这个账号暂时不能使用城际交通搜索。")
        case .quotaExceeded:
            language.text("You've reached today's search limit. Try again tomorrow, or check on 12306 and Trip.com.",
                          "今天的搜索次数已用完，明天再试，或直接在 12306、Trip.com 查看。")
        case .offline:
            language.text("You're offline. Connect to the internet and try again.", "当前没有网络，联网后再试。")
        case .timedOut:
            language.text("This took too long. Try again.", "等待时间太长，请重试。")
        case .unavailable:
            language.text("Couldn't compare right now. Try again, or check on 12306 and Trip.com.",
                          "暂时无法比较，请重试，或直接在 12306、Trip.com 查看。")
        case .lookupUnavailable:
            language.text("Couldn't look up this flight right now. Try again later, or check the airline's app or site.",
                          "暂时查不到这个航班，请稍后再试，或在航空公司 App 或官网查看。")
        }
    }
}

@MainActor public struct LioTransportRelayClient: Sendable {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)

    static let version = "TRANSPORT.1"
    static let maximumResponseBytes = 131_072
    private static let maximumItems = 20
    private let url: URL
    private let flightsURL: URL
    private let isCurrent: @MainActor () -> Bool
    private let bearer: @MainActor () -> String?
    private let exchange: Exchange

    init(baseURL: URL, isCurrent: @escaping @MainActor () -> Bool,
         bearer: @escaping @MainActor () -> String?, exchange: @escaping Exchange) {
        url = baseURL.appending(path: "v1/tools/transport/search")
        flightsURL = baseURL.appending(path: "v1/tools/flights")
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.exchange = exchange
    }

    func search(_ query: LioTransportQuery) async throws -> LioTransportResult {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else {
            throw LioTransportRelayFailure.signInRequired
        }
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "version": Self.version, "origin": query.from.id, "destination": query.to.id, "date": query.day,
            "modes": ["rail", "flight"],
        ], options: [.sortedKeys])

        let body: Data
        let response: URLResponse
        do {
            (body, response) = try await exchange(request)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try requireCurrentSession()
            switch (error as? URLError)?.code {
            case .notConnectedToInternet, .networkConnectionLost: throw LioTransportRelayFailure.offline
            case .timedOut: throw LioTransportRelayFailure.timedOut
            default: throw LioTransportRelayFailure.unavailable
            }
        }
        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == url, body.count <= Self.maximumResponseBytes else {
            throw LioTransportRelayFailure.unavailable
        }
        switch http.statusCode {
        case 200:
            guard let result = Self.decode(body, for: query) else { throw LioTransportRelayFailure.unavailable }
            return result
        case 401: throw LioTransportRelayFailure.signInRequired
        case 403: throw LioTransportRelayFailure.unavailableForAccount
        case 429: throw LioTransportRelayFailure.quotaExceeded
        default: throw LioTransportRelayFailure.unavailable
        }
    }

    /// FLIGHTS.1 (#2007): one flight by number and day. One POST with the caller's own bearer; the reply is
    /// checked here before any of it reaches a view.
    func flightStatus(_ query: LioFlightQuery) async throws -> LioFlightLookupResult {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else {
            throw LioTransportRelayFailure.signInRequired
        }
        var request = URLRequest(url: flightsURL, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "version": Self.flightsVersion, "date": query.day, "flight_number": query.number,
        ], options: [.sortedKeys])

        let body: Data
        let response: URLResponse
        do {
            (body, response) = try await exchange(request)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            try requireCurrentSession()
            switch (error as? URLError)?.code {
            case .notConnectedToInternet, .networkConnectionLost: throw LioTransportRelayFailure.offline
            case .timedOut: throw LioTransportRelayFailure.timedOut
            default: throw LioTransportRelayFailure.lookupUnavailable
            }
        }
        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == flightsURL, body.count <= Self.maximumResponseBytes else {
            throw LioTransportRelayFailure.lookupUnavailable
        }
        switch http.statusCode {
        case 200:
            guard let result = Self.decodeFlights(body, for: query) else { throw LioTransportRelayFailure.lookupUnavailable }
            return result
        case 401: throw LioTransportRelayFailure.signInRequired
        case 403: throw LioTransportRelayFailure.unavailableForAccount
        case 429: throw LioTransportRelayFailure.quotaExceeded
        default: throw LioTransportRelayFailure.lookupUnavailable
        }
    }

    static let flightsVersion = "FLIGHTS.1"
    private static let maximumFlights = 100

    private struct FlightsReply: Decodable {
        let version: String
        let source: String
        let date: String
        let more: Bool
        let items: [LioFlightStatus]
    }

    static func decodeFlights(_ body: Data, for query: LioFlightQuery) -> LioFlightLookupResult? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let reply = try? decoder.decode(FlightsReply.self, from: body), reply.version == flightsVersion,
              reply.date == query.day, reply.items.count <= maximumFlights else { return nil }
        let valid = reply.items.allSatisfy { item in
            item.flightNumber.range(of: LioFlightQuery.pattern, options: .regularExpression) != nil
                && [item.departure, item.arrival].allSatisfy { code in
                    code.map { $0.range(of: #"^[A-Z]{3}$"#, options: .regularExpression) != nil } ?? true
                }
        }
        guard valid else { return nil }
        return LioFlightLookupResult(query: query, flights: reply.items, more: reply.more)
    }

    private func requireCurrentSession() throws {
        try Task.checkCancellation()
        guard isCurrent() else { throw CancellationError() }
    }

    // MARK: Wire (checked once here, where the reply enters the app)

    private struct Reply: Decodable {
        struct City: Decodable { let id: String }
        struct Mode<Item: Decodable>: Decodable { let status: String; let items: [Item] }
        struct Station: Decodable { let nameZh: String; let nameEn: String? }
        struct Seat: Decodable { let classZh: String; let classEn: String; let priceCnyMinor: Int }
        struct Train: Decodable {
            let number: String
            let departStation: Station
            let arriveStation: Station
            let departTime: String
            let arriveTime: String
            let durationMin: Int
            let seats: [Seat]
            let availability: String?
        }
        struct Carrier: Decodable { let nameZh: String?; let nameEn: String? }
        struct Airport: Decodable { let iata: String; let nameZh: String?; let nameEn: String? }
        struct Flight: Decodable {
            let number: String
            let carrier: Carrier?
            let departAirport: Airport
            let arriveAirport: Airport
            let departTime: String
            let arriveTime: String
            let durationMin: Int
        }

        let version: String
        let date: String
        let origin: City
        let destination: City
        let rail: Mode<Train>?
        let flight: Mode<Flight>?
    }

    static func decode(_ body: Data, for query: LioTransportQuery) -> LioTransportResult? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let reply = try? decoder.decode(Reply.self, from: body), reply.version == version,
              reply.date == query.day, reply.origin.id == query.from.id, reply.destination.id == query.to.id,
              let rail = reply.rail, let flight = reply.flight,
              let trains = mode(rail, { train($0) }), let flights = mode(flight, { self.flight($0) }) else {
            return nil
        }
        return LioTransportResult(query: query, rail: trains, flight: flights, bus: .guideOnly, isSample: false)
    }

    private static func mode<Item>(_ mode: Reply.Mode<Item>,
                                   _ project: (Item) -> LioTransportOption?) -> LioTransportModeResult? {
        switch mode.status {
        case "ok", "empty":
            guard mode.items.count <= maximumItems else { return nil }
            let options = mode.items.compactMap(project)
            return options.count == mode.items.count ? .options(options) : nil
        case "unavailable", "quota_exceeded":
            return mode.items.isEmpty ? .unavailable : nil
        case "not_enabled":
            return mode.items.isEmpty ? .guideOnly : nil
        default:
            return nil
        }
    }

    private static func clock(_ value: String) -> Bool {
        value.range(of: #"^([01][0-9]|2[0-3]):[0-5][0-9]$"#, options: .regularExpression) != nil
    }

    private static func knownStationEN(_ nameZH: String) -> String? {
        LioTransportCity.all.lazy.flatMap(\.stations).first { $0.nameZH == nameZH }?.nameEN
    }

    private static func knownAirport(_ code: String) -> LioTransportHub? {
        LioTransportCity.all.lazy.flatMap(\.airports).first { $0.code == code }
    }

    private static func train(_ item: Reply.Train) -> LioTransportOption? {
        guard item.availability == nil, !item.number.isEmpty, item.number.count <= 8,
              clock(item.departTime), clock(item.arriveTime), (1...7 * 1440).contains(item.durationMin) else {
            return nil
        }
        func station(_ value: Reply.Station) -> LioTransportHub? {
            guard !value.nameZh.isEmpty, value.nameZh.count <= 41 else { return nil }
            return LioTransportHub(kind: .station, nameZH: value.nameZh,
                                   nameEN: value.nameEn ?? knownStationEN(value.nameZh) ?? value.nameZh)
        }
        guard let departure = station(item.departStation), let arrival = station(item.arriveStation) else { return nil }
        let fares = item.seats.map { LioTransportFare(classZH: $0.classZh, classEN: $0.classEn, priceMinor: $0.priceCnyMinor) }
        guard fares.count <= 9, fares.allSatisfy({ $0.priceMinor > 0 && !$0.classZH.isEmpty && !$0.classEN.isEmpty }) else {
            return nil
        }
        return LioTransportOption(mode: .rail, number: item.number, carrierZH: nil, carrierEN: nil, departure: departure,
                                  arrival: arrival, departTime: item.departTime, arriveTime: item.arriveTime,
                                  durationMinutes: item.durationMin, fares: fares)
    }

    private static func flight(_ item: Reply.Flight) -> LioTransportOption? {
        guard !item.number.isEmpty, item.number.count <= 8, clock(item.departTime), clock(item.arriveTime),
              (1...2 * 1440).contains(item.durationMin) else {
            return nil
        }
        func airport(_ value: Reply.Airport) -> LioTransportHub? {
            guard value.iata.range(of: #"^[A-Z]{3}$"#, options: .regularExpression) != nil else { return nil }
            if let known = knownAirport(value.iata) { return known }
            let nameZH = value.nameZh ?? value.iata
            return LioTransportHub(kind: .airport, nameZH: nameZH, nameEN: value.nameEn ?? nameZH, code: value.iata)
        }
        guard let departure = airport(item.departAirport), let arrival = airport(item.arriveAirport) else { return nil }
        return LioTransportOption(mode: .flight, number: item.number, carrierZH: item.carrier?.nameZh,
                                  carrierEN: item.carrier?.nameEn ?? item.carrier?.nameZh, departure: departure,
                                  arrival: arrival, departTime: item.departTime, arriveTime: item.arriveTime,
                                  durationMinutes: item.durationMin, fares: [])
    }
}

#if os(iOS)
extension LioTransportRelayClient {
    /// Internal testers only, when the build enables intercity search (`G2CTransportEnabled`).
    public static func internalBeta(endpoint: MessageEndpoint,
                                    isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioTransportRelayClient? {
        guard endpoint.allowsDemoBetaActivation,
              Bundle.main.object(forInfoDictionaryKey: "G2CTransportEnabled") as? String == "YES" else {
            return nil
        }
        return LioTransportRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = 30
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: request.httpBody?.count ?? 0, uploadFinished: nil)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }
            let (stream, response) = try await session.bytes(for: request)
            let limit = min(endpoint.maximumResponseBytes, Self.maximumResponseBytes)
            guard response.expectedContentLength <= limit else { throw LioTransportRelayFailure.unavailable }
            var body = Data()
            for try await byte in stream {
                guard body.count < limit else { throw LioTransportRelayFailure.unavailable }
                body.append(byte)
            }
            return (body, response)
        }
    }
}
#endif

#if os(iOS)
import SwiftUI

private struct LioTransportRelayKey: EnvironmentKey {
    static let defaultValue: LioTransportRelayClient? = nil
}

extension EnvironmentValues {
    /// Set by the App host for internal testers when `G2CTransportEnabled` is YES; nil keeps the guide-only page.
    public var lioTransportRelay: LioTransportRelayClient? {
        get { self[LioTransportRelayKey.self] }
        set { self[LioTransportRelayKey.self] = newValue }
    }
}
#endif
