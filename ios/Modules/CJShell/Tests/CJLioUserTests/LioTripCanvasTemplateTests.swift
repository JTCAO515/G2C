import Foundation
import Testing
@testable import CJLioUser

/// #1997 (T-4): a popular route used as my trip becomes the trip canvas; its places are looked up in the places library.
@MainActor struct LioTripCanvasTemplateTests {
    // MARK: Fixtures

    /// A library that knows a few places by name. It answers only inside the cities it was given for a name, so the
    /// city the canvas asks with is checked too. Every question it was asked is recorded.
    final class FakeLookup: LioPlaceLookup, @unchecked Sendable {
        struct Entry { let id: String; let city: String; let coordinate: LioTripCanvas.Coordinate? }
        private let lock = NSLock()
        private let entries: [String: Entry]
        private var asked: [String] = []
        init(_ entries: [String: Entry]) { self.entries = entries }
        var questions: [String] { lock.withLock { asked } }

        func match(name: String, city: String?) -> LioPlaceMatch? {
            lock.withLock { asked.append("\(name)@\(city ?? "-")") }
            guard let entry = entries[name.lowercased()], city == nil || city == entry.city else { return nil }
            return LioPlaceMatch(placeID: entry.id, coordinate: entry.coordinate)
        }
    }

    private static let beijingLibrary = FakeLookup([
        "故宫博物院": .init(id: "pl_bj_gugong", city: "beijing", coordinate: .init(latitude: 39.9, longitude: 116.4)),
        "tian'anmen square": .init(id: "pl_bj_tiananmen", city: "beijing", coordinate: nil),
        "外滩": .init(id: "pl_sh_waitan", city: "shanghai", coordinate: nil),
    ])

    private func folder() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("trip-canvas-template-" + UUID().uuidString, isDirectory: true)
    }

    private func store(_ directory: URL, current: @escaping @MainActor () -> Bool = { true }) -> LioTripCanvasStore {
        LioTripCanvasStore(directory: directory, isCurrent: current)
    }

    private static func roadbook(days: [LioRichItinerary.Day], id: String = "template.beijing-3d", city: String = "北京",
                                 cityEN: String = "Beijing") -> LioRoadbook {
        LioRoadbook(id: id, source: .template, city: .init(nameZH: city, nameEN: cityEN), createdAt: Date(timeIntervalSince1970: 0),
                    itinerary: LioRichItinerary(title: "测试路线", undated: true, days: days, lodgingArea: "", hotels: []))
    }

    private static func stop(_ id: String, _ zh: String, _ en: String, point: LioItinerary.Point? = nil,
                             time: String? = nil) -> LioRichItinerary.Stop {
        .init(id: id, kind: .sight, text: "", time: time,
              place: .init(nameZH: zh, nameEN: en, address: point == nil ? nil : "地址", matched: point != nil, point: point),
              note: nil, tip: nil)
    }

    private static func day(_ number: Int, _ stops: [LioRichItinerary.Stop]) -> LioRichItinerary.Day {
        .init(number: number, date: nil, theme: "", area: "", stops: stops, legs: [])
    }

    // MARK: Converting a route

    @Test func theBeijingRouteBecomesACanvasOfTheTravellersOwnPoints() throws {
        let book = LioRoadbookTemplates.beijing(.chinese)
        let canvas = LioTripCanvas(template: book, lookup: LioNoPlaceLookup())
        #expect(canvas.tripID == "template:beijing-3d" && canvas.title == book.itinerary.title)
        #expect(canvas.source == .template && canvas.sourceVersion == 0 && canvas.undated && canvas.startDate == nil)
        #expect(canvas.segments.count == 1 && canvas.days.count == 3 && canvas.wishlist.isEmpty && canvas.isValid)
        // The days and the order of their points are the route's.
        #expect(canvas.days.map { $0.points.map(\.id) } == book.itinerary.days.map { $0.stops.map(\.id) })
        #expect(canvas.days.map(\.points.count) == [4, 2, 4] && canvas.pointCount == 10)
        #expect(canvas.days.map(\.id) == ["day-1", "day-2", "day-3"])
        #expect(canvas.days[0].theme == "皇城中轴" && canvas.days[0].area == "东城区")
        // Every point is the traveller's (they chose the route), whatever the lookup says.
        #expect(canvas.days.flatMap(\.points).allSatisfy { $0.origin == .user })
        #expect(canvas.hasUserEdits)
        let palace = try #require(canvas.point("bj-002"))
        #expect(palace.nameZH == "故宫博物院" && palace.nameEN == "Palace Museum" && palace.time == "09:45" && palace.kind == .sight)
        #expect(palace.address == "景山前街4号" && palace.coordinate == .init(latitude: 39.917839, longitude: 116.397029))
        #expect(palace.placeID == nil)
        // Every place of the route was checked, so every point has its coordinate.
        #expect(canvas.days.flatMap(\.points).allSatisfy { $0.coordinate != nil })
        // Dated nowhere, and no estimated travel between stops.
        #expect(canvas.legs.isEmpty)
    }

    @Test func theEnglishShanghaiRouteKeepsBothNames() throws {
        let canvas = LioTripCanvas(template: LioRoadbookTemplates.shanghai(.english), lookup: LioNoPlaceLookup())
        #expect(canvas.tripID == "template:shanghai-2d" && canvas.days.count == 2 && canvas.days.map(\.points.count) == [4, 4])
        let bund = try #require(canvas.point("sh-004"))
        #expect(bund.nameZH == "外滩" && bund.nameEN == "The Bund" && bund.name(.english) == "The Bund" && bund.origin == .user)
    }

    @Test func aRouteWithNoDaysIsAnEmptyCanvasThatWorks() throws {
        var canvas = LioTripCanvas(template: Self.roadbook(days: []), lookup: Self.beijingLibrary)
        #expect(canvas.isEmpty && canvas.days.isEmpty && canvas.segments.count == 1 && canvas.isValid && !canvas.hasUserEdits)
        #expect(canvas.tripID == "template:beijing-3d")
        let added = canvas.addDay()
        #expect(added == "day-1" && canvas.days.count == 1)
    }

    @Test func aRouteWithADayOfNoStopsKeepsTheDay() {
        let canvas = LioTripCanvas(template: Self.roadbook(days: [Self.day(1, []), Self.day(2, [Self.stop("a", "故宫博物院", "Palace")])]),
                                   lookup: LioNoPlaceLookup())
        #expect(canvas.days.count == 2 && canvas.days[0].points.isEmpty && canvas.days[1].points.map(\.id) == ["a"])
    }

    @Test func aStopListedTwiceKeepsBothWithDistinctIds() {
        let book = Self.roadbook(days: [
            Self.day(1, [Self.stop("a", "故宫博物院", "Palace Museum"), Self.stop("a", "故宫博物院", "Palace Museum")]),
            Self.day(2, [Self.stop("a", "故宫博物院", "Palace Museum")]),
        ])
        let canvas = LioTripCanvas(template: book, lookup: Self.beijingLibrary)
        let ids = canvas.days.flatMap(\.points).map(\.id)
        #expect(ids.count == 3 && Set(ids).count == 3 && ids[0] == "a" && canvas.isValid)
        // The same place on three days is the same library place each time.
        #expect(canvas.days.flatMap(\.points).allSatisfy { $0.placeID == "pl_bj_gugong" })
    }

    @Test func aLongRouteStopsAtTheCanvasLimits() {
        let stops = (1...50).map { Self.stop("s\($0)", "地点\($0)", "Place \($0)") }
        let days = (1...20).map { Self.day($0, stops) }   // 1000 stops
        let canvas = LioTripCanvas(template: Self.roadbook(days: days), lookup: LioNoPlaceLookup())
        #expect(canvas.pointCount == LioTripCanvas.maximumPoints && canvas.isValid)
    }

    // MARK: The places library

    @Test func aLookupHitGivesThePointItsLibraryId() throws {
        let canvas = LioTripCanvas(template: LioRoadbookTemplates.beijing(.chinese), lookup: Self.beijingLibrary)
        let palace = try #require(canvas.point("bj-002"))
        #expect(palace.placeID == "pl_bj_gugong")
        // The checked point it came with stays; the library's point does not replace it.
        #expect(palace.coordinate == .init(latitude: 39.917839, longitude: 116.397029))
        #expect(palace.nameZH == "故宫博物院" && palace.origin == .user)
    }

    @Test func aLookupMissKeepsTheNameAndThePoint() throws {
        let canvas = LioTripCanvas(template: LioRoadbookTemplates.beijing(.chinese), lookup: Self.beijingLibrary)
        let wall = try #require(canvas.point("bj-005"))
        #expect(wall.placeID == nil && wall.nameZH == "慕田峪长城" && wall.coordinate == .init(latitude: 40.431668, longitude: 116.565052))
        #expect(canvas.days.flatMap(\.points).filter { $0.placeID != nil }.map(\.id).sorted() == ["bj-001", "bj-002"])
    }

    @Test func theEnglishNameIsTriedWhenTheChineseOneMisses() throws {
        let canvas = LioTripCanvas(template: LioRoadbookTemplates.beijing(.chinese), lookup: Self.beijingLibrary)
        // "天安门广场" is not in the fake library; "Tian'anmen Square" is.
        #expect(try #require(canvas.point("bj-001")).placeID == "pl_bj_tiananmen")
    }

    @Test func theLookupIsAskedInsideTheRoutesCity() throws {
        let beijing = LioTripCanvas(template: LioRoadbookTemplates.beijing(.chinese), lookup: Self.beijingLibrary)
        let shanghai = LioTripCanvas(template: LioRoadbookTemplates.shanghai(.chinese), lookup: Self.beijingLibrary)
        // The Bund is Shanghai's: found on the Shanghai route, and the library does not answer for it from Beijing.
        #expect(try #require(shanghai.point("sh-004")).placeID == "pl_sh_waitan")
        #expect(beijing.days.flatMap(\.points).allSatisfy { $0.placeID != "pl_sh_waitan" })
        let asked = FakeLookup([:])
        _ = LioTripCanvas(template: LioRoadbookTemplates.shanghai(.english), lookup: asked)
        #expect(!asked.questions.isEmpty && asked.questions.allSatisfy { $0.hasSuffix("@shanghai") })
        let plain = FakeLookup([:])
        _ = LioTripCanvas(template: LioRoadbookTemplates.beijing(.chinese), lookup: plain)
        #expect(plain.questions.allSatisfy { $0.hasSuffix("@beijing") })
    }

    @Test func theLibrarysPointIsUsedOnlyForAPlaceWithNone() throws {
        let book = Self.roadbook(days: [Self.day(1, [Self.stop("a", "故宫博物院", "Palace Museum"),
                                                     Self.stop("b", "故宫博物院", "Palace Museum", point: .init(latitude: 1, longitude: 2))])])
        let canvas = LioTripCanvas(template: book, lookup: Self.beijingLibrary)
        #expect(try #require(canvas.point("a")).coordinate == .init(latitude: 39.9, longitude: 116.4))
        #expect(try #require(canvas.point("b")).coordinate == .init(latitude: 1, longitude: 2))
    }

    @Test func aLookupAnswerThatCannotBeUsedIsIgnored() throws {
        let broken = FakeLookup([
            "故宫博物院": .init(id: String(repeating: "x", count: 500), city: "beijing", coordinate: nil),
            "天安门广场": .init(id: "", city: "beijing", coordinate: nil),
            "景山公园": .init(id: "pl_bj_jingshan", city: "beijing", coordinate: .init(latitude: 400, longitude: 0)),
        ])
        let book = Self.roadbook(days: [Self.day(1, [Self.stop("a", "故宫博物院", "Palace"), Self.stop("b", "天安门广场", "Square"),
                                                     Self.stop("c", "景山公园", "Jingshan")])])
        let canvas = LioTripCanvas(template: book, lookup: broken)
        let a = try #require(canvas.point("a"))
        let b = try #require(canvas.point("b"))
        #expect(a.placeID == nil && b.placeID == nil)
        let c = try #require(canvas.point("c"))
        #expect(c.placeID == "pl_bj_jingshan" && c.coordinate == nil && canvas.isValid)
    }

    @Test func productionKnowsNoPlaceSoPointsKeepOnlyNameAndPoint() {
        #expect(LioNoPlaceLookup().match(name: "故宫博物院", city: "beijing") == nil)
        #expect(LioPlaceLookups.standard.match(name: "故宫博物院", city: nil) == nil)
        let canvas = LioTripCanvas(template: LioRoadbookTemplates.beijing(.chinese))
        #expect(canvas.days.flatMap(\.points).allSatisfy { $0.placeID == nil && $0.coordinate != nil })
    }

    @Test func aPointThatAlreadyHasAnIdKeepsIt() throws {
        var canvas = LioTripCanvas(template: Self.roadbook(days: [Self.day(1, [Self.stop("a", "故宫博物院", "Palace")])]),
                                   lookup: LioNoPlaceLookup())
        canvas.segments[0].days[0].points[0].placeID = "pl_mine"
        let again = canvas.resolvingPlaces(with: Self.beijingLibrary, city: "beijing")
        #expect(try #require(again.point("a")).placeID == "pl_mine")
    }

    @Test func theCityIdIsTheFirstWordOfTheRoutesId() {
        func city(_ id: String) -> String? {
            LioPlanSummary(template: Self.roadbook(days: [], id: id)).templateCityID
        }
        #expect(city("template.beijing-3d") == "beijing" && city("template.shanghai-2d") == "shanghai")
        #expect(city("template.chengdu") == "chengdu")
        #expect(city("template.") == nil)
        let chat = LioPlanSummary(tripID: "t", tripVersion: 1, source: .chat, startDate: nil,
                                  itinerary: LioRichItinerary(title: "", undated: true, days: [], lodgingArea: "", hotels: []))
        #expect(chat.templateCityID == nil)
    }

    // MARK: Using the route (the store)

    @Test func usingARouteKeepsItsCanvasOnThePhone() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = store(directory)
        let made = try store.useTemplate(LioRoadbookTemplates.beijing(.chinese), lookup: Self.beijingLibrary)
        #expect(made.tripID == "template:beijing-3d" && made.days.count == 3)
        let read = try #require(try store.canvas(for: "template:beijing-3d"))
        #expect(read == made && read.point("bj-002")?.placeID == "pl_bj_gugong" && read.days.flatMap(\.points).allSatisfy { $0.origin == .user })
    }

    @Test func tappingUseAsMyTripTwiceKeepsWhatTheTravellerChanged() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = store(directory)
        let book = LioRoadbookTemplates.beijing(.chinese)
        var first = try store.useTemplate(book, lookup: Self.beijingLibrary)
        let moved = first.moveToWishlist("bj-006")
        #expect(moved)
        _ = first.addDay()
        try store.save(first)
        let second = try store.useTemplate(book, lookup: LioNoPlaceLookup())
        #expect(second == first && second.wishlist.map(\.id) == ["bj-006"] && second.days.count == 4)
        #expect(try store.load().count == 1)
        // Another route is another canvas.
        _ = try store.useTemplate(LioRoadbookTemplates.shanghai(.chinese))
        #expect(try store.load().map(\.tripID).sorted() == ["template:beijing-3d", "template:shanghai-2d"])
    }

    @Test func aCanvasThatCannotBeWrittenIsReportedNotHidden() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let stale = store(directory, current: { false })
        #expect(throws: (any Error).self) { try stale.useTemplate(LioRoadbookTemplates.beijing(.chinese)) }
        // A newer app's file is never written over.
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent(LioTripCanvasStore.fileName)
        let newer = Data(#"{"version":9,"canvases":[]}"#.utf8)
        try newer.write(to: file)
        #expect(throws: LioTripCanvasStore.UnsupportedVersion(version: 9)) {
            try store(directory).useTemplate(LioRoadbookTemplates.beijing(.chinese))
        }
        #expect(try Data(contentsOf: file) == newer)
    }

    // MARK: The canvas screen's model

    @Test func aSavedRouteWithNoCanvasYetOpensWithItsPlacesLookedUpAndWritesNothing() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let plan = LioPlanSummary(template: LioRoadbookTemplates.beijing(.chinese))
        let model = LioTripCanvasModel(plan: plan, store: store(directory), lookup: Self.beijingLibrary)
        #expect(model.canvas.point("bj-002")?.placeID == "pl_bj_gugong" && model.canvas.days.count == 3)
        #expect(!FileManager.default.fileExists(atPath: directory.appendingPathComponent(LioTripCanvasStore.fileName).path))
        model.addWish("外滩")
        #expect(FileManager.default.fileExists(atPath: directory.appendingPathComponent(LioTripCanvasStore.fileName).path))
    }

    @Test func aCanvasAlreadyMadeIsOpenedAsItIs() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = store(directory)
        let book = LioRoadbookTemplates.beijing(.chinese)
        var made = try store.useTemplate(book, lookup: LioNoPlaceLookup())
        let moved = made.moveToWishlist("bj-006")
        #expect(moved)
        try store.save(made)
        let model = LioTripCanvasModel(plan: LioPlanSummary(template: book), store: store, lookup: Self.beijingLibrary)
        #expect(model.canvas == made && model.canvas.point("bj-002")?.placeID == nil)
    }

    @Test func aChatPlanIsNotLookedUp() {
        let plan = LioTripCanvasTests.plan()
        let lookup = FakeLookup([:])
        let model = LioTripCanvasModel(plan: plan, store: nil, lookup: lookup)
        #expect(lookup.questions.isEmpty && model.canvas.days.flatMap(\.points).allSatisfy { $0.origin == .lio && $0.placeID == nil })
    }

    // MARK: The switch

    @Test func theRoadbookToolLeavesTheToolsTabOnlyWhenTheCanvasIsOn() {
        // Off (or unset, or anything but YES): the Roadbook tool is exactly as it was.
        for canvas: Any? in [nil, "", "NO", "yes", "$(G2C_TRIP_CANVAS_ENABLED)", true] {
            #expect(LioRoadbookFeature.shownInTools(roadbookInfo: "YES", canvasInfo: canvas), "\(String(describing: canvas))")
            #expect(!LioRoadbookFeature.shownInTools(roadbookInfo: "NO", canvasInfo: canvas))
            #expect(!LioRoadbookFeature.shownInTools(roadbookInfo: nil, canvasInfo: canvas))
        }
        #expect(!LioRoadbookFeature.shownInTools(roadbookInfo: "YES", canvasInfo: "YES"))
        #expect(!LioRoadbookFeature.shownInTools(roadbookInfo: nil, canvasInfo: "YES"))
    }

    @Test func savingARouteAsATripStillWritesOnlyTheSavedPlan() throws {
        // The old path (and the canvas path's first step): "Use as my trip" saves the plan and touches no canvas file.
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let model = LioSavedPlansModel(store: LioSavedPlans(directory: directory, isCurrent: { true }))
        let book = LioRoadbookTemplates.beijing(.chinese)
        let saved = try #require(model.saveTemplate(book))
        #expect(saved.tripID == "template:beijing-3d" && saved.source == .template && saved.itinerary == book.itinerary)
        #expect(model.isSavedTemplate(book))
        #expect(!FileManager.default.fileExists(atPath: directory.appendingPathComponent(LioTripCanvasStore.fileName).path))
    }
}
