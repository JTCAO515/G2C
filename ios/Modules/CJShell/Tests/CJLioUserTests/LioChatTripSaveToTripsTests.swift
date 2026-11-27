import Foundation
import Testing
import CJMessageHTTP
@testable import CJTripClient
@testable import CJLioUser

/// #1976: a chat plan saved with "Save to Trips" is on the Trips page afterwards, day by day. Each test goes from
/// the card the server sent (or the trip it names), through the Save button's model and the saved-plans file (a second
/// model reads it back, as after a restart), to what the trip home and the day-by-day page show.
@MainActor struct LioChatTripSaveToTripsTests {
    static let trace = "00000000-0000-4000-8000-000000000001"
    private static let utc = TimeZone(identifier: "UTC")!

    private func folder() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("save-to-trips-\(UUID().uuidString)", isDirectory: true)
    }

    // MARK: Fixtures

    private func card(_ name: String) throws -> LioExplorationWire.Trip {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let bytes = try Data(contentsOf: root.appendingPathComponent("contracts/message/lio-exploration-examples.4.json"))
        let fields = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let value = try #require(fields[name] as? [String: Any])
        let page = try LioExplorationWire.decodePage(JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]))
        return try #require(page.messages.compactMap(\.trip).first)
    }

    private func content(_ name: String) throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let data = try Data(contentsOf: root.appendingPathComponent("contracts/trip/structured-examples.4.json"))
        let file = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let cases = try #require(file["cases"] as? [String: [String: Any]])
        return try #require(cases[name]?["content"] as? [String: Any])
    }

    private func canonical(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }

    /// The server's `trip-structured` answer for this content, read the way the App reads it.
    private func record(_ content: [String: Any], version: Int64) throws -> RichStructuredTripRecord {
        let hash = try RichStructuredTripDocument.decode(canonical(content)).contentSHA256
        let trip: [String: Any] = ["trip_id": "trip-1", "version": version, "content_sha256": hash, "content": content]
        let body = try canonical(["version": "TRIP-structured-read.3", "request_id": Self.trace, "trip": trip])
        return try #require(try RichStructuredTripReadV3.detail(body, requestID: Self.trace))
    }

    /// The summary a LIO-trip-card.3 for this content gives: names (the item text) and start times only.
    private func summary(_ content: [String: Any], version: Int64) throws -> LioPlanSummary {
        let items = try #require(content["items"] as? [[String: Any]])
        let days = try #require(content["days"] as? [[String: Any]])
        let calendar = try #require(content["calendar"] as? [String: Any])
        let start = calendar["start_date"] as? String
        return LioPlanSummary(tripID: "trip-1", tripVersion: version, title: try #require(content["title"] as? String),
                              startDate: start, undated: start == nil, days: try days.map { day in
            let index = try #require(day["day_index"] as? Int)
            return LioPlanSummary.Day(number: index, date: day["date"] as? String, items: try items.compactMap { item in
                let schedule = try #require(item["schedule"] as? [String: [String: Any]])
                guard schedule["start"]?["day_index"] as? Int == index else { return nil }
                let time = (schedule["start"]?["time"] as? [String: Any])?["value"] as? String
                return LioPlanSummary.Item(id: try #require(item["id"] as? String), label: try #require(item["text"] as? String),
                                           startTime: time, endTime: nil, fixed: false)
            })
        })
    }

    private func reference(_ content: [String: Any], version: Int64) throws -> LioChatTripReference {
        LioChatTripReference(tripID: "trip-1", tripVersion: version,
                             contentSHA256: try RichStructuredTripDocument.decode(canonical(content)).contentSHA256)
    }

    /// Saves as the chat's Save button does, then opens the file again as another launch would.
    private func saveAndReopen(_ plan: LioPlanSummary, directory: URL) throws -> [LioPlanSummary] {
        let model = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true }))
        #expect(model.writable)
        model.save(plan)
        #expect(model.isSaved(plan) && model.hasSavedCopy(of: plan) && !model.saveFailed(plan))
        return LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true })).plans
    }

    /// The trip home with no dates entered yet, three days before the plan starts (or any day for an undated plan).
    private func tripHome(_ plans: [LioPlanSummary]) -> LioTripChecklist {
        let first = plans.first?.startDate.flatMap(LioTripDay.init) ?? LioTripDay("2026-11-27")!
        let now = first.start(in: Self.utc).addingTimeInterval(-86_400 * 3)
        return LioTripChecklist(.init(now: now, timeZone: Self.utc, plans: plans))
    }

    // MARK: Save, read back, by day

    @Test(arguments: ["structured4_undated", "structured4_dated", "legacy_card2"])
    func aSavedChatCardIsTheCurrentTripWithEveryDayAfterReopening(_ name: String) throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let plan = LioPlanSummary(try card(name))
        let plans = try saveAndReopen(plan, directory: directory)
        #expect(plans == [plan])

        let list = tripHome(plans)
        #expect(list.hasTrip && list.plan == plan)
        #expect(!list.schedule.isEmpty)
        let saved = try #require(list.plan)
        #expect(saved.days.map(\.number) == plan.days.map(\.number))
        #expect(saved.stopCount == plan.stopCount && saved.stopCount > 0)
        #expect(list.schedule.count + list.moreDays == saved.days.count)
        // The day-by-day page reads the same itinerary: every day, with the card's stops in order.
        #expect(saved.itinerary.days.map { $0.stops.map(\.id) } == plan.days.map { $0.items.map(\.id) })
    }

    @Test func aConfirmedReadKeepsEveryDayAndStopOnTheTripHomeInBothLanguages() throws {
        let content = try content("matched")
        let reference = try reference(content, version: 3)
        let card = try summary(content, version: 3)
        let result = LioChatTripPlaces.reconcile(reference, summary: card, record: try record(content, version: 3))
        #expect(result.outcome == .confirmed)

        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let plans = try saveAndReopen(result.plan, directory: directory)
        let list = tripHome(plans)
        let plan = try #require(list.plan)
        #expect(plan.days.map(\.number) == card.days.map(\.number))
        #expect(plan.days.map { $0.items.map(\.id) } == card.days.map { $0.items.map(\.id) })
        // The trip home names the checked place in the traveller's language; the card only had the Chinese item text.
        let first = try #require(list.schedule.first?.stops.first)
        #expect(first.name(.chinese) == "演示地点1" && first.name(.english) == "Demonstration stop 1")
        // An unconfirmed place keeps its names too, so the English home is never empty for it.
        let unconfirmed = try #require(plan.itinerary.days.flatMap(\.stops).first { !$0.place.matched })
        #expect(unconfirmed.place.nameZH.hasPrefix("演示地点") && unconfirmed.place.nameEN.hasPrefix("Demonstration stop"))
    }

    @Test func aNewerVersionShowsItsDaysAndDatesAfterReopening() throws {
        let card = try content("matched"), newer = try content("dated")
        let result = LioChatTripPlaces.reconcile(try reference(card, version: 3), summary: try summary(card, version: 3),
                                                 record: try record(newer, version: 4))
        #expect(result.outcome == .replaced)
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let plans = try saveAndReopen(result.plan, directory: directory)
        let plan = try #require(plans.first)
        #expect(plan.tripVersion == 4 && plan.startDate == "2026-12-01")
        #expect(plan.days.map(\.number) == [1, 2] && plan.days.map(\.date) == ["2026-12-01", "2026-12-02"])
        let list = tripHome(plans)
        #expect(list.plan == plan && list.schedule.map(\.number) == [1, 2])
        #expect(list.schedule.map { $0.date?.description } == ["2026-12-01", "2026-12-02"])
    }

    // MARK: A stop is never dropped

    @Test func aTripWithAStopOnADayItDoesNotListIsNotSavedWithoutThatStop() throws {
        let content = try content("dated")
        let reference = try reference(content, version: 3)
        let card = try summary(content, version: 3)
        var newer = try record(content, version: 4)
        guard case .rich(let document) = newer.content else { Issue.record("structured.4 expected"); return }
        // The last day is gone from the list but its stops are still in the content.
        let cut = RichStructuredTripDocument(title: document.title, calendar: document.calendar,
                                             days: Array(document.days.dropLast()), items: document.items,
                                             sources: document.sources, dateChecks: document.dateChecks, legs: document.legs,
                                             lodging: document.lodging, originalUTF8: document.originalUTF8)
        #expect(throws: LioChatTripMappingFailure.self) { try LioPlanSummary(chatTripID: "trip-1", version: 4, document: cut) }
        newer = RichStructuredTripRecord(tripID: "trip-1", version: 4, content: .rich(cut))
        // The card's own summary has every stop, so that is what is saved.
        let result = LioChatTripPlaces.reconcile(reference, summary: card, record: newer)
        #expect(result.outcome == .failed(.invalid) && result.plan == card)
        #expect(result.plan.stopCount == document.items.count)
    }

    // MARK: Unconfirmed places

    @Test func anUnmatchedPlaceIsMarkedOnlyWhenThePlacesWereRead() throws {
        // Places read off (the default build): a summary's places are names, none is marked.
        let plan = LioPlanSummary(try card("structured4_undated"))
        let stop = try #require(plan.itinerary.days.first?.stops.first)
        #expect(!stop.place.matched)
        #expect(stop.unconfirmedNote(.english, placesRead: false) == nil && stop.unconfirmedNote(.chinese, placesRead: false) == nil)

        // Places read on: the unmatched one is marked in both languages, the matched ones are not.
        #expect(stop.unconfirmedNote(.english, placesRead: true) == "Place not confirmed")
        #expect(stop.unconfirmedNote(.chinese, placesRead: true) == "地点未确认")
        let content = try content("matched")
        let confirmed = LioChatTripPlaces.reconcile(try reference(content, version: 3), summary: try summary(content, version: 3),
                                                    record: try record(content, version: 3)).plan
        let stops = confirmed.itinerary.days.flatMap(\.stops)
        #expect(stops.contains { !$0.place.matched } && stops.contains { $0.place.matched })
        for stop in stops {
            let marked = stop.unconfirmedNote(.chinese, placesRead: true) != nil
            #expect(marked == !stop.place.matched && (stop.unconfirmedNote(.english, placesRead: true) != nil) == marked)
            #expect(stop.unconfirmedNote(.english, placesRead: false) == nil)
        }
        // A popular route's places are all checked.
        let template = LioPlanSummary(template: LioRoadbookTemplates.beijing(.english))
        #expect(template.itinerary.days.flatMap(\.stops).allSatisfy { $0.unconfirmedNote(.english, placesRead: true) == nil })
    }

    @Test func aDegradedTripWithoutADateOrTimesStillShowsEveryDayAndStop() throws {
        // What a degraded save can leave out: the start date, every start time and every checked place.
        let plan = LioPlanSummary(tripID: "trip-degraded", tripVersion: 1, title: "北京三日", startDate: nil, undated: true, days: [
            .init(number: 1, date: nil, items: [.init(id: "a", label: "故宫", startTime: nil, endTime: nil, fixed: nil)]),
            .init(number: 2, date: nil, items: [.init(id: "b", label: "长城", startTime: nil, endTime: nil, fixed: nil)]),
            .init(number: 3, date: nil, items: [.init(id: "c", label: "天坛", startTime: nil, endTime: nil, fixed: nil)]),
        ])
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let plans = try saveAndReopen(plan, directory: directory)
        #expect(plans == [plan])
        let list = tripHome(plans)
        #expect(list.hasTrip && list.arrival == nil && list.phase == .beforeTrip(daysToGo: nil))
        #expect(list.schedule.map(\.number) == [1, 2] && list.moreDays == 1)
        #expect(list.schedule.flatMap(\.stops).map(\.time) == [nil, nil])
        let stops = try #require(list.plan).itinerary.days.flatMap(\.stops)
        #expect(stops.map { $0.place.nameZH } == ["故宫", "长城", "天坛"])
        #expect(stops.allSatisfy { $0.unconfirmedNote(.english, placesRead: true) == "Place not confirmed" })
    }

    // MARK: A save that did not reach the phone

    @Test func aFailedSaveIsReportedAndNothingIsShownAsSaved() throws {
        let directory = folder()
        defer {
            try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
            try? FileManager.default.removeItem(at: directory)
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let model = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true }))
        let plan = LioPlanSummaryTests.plan(version: 1)
        // A folder that cannot be written: the atomic write cannot create its temporary file.
        try FileManager.default.setAttributes([.posixPermissions: 0o500], ofItemAtPath: directory.path)
        model.save(plan)
        #expect(model.saveFailed(plan) && !model.isSaved(plan) && !model.hasSavedCopy(of: plan) && model.plans.isEmpty)

        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
        model.save(plan)
        #expect(!model.saveFailed(plan) && model.isSaved(plan))
    }

    @Test func aFailedSaveThroughThePlacesReadIsReportedToo() async throws {
        // The Save button's path with places read on: the read finds nothing (`trip: null`), the summary is saved.
        let directory = folder()
        defer {
            try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
            try? FileManager.default.removeItem(at: directory)
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let model = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true }))
        let content = try content("matched")
        let card = try summary(content, version: 3)
        let body = try canonical(["version": "TRIP-structured-read.3", "request_id": Self.trace, "trip": NSNull()])
        let places = LioChatTripPlaces(enabled: true, read: { _ in .init(status: 200, requestID: Self.trace, bytes: body) })
        try FileManager.default.setAttributes([.posixPermissions: 0o500], ofItemAtPath: directory.path)
        let outcome = await model.save(card, reference: try reference(content, version: 3), places: places)
        #expect(outcome == .missing && model.saveFailed(card) && !model.hasSavedCopy(of: card) && model.savingTripIDs.isEmpty)

        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
        _ = await model.save(card, reference: try reference(content, version: 3), places: places)
        #expect(!model.saveFailed(card) && model.hasSavedCopy(of: card))
    }
}
