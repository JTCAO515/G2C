import Foundation
import PDFKit
import Testing
@testable import CJLioUser

/// #1723: a saved plan is one trip object (`LioRichItinerary` plus id, version and source) kept in
/// saved-plans.json v2; v1 files still open, and a popular route saved as a trip keeps its checked places.
@MainActor struct LioSavedTripStoreTests {
    private func folder() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("saved-trip-\(UUID().uuidString)", isDirectory: true)
    }

    @Test func aVersionOneFileStillOpensWithUnconfirmedPlaces() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let v1 = """
        {"version":1,"records":[
         {"savedAt":10,"plan":{"tripID":"trip-1","tripVersion":2,"title":"北京三日","startDate":"2026-12-01","undated":false,
          "days":[{"number":1,"date":"2026-12-01","items":[
            {"id":"a","label":"天安门广场","startTime":"09:00","endTime":"10:00","fixed":null},
            {"id":"b","label":"故宫","startTime":null,"endTime":null,"fixed":true}]}]}},
         {"savedAt":5,"plan":{"tripID":"trip-1","tripVersion":1,"title":"旧","startDate":null,"undated":true,"days":[]}}
        ]}
        """
        try Data(v1.utf8).write(to: directory.appendingPathComponent(LioSavedPlans.fileName))
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        let plans = try store.load()
        #expect(plans.count == 1, "one copy per trip, the highest version")
        let plan = try #require(plans.first)
        #expect(plan.tripID == "trip-1" && plan.tripVersion == 2 && plan.source == .chat && plan.title == "北京三日")
        #expect(plan.startDate == "2026-12-01" && !plan.undated)
        #expect(plan.days.map { $0.items.map(\.label) } == [["天安门广场", "故宫"]])
        let stops = plan.itinerary.days.flatMap(\.stops)
        #expect(stops.map(\.time) == ["09:00", nil] && stops.map(\.fixed) == [nil, true])
        #expect(stops.allSatisfy { !$0.place.matched && $0.place.driverAddress == nil && $0.place.mapPoint == nil })

        // The next write upgrades the file to v2 without losing the trip.
        try store.save(Self.otherPlan, at: Date())  // v1 dates are seconds since 2001, so this one is newer
        let object = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: directory
            .appendingPathComponent(LioSavedPlans.fileName))) as? [String: Any])
        #expect(object["version"] as? Int == 2)
        #expect(try store.load() == [Self.otherPlan, plan])
    }

    @Test func versionTwoKeepsTheWholeTripRoundTrip() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        let rich = LioPlanSummary(tripID: "trip-rich", tripVersion: 7, source: .chat, startDate: "2026-12-01",
                                  itinerary: LioRoadbookTests.itinerary(dates: ["2026-12-01", "2026-12-02"]))
        let template = LioPlanSummary(template: LioRoadbookTemplates.beijing(.english))
        try store.save(rich, at: Date(timeIntervalSince1970: 1))
        try store.save(template, at: Date(timeIntervalSince1970: 2))
        let reopened = try LioSavedPlans(directory: directory, isCurrent: { true }).load()
        #expect(reopened == [template, rich])
        #expect(reopened[1].itinerary == rich.itinerary)
        #expect(reopened[1].itinerary.days[0].legs == rich.itinerary.days[0].legs)
        #expect(reopened[0].itinerary.hotels == template.itinerary.hotels)
    }

    @Test func anOlderVersionNeverReplacesANewerOne() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        let newer = LioPlanSummaryTests.plan(version: 3)
        try store.save(newer, at: Date(timeIntervalSince1970: 1))
        try store.save(LioPlanSummaryTests.plan(version: 2), at: Date(timeIntervalSince1970: 2))
        #expect(try store.load() == [newer])
    }

    @Test func aDamagedRecordIsSkippedNotTheWholeList() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        try store.save(Self.otherPlan, at: Date(timeIntervalSince1970: 1))
        let file = directory.appendingPathComponent(LioSavedPlans.fileName)
        var object = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
        var records = try #require(object["records"] as? [Any])
        records.append(["savedAt": 2, "tripID": "bad"])
        object["records"] = records
        try JSONSerialization.data(withJSONObject: object).write(to: file)
        #expect(try store.load() == [Self.otherPlan])
    }

    /// #1723 acceptance with the Beijing route (chat places get addresses once S line sends them, PR-2).
    @Test func savedBeijingRouteShowsOnTheTripHomeMakesARoadbookAndCanTakeATaxi() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let model = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true }))
        let saved = try #require(model.saveTemplate(LioRoadbookTemplates.beijing(.chinese)))
        #expect(saved.tripID == "template:beijing-3d" && saved.tripVersion == 0 && saved.source == .template)
        let plans = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true })).plans
        #expect(plans == [saved])

        // Trip home: the saved route is the current trip and has a schedule.
        let list = LioTripChecklist(.init(now: Date(), plans: plans))
        #expect(list.plan == saved && list.hasTrip)
        #expect(!list.schedule.isEmpty && list.schedule[0].stops.first?.name == "天安门广场")

        // Roadbook: generated from the same object, with a PDF.
        let book = LioRoadbook(savedPlan: saved)
        #expect(book.id == "saved.template:beijing-3d.v0" && book.itinerary == saved.itinerary)
        #expect(book.itinerary.days.count == 3)
        let text = try #require(PDFDocument(data: LioRoadbookPDF.data(for: book, language: .chinese))?.string)
        #expect(text.contains("故宫博物院"))

        // Every place can be given to a taxi and to the driver.
        let places = saved.itinerary.days.flatMap(\.stops).map(\.place) + saved.itinerary.hotels.map(\.place)
        #expect(!places.isEmpty)
        for place in places {
            #expect(place.matched && place.driverAddress?.isEmpty == false && place.mapPoint != nil, "\(place.nameZH)")
            #expect(LioRoadbook.taxiDestination(place) != nil, "\(place.nameZH)")
        }
    }

    @Test func savingTheRouteAgainKeepsOneCopy() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        try store.saveTemplate(LioRoadbookTemplates.beijing(.chinese), at: Date(timeIntervalSince1970: 1))
        try store.saveTemplate(LioRoadbookTemplates.beijing(.english), at: Date(timeIntervalSince1970: 2))
        let plans = try store.load()
        #expect(plans.count == 1 && plans[0].title == LioRoadbookTemplates.beijing(.english).itinerary.title)
    }

    static let otherPlan = LioPlanSummaryTests.plan(version: 1, id: "trip-2")
}
