/// The Tools tab (formerly "插件"): one card per tool with an icon, a name and one sentence.
/// Tools whose service is not enabled for this build are left out rather than shown disabled.
enum LioToolCatalog {
    struct Availability: Equatable, Sendable {
        var taxi = false
        var currency = false
        var hotels = false
        var nearby = false
        /// #1515: `G2CRoadbookEnabled`, off unless the build says YES.
        var roadbook = false
        /// #1519: `G2CTransportEnabled`, off unless the build says YES.
        var transport = false
        /// #1595: `G2CArrivalModeEnabled`, off unless the build says YES.
        var arrival = false
        /// #1591: `G2CAttractionBookingEnabled`, off unless the build says YES.
        var attractionBooking = false
        /// #1606: `G2CMenuOrderEnabled` (the host injects the service only then), or Debug's `--lio-menu-preview`.
        var menuOrder = false
        /// #1574: `G2CShowCardEnabled`, off unless the build says YES; first card when shown (JT).
        var returnHotel = false
        /// #1724: tools whose entry is gated by `.build(infoKey:)`, on in this build.
        var enabled: Set<LioTool> = []
    }

    static func title(_ language: LioLanguage) -> String {
        language.text("Tools", "工具")
    }

    /// The tools shown as cards, in registry order (#1724).
    static func visible(_ availability: Availability, entries: [LioToolEntry] = LioToolRegistry.entries) -> [LioTool] {
        entries.filter { entry in
            switch entry.gate {
            case .always: true
            case .availability(let shown): shown(availability)
            case .build: availability.enabled.contains(entry.tool)
            }
        }.map(\.tool)
    }
}

extension LioToolCatalog {
    /// The saved plan Arrival Mode starts from: among plans whose first day is today or later, the one starting
    /// soonest (on a tie, the one saved most recently, since `plans` is newest first); with none, the most recently
    /// saved. Unlike the trip home's current plan, a trip already under way is skipped: Arrival Mode is about the
    /// first day.
    static func arrivalPlan(_ plans: [LioPlanSummary], today: LioArrivalDay) -> LioPlanSummary? {
        let upcoming = plans.compactMap { plan in plan.startDate.flatMap(LioArrivalDay.init).map { (plan, $0) } }
            .filter { $0.1 >= today }
            .min { $0.1 < $1.1 }?.0
        return upcoming ?? plans.first
    }
}
