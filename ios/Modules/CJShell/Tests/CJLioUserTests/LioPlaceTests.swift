import Foundation
import Testing
@testable import CJLioUser

/// #1992: the place model, its lookup and what the place page says and offers.
struct LioPlaceTests {
    private static func decode(_ json: String) -> [LioPlace] {
        LioPlaceRepository.places(in: Data(json.utf8))
    }

    private static let all: Set<LioTool> = [.taxi, .attractionBooking]

    private static var samples: LioPlaceRepository { .samples }

    // MARK: Decoding

    @Test func aLibraryEntryDecodesWithItsNestedFields() throws {
        let places = Self.decode("""
        {"version": "g2c-places.1", "places": [{
          "id": "pl_bj_gugong", "city": "beijing", "category": "attraction", "subcategory": "museum",
          "name_zh": " 故宫博物院 ", "name_en": "The Palace Museum", "aliases_zh": ["故宫", ""], "aliases_en": [],
          "address_zh": "北京市东城区景山前街4号", "address_en": null,
          "nearest_metro": {"station_zh": "小什字", "station_en": "Xiaoshizi", "line": "1号线", "exit": "5B"},
          "hours_zh": "08:30–17:00", "intro_short_zh": "一句话", "intro_short_en": null,
          "ticket": {"booking": "required", "passport_required": true, "price_cny": 60, "closed_weekdays": [1, 1, 9],
                     "booking_channel_zh": "官方", "booking_url": "https://ticket.dpm.org.cn/"},
          "official_url": "https://intl.dpm.org.cn/visit", "checked_on": "2026-11-27", "visit_minutes": 120,
          "location": {"gcj02": {"lat": 39.9165, "lng": 116.3971}, "amap_id": null, "method": "manual"},
          "rank": null, "review": {"status": "approved"}
        }]}
        """)
        let place = try #require(places.first)
        #expect(places.count == 1)
        #expect(place.id == "pl_bj_gugong" && place.category == .attraction && place.kind == "museum")
        #expect(place.nameZH == "故宫博物院" && place.nameEN == "The Palace Museum")
        #expect(place.aliasesZH == ["故宫"] && place.introShortEN == nil && place.introShort(.english) == "一句话")
        #expect(place.point == .init(latitude: 39.9165, longitude: 116.3971))
        #expect(place.nearestMetro == .init(stationZH: "小什字", stationEN: "Xiaoshizi", line: "1号线", exit: "5B"))
        let ticket = try #require(place.ticket)
        #expect(ticket.booking == .required && ticket.passportRequired == true && ticket.priceCNY == 60)
        #expect(ticket.closedWeekdays == [1])
        #expect(ticket.bookingURL?.absoluteString == "https://ticket.dpm.org.cn/")
        #expect(place.officialURL?.host == "intl.dpm.org.cn" && place.checkedOn == "2026-11-27" && place.visitMinutes == 120)
    }

    @Test func theSlimAppCopyDecodesToo() throws {
        let places = Self.decode("""
        {"version": "g2c-places-app.1", "places": [{
          "id": "pl_sh_waitan", "city": "shanghai", "category": "attraction", "kind": "street", "tier": "main", "rank": 1,
          "name_zh": "外滩", "name_en": "The Bund", "aliases_zh": [], "aliases_en": ["Bund"],
          "lat": 31.2400, "lng": 121.4900, "amap_id": "B0001", "intro_short_zh": "沿江看老建筑",
          "intro_short_en": "Old buildings along the river.", "thumb": "waitan.jpg"
        }]}
        """)
        let place = try #require(places.first)
        #expect(place.kind == "street" && place.thumb == "waitan.jpg" && place.aliasesEN == ["Bund"])
        #expect(place.point == .init(latitude: 31.24, longitude: 121.49))
        #expect(place.ticket == nil && place.hoursZH == nil)
    }

    @Test func missingAndMalformedFieldsAreLeftOutAndBadEntriesSkipped() {
        let places = Self.decode("""
        [
          {"id": "a", "name_zh": "甲"},
          {"id": "b", "name_zh": "乙", "name_en": 5, "category": "spaceport", "aliases_zh": "no", "ticket": "none",
           "nearest_metro": {"station_en": "x"}, "location": {"gcj02": {"lat": "north", "lng": 1}}, "visit_minutes": -3},
          {"id": "", "name_zh": "无编号"},
          {"id": "c"},
          {"id": "d", "name_en": "English only"},
          "not an object",
          {"id": "a", "name_zh": "重复"}
        ]
        """)
        #expect(places.map(\.id) == ["a", "b", "a"])
        #expect(places[0].nameEN == "甲" && places[0].category == .other && places[0].point == nil)
        let b = places[1]
        #expect(b.nameEN == "乙" && b.category == .other && b.aliasesZH.isEmpty && b.ticket == nil)
        #expect(b.nearestMetro == nil && b.point == nil && b.visitMinutes == nil)
        // The repository keeps the first of two entries with one id.
        #expect(LioPlaceRepository(places: places).place(id: "a")?.nameZH == "甲")
        #expect(LioPlaceRepository(places: places).places.count == 2)
    }

    @Test func coordinatesAndLinksAreChecked() {
        func place(_ extra: String) -> LioPlace? {
            Self.decode(#"[{"id": "x", "name_zh": "地", \#(extra)}]"#).first
        }
        #expect(place(#""lat": 0, "lng": 0"#)?.point == nil)
        #expect(place(#""lat": 91, "lng": 10"#)?.point == nil)
        #expect(place(#""lat": 30, "lng": 181"#)?.point == nil)
        #expect(place(#""lat": 30"#)?.point == nil)
        #expect(place(#""lat": 30, "lng": 120"#)?.point == .init(latitude: 30, longitude: 120))
        #expect(place(#""official_url": "http://example.cn/a""#)?.officialURL == nil)
        #expect(place(#""official_url": "https://user:pw@example.cn/a""#)?.officialURL == nil)
        #expect(place(#""official_url": "javascript:alert(1)""#)?.officialURL == nil)
        #expect(place(#""official_url": "https://example.cn/a""#)?.officialURL != nil)
        #expect(place(#""checked_on": "2026-13-45""#)?.checkedOn == nil)
        #expect(place(#""ticket": {"booking": "maybe", "closed_weekdays": []}"#)?.ticket?.closedWeekdays == [])
    }

    @Test func notAPlaceFileGivesNothing() {
        #expect(Self.decode("").isEmpty)
        #expect(Self.decode("{}").isEmpty)
        #expect(Self.decode(#"{"places": "none"}"#).isEmpty)
        #expect(Self.decode("[1, 2]").isEmpty)
    }

    // MARK: The bundled samples

    #if DEBUG
    @Test func debugBuildsReadTheSamples() throws {
        // `bundled` also honours `--places-dev-pack`; the samples are what it shows when no pack is asked for.
        let data = try #require(LioPlaceRepository.resource(LioPlaceRepository.sampleResource))
        let repository = LioPlaceRepository.debugRepository(library: nil, samples: data, arguments: ["app"], environment: [:])
        #expect(repository.places == LioPlaceRepository.samples.places)
        #expect(repository.places.allSatisfy { !repository.isDevelopmentData($0) })
    }
    #else
    @Test func releaseBuildsDoNotReadTheSamples() {
        #expect(LioPlaceRepository.bundled.places.isEmpty)
    }
    #endif

    @Test func theSamplesAreNotPassedOffAsReviewedData() throws {
        let data = try #require(LioPlaceRepository.resource(LioPlaceRepository.sampleResource))
        let text = try #require(String(data: data, encoding: .utf8))
        #expect(!text.contains("\"approved\"") && text.contains("\"sample\""))
        let repository = Self.samples
        #expect(repository.places.count >= 7)
        #expect(Set(repository.places.map(\.id)).count == repository.places.count)
        #expect(repository.place(id: "pl_bj_pek")?.terminals.isEmpty == false)
        #expect(repository.place(id: "pl_bj_qijiuba")?.point == nil)
        #expect(repository.place(id: "pl_nowhere") == nil)
    }

    // MARK: Words

    @Test func namesAndIntrosFollowTheLanguageAndFallBack() throws {
        let place = try #require(Self.decode(#"""
        [{"id": "x", "name_zh": "故宫", "name_en": "Palace", "intro_short_zh": "短", "intro_long_en": "Long"}]
        """#).first)
        #expect(place.name(.chinese) == "故宫" && place.secondaryName(.chinese) == "Palace")
        #expect(place.name(.english) == "Palace" && place.secondaryName(.english) == "故宫")
        #expect(place.introShort(.english) == "短" && place.introLong(.english) == "Long")
        #expect(place.introLong(.chinese) == "Long")
        let same = try #require(Self.decode(#"[{"id": "y", "name_zh": "外滩"}]"#).first)
        #expect(same.nameEN == "外滩" && same.secondaryName(.english) == nil)
    }

    @Test func theStatusLineSaysBookingAndClosingDays() throws {
        let palace = try #require(Self.samples.place(id: "pl_bj_gugong"))
        #expect(LioPlacePresentation(palace, language: .english).statusLine == "Booking required · Closed Mondays")
        #expect(LioPlacePresentation(palace, language: .chinese).statusLine == "需要预约 · 周一闭馆")
        let tiantan = try #require(Self.samples.place(id: "pl_bj_tiantan"))
        #expect(LioPlacePresentation(tiantan, language: .english).statusLine == "No booking needed")
        let jingshan = try #require(Self.samples.place(id: "pl_bj_jingshan"))
        #expect(LioPlacePresentation(jingshan, language: .english).statusLine == nil)
        let none = try #require(Self.decode(#"[{"id": "n", "name_zh": "甲", "ticket": {"closed_weekdays": []}}]"#).first)
        #expect(LioPlacePresentation(none, language: .english).statusLine == "No regular closing day")
        let two = try #require(Self.decode(#"[{"id": "t", "name_zh": "乙", "ticket": {"closed_weekdays": [2, 5]}}]"#).first)
        #expect(LioPlacePresentation(two, language: .english).closedText == "Closed Tuesdays, Fridays")
        #expect(LioPlacePresentation(two, language: .chinese).closedText == "周二、周五闭馆")
    }

    @Test func hoursTicketsAndDirectionsCollectWhatTheLibraryHas() throws {
        let palace = try #require(Self.samples.place(id: "pl_bj_gugong"))
        let english = LioPlacePresentation(palace, language: .english)
        #expect(english.hours.count == 2 && english.hours[0].contains("08:30") && english.hoursAreChineseOnly)
        #expect(!LioPlacePresentation(palace, language: .chinese).hoursAreChineseOnly)
        #expect(english.tickets == ["Booking required", "Passport required"])
        #expect(english.bookingChannel != nil && english.bookingURL?.scheme == "https")
        #expect(english.directions == ["北京市东城区景山前街4号"])
        #expect(english.checkedText == "Checked on 2026-11-27")
        #expect(LioPlacePresentation(palace, language: .chinese).checkedText == "核对于2026-11-27")

        let cableway = try #require(Self.samples.place(id: "pl_cq_changjiang_suodao"))
        #expect(LioPlacePresentation(cableway, language: .english).directions.last == "Nearest metro: Xiaoshizi · 1号线、6号线 · Exit 5B")
        #expect(LioPlacePresentation(cableway, language: .chinese).directions.last == "最近的地铁：小什字 · 1号线、6号线 · 5B口")

        let pek = try #require(Self.samples.place(id: "pl_bj_pek"))
        let hub = LioPlacePresentation(pek, language: .english)
        #expect(hub.directions == pek.toCityEN && hub.terminals.count == 2 && hub.tips == pek.tipsZH)
        #expect(hub.kindLabel == "Airport" && hub.symbol == "airplane")
    }

    @Test func distancesReadAsMetresOrKilometres() {
        #expect(LioPlacePresentation.distanceText(34) == "30 m")
        #expect(LioPlacePresentation.distanceText(436) == "440 m")
        #expect(LioPlacePresentation.distanceText(1_240) == "1.2 km")
    }

    @Test func copyHasBothLanguagesAndTheUICopyKeys() {
        let fromUICopy = LioPlaceCopy.allCases.filter { !$0.isPlaceholder }
        #expect(fromUICopy.map(\.rawValue).sorted() == [
            "place.add_to_trip.button", "place.book.button", "place.booking_method.label", "place.directions.label",
            "place.hours.label", "place.navigate.button", "place.nearby_food.label", "place.official_info.button",
            "place.show_driver.button", "place.taxi.button", "place.tickets.label",
        ])
        #expect(LioPlaceCopy.addToTrip.text(.chinese) == "加入行程" && LioPlaceCopy.addToTrip.text(.english) == "Add to trip")
        #expect(LioPlaceCopy.taxi.text(.chinese) == "打车去" && LioPlaceCopy.book.text(.english) == "Book")
        #expect(LioPlaceCopy.showDriver.text(.chinese) == "给司机看" && LioPlaceCopy.navigate.text(.english) == "Get directions")
        #expect(Set(LioPlaceCopy.allCases.map(\.rawValue)).count == LioPlaceCopy.allCases.count)
        for key in LioPlaceCopy.allCases {
            #expect(key.rawValue.hasPrefix("place.") && !key.text(.chinese).isEmpty && !key.text(.english).isEmpty)
            #expect(key.text(.chinese) != key.text(.english), "\(key.rawValue)")
        }
    }

    // MARK: Buttons

    @Test func aBookableSightOffersTaxiDriverDirectionsAndBooking() throws {
        let palace = try #require(Self.samples.place(id: "pl_bj_gugong"))
        let actions = LioPlacePresentation(palace, language: .english).actions { Self.all.contains($0) }
        #expect(actions.actions == [.taxi, .driver, .navigate, .book])

        let taxi = try #require(actions.taxi)
        #expect(taxi.tool == .taxi)
        #expect(Set(taxi.parameters.keys).isSubset(of: LioTaxiPlace.routeParameters))
        #expect(taxi.parameters["destination"] == "故宫博物院" && taxi.parameters["destinationEN"] == "The Palace Museum")
        let destination = try #require(LioTaxiPlace(route: taxi))
        #expect(destination.coordinate == .init(latitude: 39.9165, longitude: 116.3971, referenceSystem: .gcj02))
        #expect(destination.addressZH == "北京市东城区景山前街4号")

        let booking = try #require(actions.booking)
        #expect(booking.tool == .attractionBooking && booking.parameters == ["sight": "beijing.palace-museum"])
        let driver = try #require(actions.driver)
        #expect(driver.mainZH == "故宫博物院" && driver.noteZH == nil)
        #expect(actions.navigation?.point == palace.point)
    }

    @Test func buttonsAppearOnlyWhenTheyCanWork() throws {
        // No router, so no tool opens: the driver card and directions stay.
        let palace = try #require(Self.samples.place(id: "pl_bj_gugong"))
        let noTools = LioPlacePresentation(palace, language: .chinese).actions { _ in false }
        #expect(noTools.actions == [.driver, .navigate])

        // Booking is not known for Jingshan, and Temple of Heaven needs none: no booking button for either.
        for id in ["pl_bj_jingshan", "pl_bj_tiantan"] {
            let place = try #require(Self.samples.place(id: id))
            let actions = LioPlacePresentation(place, language: .english).actions { Self.all.contains($0) }
            #expect(actions.booking == nil, "\(id)")
            #expect(actions.taxi != nil && actions.navigation != nil, "\(id)")
        }

        // No coordinate: no taxi. The driver card says the address is not confirmed.
        let qijiuba = try #require(Self.samples.place(id: "pl_bj_qijiuba"))
        let unplaced = LioPlacePresentation(qijiuba, language: .english).actions { Self.all.contains($0) }
        #expect(unplaced.taxi == nil)
        #expect(unplaced.driver?.noteZH == "地址未确认")
        #expect(unplaced.navigation != nil && unplaced.navigation?.point == nil)

        // A restaurant is never offered a sight booking.
        let food = try #require(Self.samples.place(id: "pl_bj_sijiminfu_gugong"))
        #expect(LioPlacePresentation(food, language: .english).actions { Self.all.contains($0) }.booking == nil)

        // An airport has the taxi and the driver card, with its name and no sight booking.
        let pek = try #require(Self.samples.place(id: "pl_bj_pek"))
        let airport = LioPlacePresentation(pek, language: .english).actions { Self.all.contains($0) }
        #expect(airport.actions == [.taxi, .driver, .navigate])
        #expect(airport.driver?.mainZH == "北京首都国际机场")
    }

    // MARK: Nearby

    @Test func nearbyFoodListsRecordedRestaurantsNearestFirst() throws {
        let repository = Self.samples
        let palace = try #require(repository.place(id: "pl_bj_gugong"))
        let nearby = LioPlacePresentation(palace, language: .english).nearbyFood(in: repository)
        #expect(nearby.map(\.place.id) == ["pl_bj_sijiminfu_gugong"])
        #expect((300...600).contains(nearby[0].metres))

        // Other categories, far places and places without a coordinate are not listed; a place is not its own neighbour.
        let pek = try #require(repository.place(id: "pl_bj_pek"))
        #expect(repository.nearby(pek, category: .food, limit: 3).isEmpty)
        #expect(repository.nearby(palace, category: .attraction, limit: 5).map(\.place.id) == ["pl_bj_jingshan"])
        let qijiuba = try #require(repository.place(id: "pl_bj_qijiuba"))
        #expect(repository.nearby(qijiuba, category: .food, limit: 3).isEmpty)
        #expect(repository.nearby(palace, category: .food, limit: 0).isEmpty)
    }

    @Test func distanceBetweenPointsIsRightToAFewMetres() {
        let a = LioItinerary.Point(latitude: 39.9087, longitude: 116.3975)
        let b = LioItinerary.Point(latitude: 39.9187, longitude: 116.3975)
        #expect(abs(LioPlaceRepository.metres(from: a, to: b) - 1_112) < 5)
        #expect(LioPlaceRepository.metres(from: a, to: a) == 0)
    }
}
