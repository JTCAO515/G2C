#if os(iOS)
import SwiftUI

/// What the trip home asks of Arrival Mode, as closures, so the home compiles without Arrival Mode's types.
/// `LioTripHomeArrival.fromBuild()` (in the Arrival Mode adapter) fills it when `G2CArrivalModeEnabled` is YES.
/// Everything is read on this phone; the only writes are ticking one of Arrival Mode's own checklist steps and
/// clearing those ticks when the trip ends.
@MainActor struct LioTripHomeArrival {
    /// The sourced entry decision for this traveller, or `.missingDetails`.
    var entry: @MainActor (_ profile: LioTripProfile?, _ nationality: String, _ today: Date) -> LioTripEntryStatus
    var checklist: @MainActor () -> LioTripArrivalChecklist
    var setStep: @MainActor (_ step: String, _ done: Bool) -> Void
    /// Arrival Mode's pages, opened from "Go".
    var entryPage: @MainActor (_ profile: LioTripProfile?) -> AnyView
    var internetPage: @MainActor () -> AnyView
    var checklistPage: @MainActor (_ profile: LioTripProfile?) -> AnyView
    /// Ending the trip (#1741) clears Arrival Mode's ticked steps, and nothing else of Arrival Mode.
    var clearProgress: @MainActor () -> Void = {}
}

extension LioTripHomeArrival {
    /// Arrival Mode's checklist page reading Back to Hotel's "my hotel" for its taxi step (#1741), read only.
    func readingMyHotel(from store: LioReturnHotelStore?) -> Self {
        guard let store else { return self }
        var arrival = self
        let page = checklistPage
        arrival.checklistPage = { profile in AnyView(page(profile).environment(\.lioReturnHotelStore, store)) }
        return arrival
    }
}

/// The other tools the trip home links to, each present only when its own switch is on in this build.
@MainActor struct LioTripHomeTools {
    var arrival: LioTripHomeArrival?
    /// Back to Hotel's store (`G2CShowCardEnabled`), read only: the same file its own page and the Tools tab use,
    /// built with its own path functions from the account's message folder (agreed with the Back to Hotel line).
    var hotelStore: LioReturnHotelStore?
    /// What the traveller fills in on the show cards (name, allergies …), kept by Back to Hotel's own store.
    var detailsStore: LioShowCardDetailsStore?
    var showCards = false
    /// Attraction booking (`G2CAttractionBookingEnabled`): its rules and the system's local reminders.
    var reminders: LioAttractionReminderScheduler?
    /// Roadbooks (`G2CRoadbookEnabled`): offline copies in the account folder.
    var roadbookStore: LioRoadbookStore?
    var roadbooks = false
    /// Business trips (`G2CTripBusinessEnabled`, #1765): the bundled entries and steps. Nil keeps the checklist and
    /// the trip settings exactly as they were.
    var business: LioTripBusinessGuide?

    /// The tools as this build has them, for the signed-in account's message folder.
    static func fromBuild(messageDirectory: URL?, isCurrent: @escaping @MainActor () -> Bool,
                          arrival: LioTripHomeArrival?, reminderScope: LioAttractionReminderScope) -> Self {
        let info = { (key: String) in Bundle.main.object(forInfoDictionaryKey: key) }
        // Back to Hotel's own switch (#1632): `G2CShowCardEnabled`, or its Debug preview argument.
        let showCards = LioReturnHotelTools.shownInTools
        let roadbooks = LioRoadbookFeature.enabled(infoValue: info("G2CRoadbookEnabled"))
        let hotelStore = showCards ? messageDirectory.map {
            LioReturnHotelStore(directory: LioReturnHotelStore.storageDirectory(inMessageDirectory: $0), isCurrent: isCurrent)
        } : nil
        return Self(
            arrival: arrival.map { $0.readingMyHotel(from: hotelStore) },
            hotelStore: hotelStore,
            detailsStore: showCards ? messageDirectory.map {
                LioShowCardDetailsStore(directory: LioShowCardDetailsStore.storageDirectory(inMessageDirectory: $0), isCurrent: isCurrent)
            } : nil,
            showCards: showCards,
            reminders: LioAttractionBookingFeature.enabled(infoValue: info(LioAttractionBookingFeature.infoKey))
                ? LioAttractionReminderScheduler(center: LioSystemReminderCenter(), scope: reminderScope) : nil,
            roadbookStore: roadbooks ? messageDirectory.map {
                LioRoadbookStore(directory: LioAccountFolders.roadbooks(inMessageDirectory: $0), isCurrent: isCurrent)
            } : nil,
            roadbooks: roadbooks,
            business: LioTripBusinessFeature.enabled(infoValue: info(LioTripBusinessFeature.infoKey)) ? .bundled() : nil)
    }

    /// A damaged hotel file reads as no hotel, as on Back to Hotel itself.
    func savedHotel() -> LioStayHotel? { (try? hotelStore?.load()) ?? nil }
}

/// Opens the tool page that does a task ("Go"). Pages are the tools' own; nothing here edits their data.
struct LioTripTaskPage: View {
    let task: LioTripTask
    let language: LioLanguage
    let profile: LioTripProfile?
    let tools: LioTripHomeTools
    let now: Date
    @Environment(\.lioTaxiEntry) private var taxiEntry

    var body: some View {
        switch task.kind {
        case .entry, .arrivalCard:
            if let arrival = tools.arrival { arrival.entryPage(profile) }
        case .payment:
            LioPaymentGuideView(language: language)
        case .internet:
            if let arrival = tools.arrival { arrival.internetPage() }
        case .hotel:
            LioReturnHotelView(language: language, store: tools.hotelStore, detailsStore: tools.detailsStore, taxiEntry: taxiEntry)
        case .booking(let id, let visit, _, _):
            if let rule = LioAttractionBookingRule.all.first(where: { $0.id == id }), let reminders = tools.reminders {
                LioAttractionBookingDetail(rule: rule, language: language, reminders: reminders, today: now,
                                           visit: visit?.start(in: LioTripChecklist.beijing))
            }
        case .medicalCard:
            LioLocalSupportView(language: language)
        case .landing:
            if let arrival = tools.arrival { arrival.checklistPage(profile) }
        case .checkIn:
            LioShowCardsView(language: language, hotel: tools.savedHotel(), detailsStore: tools.detailsStore)
        case .business:
            // Business items open the organizer's page or a tool through the router, never a page here.
            EmptyView()
        }
    }
}
#endif
