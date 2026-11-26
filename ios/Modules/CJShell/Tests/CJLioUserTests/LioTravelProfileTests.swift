import Foundation
import Testing
@testable import CJLioUser

/// #1739 W3-1: the travel profile gathered from this device's stores, and what each tool fills from it.
@MainActor struct LioTravelProfileTests {
    private let today = LioTripDay("2026-12-01")!
    private let place = LioTaxiPlace(nameZH: "北京王府井希尔顿酒店", nameEN: "Hilton Beijing Wangfujing",
                                     addressZH: "北京市东城区王府井东街8号", addressEN: "8 Wangfujing East St",
                                     coordinate: .init(latitude: 39.9139, longitude: 116.4143, referenceSystem: .gcj02))
    private var hotel: LioStayHotel { LioStayHotel(place: place, roomNumber: "1208", source: .manual) }

    private func plan(_ id: String, start: String?, days: Int) -> LioPlanSummary {
        LioPlanSummary(tripID: id, tripVersion: 1, title: id, startDate: start, undated: start == nil,
                       days: (1...days).map { LioPlanSummary.Day(number: $0, date: nil, items: []) })
    }

    private func tripHome(arrival: String?, stayDays: Int?, cityID: String?, planID: String? = nil,
                          ended: [String]? = nil) -> LioTripHomeStore.Snapshot {
        LioTripHomeStore.Snapshot(profile: LioTripProfile(arrival: arrival.flatMap(LioTripDay.init), stayDays: stayDays,
                                                          cityID: cityID, planID: planID, startedAt: .distantPast),
                                  endedPlanIDs: ended)
    }

    private var showCard: LioShowCardDetails {
        var details = LioShowCardDetails()
        details.foodAllergies = [.peanut, .milk, .wheat]
        return details
    }

    // MARK: - Aggregation

    @Test func everySourcePresentFillsEveryField() {
        let profile = LioTravelProfile.aggregate(
            tripHome: tripHome(arrival: "2026-12-10", stayDays: 5, cityID: "beijing"),
            plans: [plan("p1", start: "2026-12-10", days: 4)], nationality: "GB", hotel: hotel, showCard: showCard,
            today: today)
        // The trip home's own answers win over the plan's.
        #expect(profile.arrival == LioTripDay("2026-12-10"))
        #expect(profile.stayDays == 5)
        #expect(profile.city == .init(id: "beijing", nameZH: "北京", nameEN: "Beijing"))
        #expect(profile.nationality == "GB")
        #expect(profile.hotel == hotel)
        #expect(profile.dietary == [.peanut, .dairy, .gluten])
        #expect(profile.lastDay == LioTripDay("2026-12-14"))
    }

    @Test func missingSourcesLeaveOnlyTheirFieldsEmpty() {
        // No trip home: dates come from the current saved plan; there is no city, hotel or allergy to read.
        let fromPlan = LioTravelProfile.aggregate(tripHome: nil, plans: [plan("p1", start: "2026-12-20", days: 3)],
                                                  nationality: "  ", hotel: nil, showCard: LioShowCardDetails(), today: today)
        #expect(fromPlan.arrival == LioTripDay("2026-12-20"))
        #expect(fromPlan.stayDays == 3)
        #expect(fromPlan.city == nil)
        #expect(fromPlan.nationality == nil)
        #expect(fromPlan.hotel == nil)
        #expect(fromPlan.dietary.isEmpty)

        // A trip home with only a city: the undated plan gives the days, nothing gives the arrival.
        let cityOnly = LioTravelProfile.aggregate(tripHome: tripHome(arrival: nil, stayDays: nil, cityID: "chengdu"),
                                                  plans: [plan("p2", start: nil, days: 2)], nationality: "DE",
                                                  hotel: nil, showCard: nil, today: today)
        #expect(cityOnly.arrival == nil)
        #expect(cityOnly.stayDays == 2)
        #expect(cityOnly.city?.nameZH == "成都")
        #expect(cityOnly.nationality == "DE")

        // An unknown city id and an ended plan are not used.
        let ended = LioTravelProfile.aggregate(tripHome: tripHome(arrival: nil, stayDays: nil, cityID: "atlantis", ended: ["p1"]),
                                               plans: [plan("p1", start: "2026-12-20", days: 3)], nationality: nil,
                                               hotel: nil, showCard: nil, today: today)
        #expect(ended.city == nil)
        #expect(ended.arrival == nil)
        #expect(ended.stayDays == nil)
    }

    @Test func noSourcesGiveAnEmptyProfile() {
        let profile = LioTravelProfile.aggregate(tripHome: nil, plans: [], nationality: nil, hotel: nil, showCard: nil,
                                                 today: today)
        #expect(profile == LioTravelProfile())
        #expect(profile.hotelSearch(routeCity: nil, today: today) == ("", nil, nil))
        #expect(profile.transport(routeFrom: nil, routeTo: nil, today: today) == ("", "", nil))
        #expect(profile.taxiDestination == nil)
        #expect(profile.attractionBooking(today: today) == (nil, nil))
        #expect(profile.menuNeeds.isEmpty)
    }

    @Test func deviceSourceReadsTheAccountFilesWithoutWriting() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("travel-profile-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let plans = LioSavedPlans(directory: LioSavedPlans.storageDirectory(inMessageDirectory: root), isCurrent: { true })
        let home = LioTripHomeStore(directory: LioTripHomeStore.storageDirectory(inMessageDirectory: root), isCurrent: { true })
        let defaults = try #require(UserDefaults(suiteName: "travel-profile-" + UUID().uuidString))
        let source = LioTravelProfileSource.device(messageDirectory: root, savedPlans: plans, tripHome: home,
                                                   defaults: defaults, isCurrent: { true })
        #expect(source.read(today) == LioTravelProfile())
        #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)

        try plans.save(plan("p1", start: "2026-12-10", days: 4))
        try home.save(tripHome(arrival: nil, stayDays: nil, cityID: "beijing"))
        try LioReturnHotelStore(directory: LioReturnHotelStore.storageDirectory(inMessageDirectory: root),
                                isCurrent: { true }).save(hotel)
        try LioShowCardDetailsStore(directory: LioShowCardDetailsStore.storageDirectory(inMessageDirectory: root),
                                    isCurrent: { true }).save(showCard)
        defaults.set("FR", forKey: LioArrivalTrip.nationalityStorageKey)
        let profile = source.read(today)
        #expect(profile.arrival == LioTripDay("2026-12-10"))
        #expect(profile.stayDays == 4)
        #expect(profile.city?.id == "beijing")
        #expect(profile.nationality == "FR")
        #expect(profile.hotel == hotel)
        #expect(profile.dietary == [.peanut, .dairy, .gluten])

        let signedOut = LioTravelProfileSource.device(messageDirectory: root, savedPlans: plans, tripHome: home,
                                                      defaults: defaults, isCurrent: { false })
        #expect(signedOut.read(today) == LioTravelProfile())
    }

    @Test func toolsReadTheProfileThroughTheirServices() {
        var context = LioToolContext(language: .english)
        #expect(context.travelProfile().profile == LioTravelProfile())
        var stored = LioTravelProfile()
        stored.nationality = "JP"
        context.services = LioToolServices().with(LioTravelProfileSource { _ in stored })
        #expect(context.travelProfile().profile.nationality == "JP")
    }

    // MARK: - What each tool fills

    private var full: LioTravelProfile {
        LioTravelProfile.aggregate(tripHome: tripHome(arrival: "2026-12-10", stayDays: 5, cityID: "beijing"), plans: [],
                                   nationality: "GB", hotel: hotel, showCard: showCard, today: today)
    }

    @Test func hotelsFillCityCheckInAndNights() {
        let search = full.hotelSearch(routeCity: nil, today: today)
        #expect(search.city == "北京")
        #expect(search.checkIn == LioTripDay("2026-12-10"))
        #expect(search.nights == 4)
        // A route's city wins; during the trip the stay starts today.
        let during = full.hotelSearch(routeCity: "上海", today: LioTripDay("2026-12-12")!)
        #expect(during.city == "上海")
        #expect(during.checkIn == LioTripDay("2026-12-12"))
        #expect(during.nights == 2)
        // After the trip no date is offered.
        #expect(full.hotelSearch(routeCity: nil, today: LioTripDay("2026-12-20")!).checkIn == nil)
    }

    @Test func intercityFillsTheTripCityAsOriginAndTheNextTripDay() {
        let trip = full.transport(routeFrom: nil, routeTo: nil, today: today)
        #expect(trip.from == "北京")
        #expect(trip.to == "")
        #expect(trip.date == LioTripDay("2026-12-10"))
        let routed = full.transport(routeFrom: "西安", routeTo: "成都", today: today)
        #expect(routed.from == "西安")
        #expect(routed.to == "成都")
    }

    @Test func taxiFillsTheSavedHotelAsDestination() {
        #expect(full.taxiDestination == place)
    }

    @Test func sightBookingsFillTheCityAndVisitDay() {
        let booking = full.attractionBooking(today: today)
        #expect(booking.cityZH == "北京")
        #expect(booking.visit == LioTripDay("2026-12-10"))
        // The trip's city name matches the rules' own city names.
        #expect(LioAttractionBookingRule.all.contains { $0.cityZH == booking.cityZH })
    }

    @Test func menuTicksTheSavedFoodAllergies() {
        #expect(full.menuNeeds == [.peanut, .dairy, .gluten])
        #expect(LioFoodAllergen.allCases.map(\.dietaryNeed) == LioDietaryNeed.allergies)
    }
}
