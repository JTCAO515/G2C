import Foundation
import Testing
@testable import CJLioUser

/// #1741 (W3-4): arrival taxi reads "my hotel", taxi trip places come from the saved trip, ending a trip clears
/// Arrival Mode's ticks, the nationality is kept per account; #1689: account deletion removes sight reminders.
@MainActor struct LioTripFixes1741Tests {
    private func isolated() throws -> (UserDefaults, String) {
        let suite = "lio.1741." + UUID().uuidString
        return (try #require(UserDefaults(suiteName: suite)), suite)
    }

    private func place(_ name: String, matched: Bool, point: LioItinerary.Point?) -> LioRichItinerary.Place {
        .init(nameZH: name, nameEN: name + " EN", address: name + "路 1 号", matched: matched, point: point)
    }

    private func tripHotel(_ name: String) -> LioRichItinerary.Hotel {
        .init(id: name, place: place(name, matched: true, point: .init(latitude: 39.9, longitude: 116.4)), note: nil)
    }

    private let myHotel = LioStayHotel(
        place: LioTaxiPlace(nameZH: "我的酒店甲", nameEN: "My Hotel A", addressZH: "东城区甲路 8 号", addressEN: nil,
                            coordinate: .init(latitude: 39.91, longitude: 116.41, referenceSystem: .gcj02)),
        roomNumber: "1208", source: .hotelSearch)

    // MARK: 1. Arrival taxi step goes to "my hotel"

    @Test func arrivalTaxiGoesToMyHotelBeforeTheTripStay() {
        let destination = LioArrivalHotel.destination(myHotel: myHotel, tripHotels: [tripHotel("行程酒店")])
        #expect(destination?.source == .myHotel)
        #expect(destination?.nameZH == "我的酒店甲")
        #expect(destination?.addressZH == "东城区甲路 8 号")
    }

    @Test func withoutMyHotelTheArrivalTaxiStepIsUnchanged() {
        let hotels = [tripHotel("行程酒店")]
        #expect(LioArrivalHotel.destination(myHotel: nil, tripHotels: hotels) == LioArrivalHotel(hotels: hotels))
        #expect(LioArrivalHotel.destination(myHotel: nil, tripHotels: hotels)?.source == .trip)
        // No hotel anywhere: nil, so the page asks the traveller to type it, as before.
        #expect(LioArrivalHotel.destination(myHotel: nil, tripHotels: []) == nil)
    }

    // MARK: 2. Taxi trip places come from the saved trip, confirmed places only

    @Test func taxiTripPlacesAreTheSavedTripsConfirmedPlacesOnly() {
        let point = LioItinerary.Point(latitude: 39.92, longitude: 116.39)
        let stops = [
            LioRichItinerary.Stop(id: "a", kind: .sight, text: "", time: nil,
                                  place: place("故宫", matched: true, point: point), note: nil, tip: nil),
            // A chat suggestion: a name and even a point, but not matched, so never a destination.
            LioRichItinerary.Stop(id: "b", kind: .meal, text: "", time: nil,
                                  place: place("候选餐厅", matched: false, point: .init(latitude: 39.8, longitude: 116.3)),
                                  note: nil, tip: nil),
            // The same place again on another stop is offered once.
            LioRichItinerary.Stop(id: "c", kind: .sight, text: "", time: nil,
                                  place: place("故宫", matched: true, point: point), note: nil, tip: nil),
        ]
        let itinerary = LioRichItinerary(title: "北京", undated: true,
                                         days: [.init(number: 1, date: nil, theme: "", area: "", stops: stops, legs: [])],
                                         lodgingArea: "", hotels: [tripHotel("行程酒店")])
        let saved = LioPlanSummary(tripID: "t1", tripVersion: 1, source: .template, startDate: nil, itinerary: itinerary)
        // A chat card: names and times only, unmatched.
        let chat = LioPlanSummary(tripID: "t2", tripVersion: 1, title: "聊天", startDate: nil, undated: true,
                                  days: [.init(number: 1, date: nil, items: [.init(id: "x", label: "颐和园", startTime: nil,
                                                                                    endTime: nil, fixed: nil)])])

        let places = LioTaxiTripPlaces.confirmed(in: [saved, chat])
        #expect(places.map(\.nameZH) == ["故宫", "行程酒店"])
        #expect(places.first?.addressZH == "故宫路 1 号")
        #expect(places.allSatisfy { $0.coordinate.referenceSystem == .gcj02 })
        #expect(LioTaxiTripPlaces.confirmed(in: [chat]).isEmpty)
        #expect(LioTaxiTripPlaces.confirmed(in: []).isEmpty)
    }

    // MARK: 3. Ending the trip clears Arrival Mode's progress only

    @Test func endingTheTripClearsArrivalProgressOnly() throws {
        let (defaults, suite) = try isolated()
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set("entry,payment", forKey: LioArrivalProgress.storageKey)
        defaults.set("GB", forKey: LioNationalityStore.key(account: "A"))
        defaults.set("en", forKey: "cj.ui.language.v1")

        LioTripHomeArrivalRules.clearProgress(in: defaults)

        #expect(defaults.object(forKey: LioArrivalProgress.storageKey) == nil)
        #expect(LioTripHomeArrivalRules.checklist(stored: defaults.string(forKey: LioArrivalProgress.storageKey) ?? "").done.isEmpty)
        #expect(defaults.string(forKey: LioNationalityStore.key(account: "A")) == "GB")
        #expect(defaults.string(forKey: "cj.ui.language.v1") == "en")
        LioTripHomeArrivalRules.clearProgress(in: defaults)
        #expect(defaults.object(forKey: LioArrivalProgress.storageKey) == nil)
    }

    // MARK: 5. Nationality per account

    @Test func legacyNationalityMigratesOnceThenTheDeviceKeyIsGone() throws {
        let (defaults, suite) = try isolated()
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set("GB", forKey: LioNationalityStore.legacyKey)

        let store = LioNationalityStore(account: "A", defaults: defaults)
        #expect(store.value == "GB")
        #expect(defaults.object(forKey: LioNationalityStore.legacyKey) == nil)
        #expect(defaults.string(forKey: LioNationalityStore.key(account: "A")) == "GB")

        // A later account finds nothing to migrate.
        #expect(LioNationalityStore(account: "B", defaults: defaults).value == "")
        #expect(defaults.object(forKey: LioNationalityStore.key(account: "B")) == nil)
    }

    @Test func signedOutNeitherMigratesNorRemovesTheDeviceKey() throws {
        let (defaults, suite) = try isolated()
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set("GB", forKey: LioNationalityStore.legacyKey)
        let store = LioNationalityStore(account: nil, defaults: defaults)
        #expect(store.value == "GB")
        #expect(defaults.string(forKey: LioNationalityStore.legacyKey) == "GB")
        #expect(LioNationalityStore(account: "", defaults: defaults).key == LioNationalityStore.legacyKey)
    }

    @Test func anAccountWithItsOwnNationalityKeepsItWhenTheDeviceKeyIsMigrated() throws {
        let (defaults, suite) = try isolated()
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set("FR", forKey: LioNationalityStore.key(account: "A"))
        defaults.set("GB", forKey: LioNationalityStore.legacyKey)
        #expect(LioNationalityStore(account: "A", defaults: defaults).value == "FR")
        #expect(defaults.object(forKey: LioNationalityStore.legacyKey) == nil)
    }

    @Test func accountBCannotReadAccountAsNationality() throws {
        let (defaults, suite) = try isolated()
        defer { defaults.removePersistentDomain(forName: suite) }
        let a = LioNationalityStore(account: "A", defaults: defaults)
        a.value = "JP"
        let b = LioNationalityStore(account: "B", defaults: defaults)
        #expect(b.value == "")
        b.value = "KR"
        #expect(LioNationalityStore(account: "A", defaults: defaults).value == "JP")
        #expect(defaults.object(forKey: LioNationalityStore.legacyKey) == nil)
        // Clearing the choice removes the key rather than storing an empty string.
        b.value = ""
        #expect(defaults.object(forKey: LioNationalityStore.key(account: "B")) == nil)
    }

    @Test func accountDeletionClearsOnlyThatAccountsNationality() throws {
        let (defaults, suite) = try isolated()
        defer { defaults.removePersistentDomain(forName: suite) }
        LioNationalityStore(account: "A", defaults: defaults).value = "JP"
        LioNationalityStore(account: "B", defaults: defaults).value = "KR"
        #expect(!LioNationalityStore.isAbsent(account: "A", in: defaults))

        LioNationalityStore.erase(account: "A", in: defaults)

        #expect(LioNationalityStore.isAbsent(account: "A", in: defaults))
        #expect(LioNationalityStore(account: "A", defaults: defaults).value == "")
        #expect(LioNationalityStore(account: "B", defaults: defaults).value == "KR")
        LioNationalityStore.erase(account: "A", in: defaults)
        #expect(LioNationalityStore.isAbsent(account: "A", in: defaults))
    }

    @Test func switchingAccountsKeepsEachNationality() throws {
        let (defaults, suite) = try isolated()
        defer { defaults.removePersistentDomain(forName: suite) }
        LioNationalityStore(account: "A", defaults: defaults).value = "JP"
        // Switching is a new store for the other account; nothing is erased.
        _ = LioNationalityStore(account: "B", defaults: defaults)
        #expect(LioNationalityStore(account: "A", defaults: defaults).value == "JP")
    }

    @Test func noViewReadsTheDeviceWideNationalityKeyDirectly() throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 { root.deleteLastPathComponent() }
        let sources = root.appendingPathComponent("Sources/CJLioUser")
        for name in try FileManager.default.contentsOfDirectory(atPath: sources.path) where name.hasSuffix(".swift") {
            let text = try String(contentsOf: sources.appendingPathComponent(name), encoding: .utf8)
            #expect(!text.contains("@AppStorage(\"lio.local-support.nationality\")"), "\(name)")
            #expect(!text.contains("@AppStorage(LioArrivalTrip.nationalityStorageKey)"), "\(name)")
            #expect(!text.contains("LioTripHomeNationality"), "\(name)")
        }
    }
}

// MARK: 4. #1689: account deletion removes the sight booking reminders, waiting and shown

final class FakeReminderNotifications: LioReminderNotifications, @unchecked Sendable {
    private let lock = NSLock()
    private var _pending: Set<String>
    private var _delivered: Set<String>
    private var _removals: [String] = []
    init(pending: Set<String>, delivered: Set<String> = []) { _pending = pending; _delivered = delivered }
    var pending: Set<String> { lock.withLock { _pending } }
    var delivered: Set<String> { lock.withLock { _delivered } }
    var removals: [String] { lock.withLock { _removals } }
    func pendingIDs() async -> Set<String> { pending }
    func deliveredIDs() async -> Set<String> { delivered }
    func removePending(_ ids: [String]) { lock.withLock { _removals += ids; _pending.subtract(ids) } }
    func removeDelivered(_ ids: [String]) { lock.withLock { _removals += ids; _delivered.subtract(ids) } }
}

struct LioAttractionReminderPurgeTests {
    private let sight = "g2c.attraction.forbidden-city.2026-12-01"
    private let otherSight = "g2c.attraction.summer-palace.2026-12-02"
    private let shown = "g2c.attraction.great-wall.2026-11-20"
    private let other = ["g2c.other.reminder", "medication.9am", "g2c.attractionx.1"]

    /// L0: after deletion neither the pending nor the delivered list has a sight booking reminder; the check reads
    /// both lists again.
    @Test func afterDeletionNoSightReminderIsPendingOrShown() async throws {
        let center = FakeReminderNotifications(pending: Set([sight, otherSight] + other), delivered: Set([shown, "medication.8am"]))
        #expect(throws: LioAttractionReminderPurge.Failure.stillPresent) {
            try LioAttractionReminderPurge.requireAbsent(LioReminderSnapshot(pending: [], delivered: [shown]))
        }
        try await LioAttractionReminderPurge.purge(in: center)
        let after = await LioAttractionReminderPurge.read(center)
        #expect(after.residue.isEmpty)
        try LioAttractionReminderPurge.requireAbsent(after)
        // Re-entrant: a resumed cleanup removes nothing more and still verifies.
        try await LioAttractionReminderPurge.purge(in: center)
        #expect(center.removals.sorted() == [shown, sight, otherSight].sorted())
    }

    /// The synchronous steps work from a snapshot read beforehand; erasing then checking the snapshot without the
    /// removed reminders passes, and the snapshot is what a fresh read finds.
    @Test func theSnapshotStepsMatchAFreshRead() async throws {
        let center = FakeReminderNotifications(pending: [sight, "medication.9am"], delivered: [shown])
        let before = await LioAttractionReminderPurge.read(center)
        try LioAttractionReminderPurge.erase(before, in: center)
        try LioAttractionReminderPurge.requireAbsent(before.withoutSightReminders)
        #expect(await LioAttractionReminderPurge.read(center) == before.withoutSightReminders)
    }

    /// L0: only `account_cleanup` clears; switching accounts or a session found invalid does not.
    @Test func onlyAccountDeletionClearsReminders() {
        #expect(LioAttractionReminderPurge.applies(to: "account_cleanup"))
        #expect(!LioAttractionReminderPurge.applies(to: "session_invalid"))
        #expect(!LioAttractionReminderPurge.applies(to: "offline_expired"))
        #expect(!LioAttractionReminderPurge.applies(to: ""))
    }

    /// L0: notifications with other prefixes stay, waiting or shown.
    @Test func otherNotificationsAreUntouched() async throws {
        let center = FakeReminderNotifications(pending: Set([sight] + other), delivered: Set([shown] + other))
        try await LioAttractionReminderPurge.purge(in: center)
        #expect(center.pending == Set(other))
        #expect(center.delivered == Set(other))
        #expect(Set(center.removals) == [sight, shown])
    }

    @Test func theIdentifierPrefixIsTheSchedulersOwn() {
        #expect(LioAttractionReminderPurge.prefix == LioAttractionReminderItem.prefix)
        #expect(LioAttractionReminderItem(id: sight) != nil)
    }

    /// No snapshot read: both steps fail (recorded as unknown) instead of passing.
    @Test func withoutASnapshotTheStepFailsInsteadOfPassing() {
        let center = FakeReminderNotifications(pending: [sight])
        #expect(throws: LioAttractionReminderPurge.Failure.unavailable) { try LioAttractionReminderPurge.erase(nil, in: center) }
        #expect(throws: LioAttractionReminderPurge.Failure.unavailable) { try LioAttractionReminderPurge.requireAbsent(nil) }
        #expect(center.pending == [sight])
    }
}
