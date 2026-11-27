import Foundation
import Testing
@testable import CJLioUser

/// #2007: 大交通 = city compare (unchanged) + flight/train lookup + airport and station facts.
struct LioFlightQueryTests {
    private let today = LioTransportQuery.date(year: 2026, month: 11, day: 27)

    @Test func normalizesWhatPeopleTypeAndRejectsTheRest() throws {
        #expect(LioFlightQuery.normalize(" mu 5102 ") == "MU5102")
        #expect(LioFlightQuery.normalize("ＣＡ９８１") == "CA981")
        #expect(LioFlightQuery.normalize("3U-8888") == "3U8888")
        let ok = try LioFlightQuery.make(number: "mu5102", date: today, today: today).get()
        #expect(ok == LioFlightQuery(number: "MU5102", day: "2026-11-27"))
        #expect(LioFlightQuery.make(number: "", date: today, today: today) == .failure(.emptyNumber))
        for bad in ["5102", "M", "MU", "MUUU5102", "MU510221", "MU 5102 X1", "MU5102; DROP", "航班"] {
            #expect(LioFlightQuery.make(number: bad, date: today, today: today) == .failure(.badNumber), "\(bad)")
        }
        // The server's own pattern also allows a trailing letter and a digit-led carrier code.
        #expect((try? LioFlightQuery.make(number: "CA1234A", date: today, today: today).get()) != nil)
        #expect((try? LioFlightQuery.make(number: "9C8888", date: today, today: today).get()) != nil)
    }

    @Test func dayWindowIsYesterdayToSixtyDaysAhead() {
        func make(_ offset: Int) -> Result<LioFlightQuery, LioFlightQuery.Problem> {
            let day = LioTransportQuery.calendar.date(byAdding: .day, value: offset, to: today)!
            return LioFlightQuery.make(number: "MU5102", date: day, today: today)
        }
        #expect((try? make(-1).get()) != nil)
        #expect(make(-2) == .failure(.pastDate))
        #expect((try? make(60).get()) != nil)
        #expect(make(61) == .failure(.tooFarAhead))
    }
}

struct LioFlightTimeTextTests {
    @Test func showsClockOnTheQueriedDayAndDateOtherwise() {
        #expect(LioFlightTimeText.display("2026-11-27 08:05:00", queriedDay: "2026-11-27") == "08:05")
        #expect(LioFlightTimeText.display("2026-11-27T08:05", queriedDay: "2026-11-27") == "08:05")
        #expect(LioFlightTimeText.display("2026-11-27T08:05:00+08:00", queriedDay: "2026-11-27") == "08:05")
        #expect(LioFlightTimeText.display("2026-11-28 00:30:00", queriedDay: "2026-11-27") == "11-28 00:30")
        #expect(LioFlightTimeText.display("08:05", queriedDay: "2026-11-27") == "08:05")
        // Anything else is shown as the supplier wrote it, never guessed.
        #expect(LioFlightTimeText.display("Delayed 20 min", queriedDay: "2026-11-27") == "Delayed 20 min")
    }
}

@MainActor struct LioFlightRelayTests {
    private let origin = URL(string: "https://api-beta.go2china.space")!
    private let route = URL(string: "https://api-beta.go2china.space/v1/tools/flights")!
    private let query = LioFlightQuery(number: "MU5102", day: "2026-11-27")

    private func response(_ url: URL, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: nil)!
    }

    static let reply = Data("""
        {"version":"FLIGHTS.1","source":"VariFlight","date":"2026-11-27","more":false,
         "items":[{"flight_number":"MU5102","departure":"SHA","arrival":"PEK","status":"Scheduled","codeshare":false,
                   "planned_departure":"2026-11-27 08:00:00","planned_arrival":"2026-11-27 10:15:00",
                   "departure_terminal":"T2","arrival_terminal":"T3","gate":"B2","airline_name_zh":"东方航空"}]}
        """.utf8)

    private func client(status: Int = 200, body: Data = reply, sent: @escaping @MainActor (URLRequest) -> Void = { _ in })
        -> LioTransportRelayClient {
        LioTransportRelayClient(baseURL: origin, isCurrent: { true }, bearer: { "synthetic-owner" }) { request in
            sent(request)
            return (body, response(route, status: status))
        }
    }

    @Test func sendsNumberAndDayToTheFixedRouteWithTheCallersBearer() async throws {
        var sent: [URLRequest] = []
        let result = try await client { sent.append($0) }.flightStatus(query)
        let request = try #require(sent.first)
        #expect(sent.count == 1 && request.url == route && request.httpMethod == "POST")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer synthetic-owner")
        let bytes = try #require(request.httpBody)
        let body = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        #expect(body.keys.sorted() == ["date", "flight_number", "version"])
        #expect(body["version"] as? String == "FLIGHTS.1" && body["flight_number"] as? String == "MU5102")
        let flight = try #require(result.flights.first)
        #expect(flight.flightNumber == "MU5102" && flight.gate == "B2" && flight.departureTerminal == "T2")
        #expect(flight.airline(.chinese) == "东方航空" && flight.airline(.english) == "东方航空")
        // Names the supplier left out come from the bundled city table; a code with no name stays a code.
        #expect(flight.airportName(departure: true, .english) == "Shanghai Hongqiao International Airport")
        #expect(flight.airportName(departure: false, .chinese) == "北京首都国际机场")
        #expect(flight.arrivalNameFallbackIsCode(for: "XXX") == "XXX")
        #expect(!result.more)
    }

    @Test func mapsHttpStatusesToTravellerFailures() async throws {
        for (status, expected) in [(401, LioTransportRelayFailure.signInRequired), (403, .unavailableForAccount),
                                   (429, .quotaExceeded), (502, .lookupUnavailable), (503, .lookupUnavailable),
                                   (504, .lookupUnavailable)] {
            await #expect(throws: expected) { try await client(status: status, body: Data()).flightStatus(query) }
        }
    }

    @Test func rejectsRepliesForAnotherDayVersionOrMalformedRows() async throws {
        let bodies = [
            #"{"version":"FLIGHTS.1","source":"VariFlight","date":"2026-11-28","more":false,"items":[]}"#,
            #"{"version":"FLIGHTS.2","source":"VariFlight","date":"2026-11-27","more":false,"items":[]}"#,
            #"{"version":"FLIGHTS.1","source":"VariFlight","date":"2026-11-27","more":false,"items":[{"flight_number":"bad number"}]}"#,
            #"{"version":"FLIGHTS.1","source":"VariFlight","date":"2026-11-27","more":false,"items":[{"flight_number":"MU5102","departure":"shanghai"}]}"#,
            "not json",
        ]
        for body in bodies {
            await #expect(throws: LioTransportRelayFailure.lookupUnavailable) {
                try await client(body: Data(body.utf8)).flightStatus(query)
            }
        }
    }

    @Test func zeroRowsIsAnAnswerNotAnError() async throws {
        let empty = Data(#"{"version":"FLIGHTS.1","source":"VariFlight","date":"2026-11-27","more":false,"items":[]}"#.utf8)
        let result = try await client(body: empty).flightStatus(query)
        #expect(result.flights.isEmpty)
    }

    @Test func aStaleSessionNeverSends() async {
        var sent = 0
        let stale = LioTransportRelayClient(baseURL: origin, isCurrent: { false }, bearer: { "synthetic-owner" }) { _ in
            sent += 1
            return (Self.reply, response(route, status: 200))
        }
        await #expect(throws: LioTransportRelayFailure.signInRequired) { try await stale.flightStatus(query) }
        #expect(sent == 0)
    }
}

private extension LioFlightStatus {
    /// A code with no supplier name and no table entry is shown as the code.
    func arrivalNameFallbackIsCode(for code: String) -> String? {
        LioFlightStatus(flightNumber: flightNumber, departure: nil, arrival: code, codeshare: nil, status: nil,
                        plannedDeparture: nil, plannedArrival: nil, actualDeparture: nil, actualArrival: nil,
                        departureTerminal: nil, arrivalTerminal: nil, gate: nil, checkInCounter: nil,
                        baggageCarousel: nil, airlineNameZh: nil, airlineNameEn: nil, departureAirportNameZh: nil,
                        departureAirportNameEn: nil, arrivalAirportNameZh: nil, arrivalAirportNameEn: nil)
            .airportName(departure: false, .english)
    }
}

struct LioTrainLookupTests {
    @Test func acceptsRealTrainNumbersAndOnlySendsToTwelveThreeOhSix() {
        for ok in ["G1", "g1234", "D 3125", "K105", "Z7", "1461", "C2001", "ｇ１"] {
            #expect((try? LioTrainLookup.check(ok).get()) != nil, "\(ok)")
        }
        #expect(LioTrainLookup.check(" g 1 ") == .success("G1"))
        #expect(LioTrainLookup.check("") == .failure(.empty))
        for bad in ["GG1", "G12345", "MU5102", "G", "12 306", "G1;x"] {
            #expect(LioTrainLookup.check(bad) == .failure(.badNumber), "\(bad)")
        }
        #expect(LioTrainLookup.byNumberURL.host == "mobile.12306.cn" && LioTrainLookup.byNumberURL.scheme == "https")
        #expect(LioTrainLookup.englishURL.host == "www.12306.cn")
        #expect(!LioTrainLookup.reason(.chinese).isEmpty && !LioTrainLookup.reason(.english).isEmpty)
    }
}

struct LioHubPackTests {
    private func pack() throws -> LioHubPack {
        let bundled = LioHubPack.bundled()
        try #require(!bundled.places.isEmpty, "the bundled pack must load")
        return bundled
    }

    @Test func theBundledDevPackIsAValidDraftForSixCities() throws {
        let pack = try pack()
        #expect(pack.status == .draft && pack.places.count == 50)
        #expect(pack.cities == LioHubPack.cityOrder)
        #expect(Set(pack.places.map(\.id)).count == 50)
        for place in pack.places {
            #expect(place.officialURL != nil, "\(place.id)")
            #expect(!place.nameZh.isEmpty && !place.nameEn.isEmpty && place.checkedOn != nil)
            if place.hubType == .airport { #expect(place.code?.count == 3) }
        }
        #expect(pack.airport(code: "PEK")?.nameEn == "Beijing Capital International Airport")
        #expect(pack.hubs(in: "beijing", kind: .airport).count == 2 && pack.hubs(in: "chengdu", kind: .rail).count == 7)
        // Every airport the compare page names for these six cities has an entry here.
        for city in LioTransportCity.all where LioHubPack.cityOrder.contains(city.id) {
            for airport in city.airports { #expect(pack.airport(code: airport.code ?? "") != nil, "\(airport.nameZH)") }
        }
    }

    @Test func aDraftNeedsDebugOrTheDraftSwitchAndAnApprovedPackDoesNot() throws {
        let draft = try pack()
        #expect(draft.isVisible(isDebug: true, draftFlagOn: false))
        #expect(draft.isVisible(isDebug: false, draftFlagOn: true))
        #expect(!draft.isVisible(isDebug: false, draftFlagOn: false))
        let approved = LioHubPack(version: LioHubPack.version, status: .approved, places: draft.places)
        #expect(approved.isVisible(isDebug: false, draftFlagOn: false))
        #expect(!LioHubPack.empty.isVisible(isDebug: true, draftFlagOn: true))
        #expect(LioHubPack.draftFlagOn(info: ["G2CTransportHubsDraftEnabled": "YES"]))
        #expect(!LioHubPack.draftFlagOn(info: ["G2CTransportHubsDraftEnabled": "$(G2C_TRANSPORT_HUBS_DRAFT_ENABLED)"]))
        #expect(!LioHubPack.draftFlagOn(info: [:]) && !LioHubPack.draftFlagOn(info: nil))
    }

    @Test func aBadPackIsRejectedWhole() {
        func decode(_ places: String, version: String = LioHubPack.version) -> LioHubPack? {
            LioHubPack.decode(Data(#"{"version":"\#(version)","status":"approved","places":[\#(places)]}"#.utf8))
        }
        let good = #"{"id":"pl_bj_pek","city":"beijing","hub_type":"airport","name_zh":"北京首都国际机场","name_en":"Beijing Capital International Airport","code":"PEK"}"#
        #expect(decode(good) != nil)
        #expect(decode(good, version: "g2c-transport-hubs.2") == nil)
        #expect(decode(good + "," + good) == nil)
        #expect(decode(good.replacingOccurrences(of: "\"PEK\"", with: "\"pek\"")) == nil)
        #expect(decode(good.replacingOccurrences(of: "\"beijing\"", with: "\"atlantis\"")) == nil)
        #expect(decode(good.replacingOccurrences(of: "\"airport\"", with: "\"helipad\"")) == nil)
    }

    @Test func officialLinksMustBePlainHttps() {
        func place(_ url: String?) -> LioHubPlace? {
            let value = url.map { "\"\($0)\"" } ?? "null"
            let json = #"{"version":"g2c-transport-hubs.1","status":"approved","places":[{"id":"pl_bj_x","city":"beijing","hub_type":"rail","name_zh":"北京站","name_en":"Beijing Railway Station","official_url":\#(value)}]}"#
            return LioHubPack.decode(Data(json.utf8))?.places.first
        }
        #expect(place("https://www.bcia.com.cn/wljc.html")?.officialURL != nil)
        #expect(place("http://www.bcia.com.cn/")?.officialURL == nil)
        #expect(place("javascript:alert(1)")?.officialURL == nil)
        #expect(place(nil)?.officialURL == nil)
    }

    @Test func englishFallsBackToChineseWhenTheEnglishWasNotWritten() throws {
        let hub = try #require(try pack().places.first { $0.id == "pl_bj_pek" })
        #expect(!hub.toCity(.english).isEmpty && hub.toCity(.english) == hub.toCityEn)
        #expect(hub.tips(.english) == hub.foreignerTipsZh && hub.tips(.chinese) == hub.foreignerTipsZh)
        let terminal = try #require(hub.terminals?.first)
        #expect(hub.terminalNote(terminal, .english) == terminal.noteZh)
    }
}
