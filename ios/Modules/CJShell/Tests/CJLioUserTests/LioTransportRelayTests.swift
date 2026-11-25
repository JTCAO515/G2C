import Foundation
import Testing
@testable import CJLioUser

/// #1521: the App half of TRANSPORT.1 (`POST /v1/tools/transport/search`, contracts/api/TRANSPORT.1.md).
@MainActor struct LioTransportRelayTests {
    private let origin = URL(string: "https://api-beta.go2china.space")!
    private let route = URL(string: "https://api-beta.go2china.space/v1/tools/transport/search")!

    private func response(_ url: URL, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: nil)!
    }

    private func query() throws -> LioTransportQuery {
        try LioTransportQuery.make(from: "上海", to: "北京", date: LioTransportQuery.date(year: 2026, month: 12, day: 3),
                                   today: LioTransportQuery.date(year: 2026, month: 11, day: 25)).get()
    }

    static let reply = Data("""
        {"version":"TRANSPORT.1","date":"2026-12-03",
         "origin":{"id":"shanghai","name_zh":"上海","name_en":"Shanghai"},
         "destination":{"id":"beijing","name_zh":"北京","name_en":"Beijing"},
         "rail":{"status":"ok","source":"AMap","items":[
           {"number":"G2","depart_station":{"name_zh":"上海虹桥站","name_en":"Shanghai Hongqiao Railway Station"},
            "arrive_station":{"name_zh":"北京南站"},"depart_time":"08:00","arrive_time":"12:28","duration_min":268,
            "next_day":false,"seats":[{"class_zh":"二等座","class_en":"Second class","price_cny_minor":62600}],
            "availability":null}],
          "availability_note_zh":"余票以 12306 为准","availability_note_en":"Seats left: check on 12306"},
         "flight":{"status":"ok","source":"VariFlight","items":[
           {"number":"MU5101","carrier":{"name_zh":"东方航空","name_en":"China Eastern"},
            "depart_airport":{"iata":"SHA","name_zh":"上海虹桥国际机场","name_en":"Shanghai Hongqiao International Airport"},
            "arrive_airport":{"iata":"PEK","name_zh":"北京首都国际机场","name_en":"Beijing Capital International Airport"},
            "depart_time":"07:30","arrive_time":"09:40","duration_min":130,"next_day":false}],
          "price_note_zh":"价格随时变动，以订票页为准","price_note_en":"Prices change often; check when booking"},
         "links":[{"mode":"rail","provider":"12306","url":"https://www.12306.cn/en/index.html"}]}
        """.utf8)

    @Test func sendsTheCityIdsDayAndBothModesToTheFixedRoute() async throws {
        var sent: [URLRequest] = []
        let relay = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { request in
            sent.append(request)
            return (Self.reply, response(route, status: 200))
        }
        let result = try await relay.search(try query())
        let request = try #require(sent.first)
        #expect(sent.count == 1 && request.url == route && request.httpMethod == "POST")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer synthetic-owner")
        let bytes = try #require(request.httpBody)
        let body = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        #expect(body.keys.sorted() == ["date", "destination", "modes", "origin", "version"])
        #expect(body["version"] as? String == "TRANSPORT.1" && body["origin"] as? String == "shanghai")
        #expect(body["destination"] as? String == "beijing" && body["date"] as? String == "2026-12-03")
        #expect(body["modes"] as? [String] == ["rail", "flight"])
        #expect(!result.isSample && result.bus == .guideOnly)
    }

    @Test func projectsTrainsAndFlightsWithoutInventingSeats() async throws {
        let relay = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
            (Self.reply, response(route, status: 200))
        }
        let result = try await relay.search(try query())
        let train = try #require(result.rail.options.first)
        #expect(train.number == "G2" && train.mode == .rail && train.durationMinutes == 268)
        #expect(train.departure.nameZH == "上海虹桥站" && train.departure.nameEN == "Shanghai Hongqiao Railway Station")
        #expect(train.arrival.nameZH == "北京南站" && train.arrival.nameEN == "Beijing South Railway Station")
        #expect(train.fares == [LioTransportFare(classZH: "二等座", classEN: "Second class", priceMinor: 62_600)])
        let flight = try #require(result.flight.options.first)
        #expect(flight.number == "MU5101" && flight.carrierEN == "China Eastern" && flight.carrierZH == "东方航空")
        #expect(flight.departure.code == "SHA" && flight.departure.kind == .airport)
        #expect(flight.arrival.nameEN == "Beijing Capital International Airport" && flight.fares.isEmpty)
    }

    @Test func eachModeStatusMapsWithoutHidingTheOther() async throws {
        for (status, expected) in [("empty", LioTransportModeResult.options([])), ("unavailable", .unavailable),
                                   ("quota_exceeded", .unavailable), ("not_enabled", .guideOnly)] {
            let text = String(decoding: Self.reply, as: UTF8.self)
                .replacingOccurrences(of: #""rail":\{"status":"ok","source":"AMap","items":\[[\s\S]*?"availability":null\}\]"#,
                                      with: #""rail":{"status":"\#(status)","source":"AMap","items":[]"#,
                                      options: .regularExpression)
            let relay = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
                (Data(text.utf8), response(route, status: 200))
            }
            let result = try await relay.search(try query())
            #expect(result.rail == expected, "\(status)")
            #expect(result.flight.options.count == 1)
        }
    }

    @Test func missingCredentialOrSessionDoesNotSend() async throws {
        var calls = 0
        let exchange: LioTransportRelayClient.Exchange = { _ in
            calls += 1
            return (Self.reply, response(route, status: 200))
        }
        let missing = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { nil }, exchange: exchange)
        let retired = LioTransportRelayClient(baseURL: origin, isCurrent: { false }, bearer: { "synthetic-owner" },
                                              exchange: exchange)
        let request = try query()
        await #expect(throws: LioTransportRelayFailure.signInRequired) { try await missing.search(request) }
        await #expect(throws: LioTransportRelayFailure.signInRequired) { try await retired.search(request) }
        #expect(calls == 0)
    }

    @Test func rejectsForeignSourceOversizeWrongVersionAndOtherCities() async throws {
        let foreign = URL(string: "https://example.invalid/v1/tools/transport/search")!
        let wrongVersion = Data(String(decoding: Self.reply, as: UTF8.self)
            .replacingOccurrences(of: #""version":"TRANSPORT.1""#, with: #""version":"TRANSPORT.2""#).utf8)
        let otherCity = Data(String(decoding: Self.reply, as: UTF8.self)
            .replacingOccurrences(of: #""id":"beijing""#, with: #""id":"xian""#).utf8)
        let seatsClaimed = Data(String(decoding: Self.reply, as: UTF8.self)
            .replacingOccurrences(of: #""availability":null"#, with: #""availability":"有票""#).utf8)
        let request = try query()
        for (url, data) in [(foreign, Self.reply), (route, Data(repeating: 0x20, count: 131_073)), (route, wrongVersion),
                            (route, otherCity), (route, seatsClaimed), (route, Data("{}".utf8))] {
            let relay = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
                (data, response(url, status: 200))
            }
            await #expect(throws: LioTransportRelayFailure.unavailable) { try await relay.search(request) }
        }
    }

    @Test func reportsServerAndNetworkFailuresWithoutRetrying() async throws {
        let request = try query()
        let cases: [(Int, LioTransportRelayFailure)] = [(401, .signInRequired), (403, .unavailableForAccount),
                                                       (429, .quotaExceeded), (302, .unavailable), (503, .unavailable)]
        for (status, failure) in cases {
            var requests = 0
            let relay = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
                requests += 1
                return (Data(), response(route, status: status))
            }
            await #expect(throws: failure) { try await relay.search(request) }
            #expect(requests == 1)
        }
        let offline = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
            throw URLError(.notConnectedToInternet)
        }
        await #expect(throws: LioTransportRelayFailure.offline) { try await offline.search(request) }
    }

    @Test func failuresHaveBilingualMessages() {
        for failure in [LioTransportRelayFailure.signInRequired, .unavailableForAccount, .quotaExceeded, .offline,
                        .timedOut, .unavailable] {
            #expect(!failure.message(.english).isEmpty && !failure.message(.chinese).isEmpty)
        }
    }

    @Test func theRelayReplacesOnlyTheGuideNeverTheDebugSample() async throws {
        let relay = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
            (Self.reply, response(route, status: 200))
        }
        #expect(LioTransportService.guideOnly.isGuideOnly)
        #expect(try await LioTransportService.guideOnly.upgraded(with: relay).search(try query()).rail.options.count == 1)
        #expect(try await LioTransportService.guideOnly.upgraded(with: nil).search(try query()).rail == .guideOnly)
        #if DEBUG
        #expect(try await LioTransportService.preview.upgraded(with: relay).search(try query()).isSample)
        #endif
    }

    @Test func aRelayServiceIsPreferredOverTheGuideWhenTheBuildEnablesIt() async throws {
        let relay = LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { _ in
            (Self.reply, response(route, status: 200))
        }
        let enabled = ["G2CTransportEnabled": "YES"]
        let live = try #require(LioTransportService.fromBuild(arguments: [], info: enabled, relay: relay))
        #expect(try await live.search(try query()).rail.options.count == 1)
        #expect(LioTransportService.fromBuild(arguments: [], info: [:], relay: relay) == nil)
        let guide = try #require(LioTransportService.fromBuild(arguments: [], info: enabled, relay: nil))
        #expect(try await guide.search(try query()).rail == .guideOnly)
    }
}
