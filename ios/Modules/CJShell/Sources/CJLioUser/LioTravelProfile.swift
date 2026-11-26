import Foundation

/// #1739 W3-1: what this device already knows about the trip, gathered for the tools to fill their fields.
/// Read-only: it reads the stores other features own and keeps, writes and sends nothing. A field no store
/// holds stays nil (or empty); nothing is inferred to fill it.
struct LioTravelProfile: Equatable, Sendable {
    struct City: Equatable, Sendable {
        let id: String
        let nameZH: String
        let nameEN: String
    }

    /// Trip home's arrival day, else the current saved plan's start date.
    var arrival: LioTripDay?
    /// Trip home's length of stay, else the current saved plan's number of days.
    var stayDays: Int?
    /// Trip home's first city (metro catalogue id). Saved plans carry no city.
    var city: City?
    /// The passport country code chosen in Local Support / Arrival Mode.
    var nationality: String?
    /// Back to Hotel's saved hotel.
    var hotel: LioStayHotel?
    /// Food allergies typed on the show cards. Saved memory is on the server and is not read here.
    var dietary: [LioDietaryNeed] = []

    var lastDay: LioTripDay? {
        guard let arrival, let stayDays else { return nil }
        return arrival.adding(days: max(stayDays, 1) - 1)
    }

    /// Picks the plan the same way the trip home does (`LioTripChecklist.currentPlan`), so tools and the trip home
    /// talk about the same trip.
    static func aggregate(tripHome: LioTripHomeStore.Snapshot?, plans: [LioPlanSummary], nationality: String?,
                          hotel: LioStayHotel?, showCard: LioShowCardDetails?, today: LioTripDay) -> Self {
        let profile = tripHome?.profile
        let ended = Set(tripHome?.endedPlanIDs ?? [])
        let plan = LioTripChecklist.currentPlan(profile: profile, plans: plans.filter { !ended.contains($0.tripID) },
                                                today: today)
        var result = LioTravelProfile()
        result.arrival = profile?.arrival ?? plan?.startDate.flatMap(LioTripDay.init)
        result.stayDays = profile?.stayDays ?? plan.flatMap { $0.days.isEmpty ? nil : $0.days.count }
        result.city = profile?.cityID.flatMap(LioMetroCity.named).map { City(id: $0.id, nameZH: $0.nameZH, nameEN: $0.nameEN) }
        let code = nationality?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        result.nationality = code.isEmpty ? nil : code
        result.hotel = hotel
        result.dietary = (showCard?.foodAllergies ?? []).map(\.dietaryNeed)
        return result
    }

    // MARK: - What each tool fills

    /// The first trip day a booking can still use: the arrival day before the trip, today during it, nil once it
    /// ended or without an arrival day.
    func nextTripDay(today: LioTripDay) -> LioTripDay? {
        guard let arrival else { return nil }
        if today <= arrival { return arrival }
        guard let lastDay else { return today }
        return today <= lastDay ? today : nil
    }

    /// Hotels: city, check-in and nights (to the departure day, at least one); the route's city comes first.
    func hotelSearch(routeCity: String?, today: LioTripDay) -> (city: String, checkIn: LioTripDay?, nights: Int?) {
        let city = routeCity.flatMap { $0.isEmpty ? nil : $0 } ?? self.city?.nameZH ?? ""
        let checkIn = nextTripDay(today: today)
        let nights = checkIn.flatMap { start in lastDay.map { max(start.days(until: $0), 1) } }
        return (city, checkIn, nights)
    }

    /// Intercity: leaving the trip's city on the next trip day; the route's cities come first.
    func transport(routeFrom: String?, routeTo: String?, today: LioTripDay) -> (from: String, to: String, date: LioTripDay?) {
        let from = routeFrom.flatMap { $0.isEmpty ? nil : $0 } ?? city?.nameZH ?? ""
        return (from, routeTo ?? "", nextTripDay(today: today))
    }

    /// Taxi: the saved hotel as the destination.
    var taxiDestination: LioTaxiPlace? { hotel?.place }

    /// Sight bookings: the trip's city first, and the next trip day as the visit day.
    func attractionBooking(today: LioTripDay) -> (cityZH: String?, visit: LioTripDay?) {
        (city?.nameZH, nextTripDay(today: today))
    }

    /// Menu: the needs to tick before the menu is read.
    var menuNeeds: [LioDietaryNeed] { dietary }
}

extension LioFoodAllergen {
    /// The show-card allergen as the menu's dietary need (the two lists name the same nine allergens).
    var dietaryNeed: LioDietaryNeed {
        switch self {
        case .peanut: .peanut
        case .treeNuts: .treeNut
        case .shellfish: .shellfish
        case .fish: .fish
        case .egg: .egg
        case .milk: .dairy
        case .wheat: .gluten
        case .soy: .soy
        case .sesame: .sesame
        }
    }
}

/// The tool service (#1724 `LioToolServices`) that reads the travel profile. The host adds it with
/// `.lioToolServices(LioToolServices().with(LioTravelProfileSource.device(...)))`; entries read it with
/// `context.services.get(LioTravelProfileSource.self)`.
public struct LioTravelProfileSource: Sendable {
    let read: @MainActor @Sendable (_ today: LioTripDay) -> LioTravelProfile

    init(read: @escaping @MainActor @Sendable (_ today: LioTripDay) -> LioTravelProfile) { self.read = read }

    /// The signed-in account's files: saved plans, trip home, Back to Hotel and show-card details, plus the
    /// nationality setting. A store that cannot be read (account changed, phone locked) counts as empty.
    public static func device(messageDirectory: URL, savedPlans: LioSavedPlans, tripHome: LioTripHomeStore,
                              defaults: UserDefaults = .standard,
                              isCurrent: @escaping @MainActor @Sendable () -> Bool) -> Self {
        let defaults = UncheckedDefaults(value: defaults)
        return Self { today in
            guard isCurrent() else { return LioTravelProfile() }
            let hotelStore = LioReturnHotelStore(
                directory: LioReturnHotelStore.storageDirectory(inMessageDirectory: messageDirectory), isCurrent: isCurrent)
            let detailsStore = LioShowCardDetailsStore(
                directory: LioShowCardDetailsStore.storageDirectory(inMessageDirectory: messageDirectory), isCurrent: isCurrent)
            return LioTravelProfile.aggregate(
                tripHome: try? tripHome.load(), plans: (try? savedPlans.load()) ?? [],
                nationality: defaults.value.string(forKey: LioArrivalTrip.nationalityStorageKey),
                hotel: (try? hotelStore.load()) ?? nil, showCard: try? detailsStore.load(), today: today)
        }
    }

    private struct UncheckedDefaults: @unchecked Sendable { let value: UserDefaults }
}

extension LioToolContext {
    /// The travel profile for prefilling a tool page, or an empty one when the host did not add the source.
    func travelProfile(now: Date = .now) -> (profile: LioTravelProfile, today: LioTripDay) {
        let today = LioTripDay(date: now)
        return (services.get(LioTravelProfileSource.self)?.read(today) ?? LioTravelProfile(), today)
    }
}
