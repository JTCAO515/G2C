import Foundation
import Testing
import CJMessageHTTP
@testable import CJLioUser

struct LioPlanSummaryTests {
    @Test(arguments: ["structured4_undated", "structured4_dated", "legacy_card2"])
    func aNative4TripCardBecomesADayByDayPlanWithoutInventedDetail(_ name: String) throws {
        let trip = try #require(try page(name).messages.compactMap(\.trip).first)
        let plan = LioPlanSummary(trip)
        let days: [LioCalendarTripCard.Day]
        let card: (id: String, version: Int64, title: String, calendar: LioCalendarTripCard.CalendarState?)
        switch trip {
        case .calendar(let value): days = value.days; card = (value.id, value.tripVersion, value.title, value.calendar)
        case .rich(let value): days = value.days; card = (value.id, value.tripVersion, value.title, value.calendar)
        }
        #expect(plan.tripID == card.id && plan.tripVersion == card.version && plan.title == card.title)
        if case .dated(let start)? = card.calendar {
            #expect(plan.startDate == start && !plan.undated)
        } else {
            #expect(plan.startDate == nil && plan.undated)
        }
        #expect(plan.days.map { $0.items.map(\.label) } == days.map { $0.items.map(\.label) })
        #expect(plan.stopCount == days.reduce(0) { $0 + $1.items.count })

        let itinerary = plan.itinerary
        #expect(itinerary.days.map(\.number) == plan.days.map(\.number))
        for (day, source) in zip(itinerary.days, plan.days) {
            #expect(day.theme.isEmpty && day.area.isEmpty && day.legs.isEmpty && day.date == source.date)
            #expect(day.stops.map(\.time) == source.items.map(\.startTime))
            for stop in day.stops {
                // A summary names a place; it does not confirm an address, coordinate or kind.
                #expect(stop.kind == .unspecified && stop.text.isEmpty && stop.note == nil && stop.tip == nil)
                #expect(!stop.place.matched && stop.place.driverAddress == nil && stop.place.mapPoint == nil)
            }
            #expect(day.mapNumbers.isEmpty)
        }
        #expect(itinerary.hotels.isEmpty && itinerary.lodgingArea.isEmpty)
    }

    @Test func unspecifiedKindHasNoLabel() {
        #expect(LioRichItinerary.Kind.unspecified.title(.english).isEmpty)
        #expect(LioRichItinerary.Kind.unspecified.title(.chinese).isEmpty)
        #expect(LioRichItinerary.Kind(rawValue: "unspecified") == .unspecified)
    }

    @Test func shareTextListsEachDayInTheChosenLanguage() {
        let plan = Self.plan(version: 1)
        #expect(plan.itinerary.shareText(.chinese) == """
        北京三日

        第 1 天 · 2026-12-01
        09:00 天安门广场
        故宫

        第 2 天
        08:00 长城
        """)
        #expect(plan.itinerary.shareText(.english).hasPrefix("北京三日\n\nDay 1 · 2026-12-01\n09:00 天安门广场"))
    }

    @Test @MainActor func savedPlansKeepOneNewestCopyPerTripInOneAccountFile() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: LioSavedPlans.storageDirectory(inMessageDirectory: directory), isCurrent: { true })
        #expect(try store.load().isEmpty)
        let first = Self.plan(version: 1)
        try store.save(first, at: Date(timeIntervalSince1970: 10))
        var other = Self.plan(version: 1, id: "trip/other:id")
        try store.save(other, at: Date(timeIntervalSince1970: 20))
        #expect(try store.load().map(\.tripID) == ["trip/other:id", "trip-1"])

        let newer = Self.plan(version: 2)
        try store.save(newer, at: Date(timeIntervalSince1970: 30))
        #expect(try store.load() == [newer, other])

        try store.remove("trip-1")
        try store.remove("trip-1")
        #expect(try store.load() == [other])
        other = Self.plan(version: 3, id: "trip/other:id")
        try store.save(other)
        #expect(try store.load() == [other])
        // Cleanup knows exactly one file in one folder.
        let folder = directory.appendingPathComponent(LioSavedPlans.directoryName, isDirectory: true)
        #expect(try FileManager.default.contentsOfDirectory(atPath: folder.path) == [LioSavedPlans.fileName])
    }

    @Test @MainActor func savedPlansKeepTheNewestFifty() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        for index in 0..<55 { try store.save(Self.plan(version: 1, id: "t\(index)"), at: Date(timeIntervalSince1970: Double(index))) }
        let ids = try store.load().map(\.tripID)
        #expect(ids.count == LioSavedPlans.maximumCount && ids.first == "t54" && ids.last == "t5")
    }

    @Test @MainActor func anotherAccountReadsAndWritesNothing() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        var current = true
        let store = LioSavedPlans(directory: directory, isCurrent: { current })
        let model = LioSavedPlansModel(store: store)
        let plan = Self.plan(version: 1)
        model.save(plan)
        #expect(model.isSaved(plan) && model.plans == [plan])
        current = false
        #expect(!model.available && model.plans.isEmpty && !model.isSaved(plan))
        #expect(throws: CancellationError.self) { try store.load() }
        #expect(throws: CancellationError.self) { try store.save(Self.plan(version: 2)) }
        model.remove(plan)
        current = true
        #expect(model.plans == [plan])
    }

    @Test @MainActor func aNewSessionForTheSameFolderSeesTheSavedPlans() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        var firstSession = true
        let earlier = LioSavedPlans(directory: directory, isCurrent: { firstSession })
        LioSavedPlansModel(store: earlier).save(Self.plan(version: 1))
        firstSession = false
        let later = LioSavedPlans(directory: directory, isCurrent: { true })
        #expect(earlier.id != later.id)
        #expect(LioSavedPlansModel(store: earlier).plans.isEmpty)
        #expect(LioSavedPlansModel(store: later).plans == [Self.plan(version: 1)])
    }

    @Test @MainActor func modelReportsSavedOnlyForTheSameVersion() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let model = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true }))
        let plan = Self.plan(version: 1)
        #expect(model.available && !model.isSaved(plan))
        model.save(plan)
        #expect(model.isSaved(plan) && !model.isSaved(Self.plan(version: 2)))
        #expect(LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true })).plans == [plan])
        model.remove(plan)
        #expect(model.plans.isEmpty)

        let unavailable = LioSavedPlansModel(store: nil)
        unavailable.save(plan)
        #expect(!unavailable.available && unavailable.plans.isEmpty)
    }

    static func plan(version: Int64, id: String = "trip-1") -> LioPlanSummary {
        LioPlanSummary(tripID: id, tripVersion: version, title: "北京三日", startDate: "2026-12-01", undated: false, days: [
            .init(number: 1, date: "2026-12-01", items: [
                .init(id: "a", label: "天安门广场", startTime: "09:00", endTime: "10:00", fixed: nil),
                .init(id: "b", label: "故宫", startTime: nil, endTime: nil, fixed: true)
            ]),
            .init(number: 2, date: nil, items: [.init(id: "c", label: "长城", startTime: "08:00", endTime: nil, fixed: nil)])
        ])
    }

    private func page(_ name: String) throws -> LioExplorationWire.Page {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let bytes = try Data(contentsOf: root.appendingPathComponent("contracts/message/lio-exploration-examples.4.json"))
        let fields = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let value = try #require(fields[name] as? [String: Any])
        return try LioExplorationWire.decodePage(JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]))
    }
}
