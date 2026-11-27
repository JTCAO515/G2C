import Foundation
import Testing
@testable import CJLioUser

/// #1995 (T-2): the trip canvas, local data version.
@MainActor struct LioTripCanvasTests {
    // MARK: Fixtures

    private static func place(_ zh: String, _ en: String, matched: Bool = false, latitude: Double? = nil) -> LioRichItinerary.Place {
        .init(nameZH: zh, nameEN: en, address: matched ? "\(zh)路 1 号" : nil, matched: matched,
              point: latitude.map { LioItinerary.Point(latitude: $0, longitude: 116.4) })
    }

    private static func stop(_ id: String, _ kind: LioRichItinerary.Kind, _ place: LioRichItinerary.Place, time: String? = nil) -> LioRichItinerary.Stop {
        .init(id: id, kind: kind, text: "", time: time, place: place, note: nil, tip: nil)
    }

    /// Day 1: a, b, c (a→b walking 10 min, b→c no estimate). Day 2: d, e.
    static func plan(source: LioPlanSummary.Source = .chat, version: Int64 = 1, id: String = "trip-1") -> LioPlanSummary {
        let day1 = LioRichItinerary.Day(number: 1, date: "2026-12-01", theme: "老城", area: "东城", stops: [
            stop("a", .sight, place("天安门广场", "Tiananmen Square", matched: true, latitude: 39.9), time: "09:00"),
            stop("b", .sight, place("故宫", "Forbidden City", matched: true, latitude: 39.92), time: "10:30"),
            stop("c", .meal, place("全聚德", "Quanjude")),
        ], legs: [
            .init(fromID: "a", toID: "b", estimate: .init(mode: .walking, seconds: 600, metres: 800)),
            .init(fromID: "b", toID: "c", estimate: nil),
        ])
        let day2 = LioRichItinerary.Day(number: 2, date: nil, theme: "", area: "", stops: [
            stop("d", .sight, place("长城", "Great Wall")),
            stop("e", .hotel, place("王府井酒店", "Wangfujing Hotel")),
        ], legs: [])
        return LioPlanSummary(tripID: id, tripVersion: version, source: source, startDate: "2026-12-01",
                              itinerary: LioRichItinerary(title: "北京三日", undated: false, days: [day1, day2], lodgingArea: "", hotels: []))
    }

    private func canvas(_ plan: LioPlanSummary = LioTripCanvasTests.plan()) -> LioTripCanvas { LioTripCanvas(plan: plan) }

    private func ids(_ canvas: LioTripCanvas, day: Int) -> [String] { canvas.days[day].points.map(\.id) }

    private func folder() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("trip-canvas-" + UUID().uuidString, isDirectory: true)
    }

    // MARK: Converting a saved plan

    @Test func aChatPlanBecomesCitySegmentDaysAndPointsDraftedByLio() throws {
        let canvas = canvas()
        #expect(canvas.tripID == "trip-1" && canvas.title == "北京三日" && canvas.startDate == "2026-12-01" && !canvas.undated)
        #expect(canvas.source == .chat && canvas.sourceVersion == 1)
        #expect(canvas.segments.count == 1 && canvas.days.count == 2 && canvas.wishlist.isEmpty)
        #expect(canvas.days.map(\.id) == ["day-1", "day-2"] && canvas.days[0].date == "2026-12-01" && canvas.days[0].area == "东城")
        #expect(ids(canvas, day: 0) == ["a", "b", "c"] && ids(canvas, day: 1) == ["d", "e"])
        let a = try #require(canvas.point("a"))
        #expect(a.nameZH == "天安门广场" && a.nameEN == "Tiananmen Square" && a.time == "09:00" && a.kind == .sight)
        #expect(a.origin == .lio && a.placeID == nil)
        #expect(a.address == "天安门广场路 1 号" && a.coordinate == .init(latitude: 39.9, longitude: 116.4))
        let c = try #require(canvas.point("c"))
        #expect(c.coordinate == nil && c.address == nil && c.kind == .meal)
        #expect(canvas.days.flatMap(\.points).allSatisfy { $0.origin == .lio })
        #expect(canvas.dayNumber("day-2") == 2 && canvas.pointCount == 5 && !canvas.hasUserEdits && canvas.isValid)
    }

    @Test func theWayToTheNextPointIsKeptWhereThePlanHadAnEstimate() throws {
        let canvas = canvas()
        let leg = try #require(canvas.leg(from: "a", to: "b"))
        #expect(leg.mode == .walking && leg.seconds == 600 && leg.metres == 800)
        #expect(leg.description(.english) == "Walk · about 10 min · 0.8 km" && leg.description(.chinese) == "步行 · 约 10 分钟 · 0.8 公里")
        #expect(canvas.leg(from: "b", to: "c") == nil)
        #expect(canvas.leg(after: 0, in: canvas.days[0]) == leg && canvas.leg(after: 2, in: canvas.days[0]) == nil)
    }

    @Test func aRouteTheTravellerTookAsTheirOwnTripIsTheirs() {
        let canvas = LioTripCanvas(plan: Self.plan(source: .template, version: 0, id: "template:classic"))
        #expect(canvas.source == .template)
        #expect(canvas.days.flatMap(\.points).allSatisfy { $0.origin == .user })
    }

    @Test func aPlanWithNoDaysIsAnEmptyCanvasThatStillWorks() throws {
        let plan = LioPlanSummary(tripID: "t", tripVersion: 1, source: .chat, startDate: nil,
                                  itinerary: LioRichItinerary(title: "", undated: true, days: [], lodgingArea: "", hotels: []))
        var canvas = LioTripCanvas(plan: plan)
        #expect(canvas.isEmpty && canvas.days.isEmpty && canvas.segments.count == 1 && canvas.isValid)
        let r1 = canvas.addWish(id: "w1", name: "外滩")
        #expect(r1)
        let added = canvas.addDay()
        let day = try #require(added)
        let r2 = canvas.move("w1", toDay: day, at: 0)
        #expect(day == "day-1" && r2)
        #expect(canvas.days[0].points.map(\.id) == ["w1"] && canvas.wishlist.isEmpty)
        let standalone = LioTripCanvas(emptyTripID: LioTripCanvas.standaloneID)
        #expect(standalone.isEmpty && standalone.tripID == "local" && standalone.isValid)
    }

    @Test func repeatedStopIdsStayUniqueAndTheirLegsFollow() throws {
        let day = { (number: Int) in
            LioRichItinerary.Day(number: number, date: nil, theme: "", area: "", stops: [
                Self.stop("s", .sight, Self.place("甲", "A")), Self.stop("t", .sight, Self.place("乙", "B")),
            ], legs: [.init(fromID: "s", toID: "t", estimate: .init(mode: .taxi, seconds: 120, metres: 500))])
        }
        let plan = LioPlanSummary(tripID: "t", tripVersion: 1, source: .chat, startDate: nil,
                                  itinerary: LioRichItinerary(title: "x", undated: true, days: [day(1), day(1)], lodgingArea: "", hotels: []))
        let canvas = LioTripCanvas(plan: plan)
        let all = canvas.days.flatMap(\.points).map(\.id)
        #expect(all.count == 4 && Set(all).count == 4 && Set(canvas.days.map(\.id)).count == 2 && canvas.isValid)
        #expect(canvas.legs.count == 2 && canvas.leg(from: all[2], to: all[3])?.mode == .taxi)
    }

    // MARK: Dragging

    @Test func movingAPointWithinItsDayReordersItAndMakesOnlyThatPointTheTravellers() {
        var canvas = canvas()
        let r3 = canvas.move("c", toDay: "day-1", at: 0)
        #expect(r3)
        #expect(ids(canvas, day: 0) == ["c", "a", "b"])
        #expect(canvas.point("c")?.origin == .user)
        #expect(canvas.point("a")?.origin == .lio && canvas.point("b")?.origin == .lio && canvas.point("d")?.origin == .lio)
        #expect(canvas.hasUserEdits)
    }

    @Test func droppingOnAPointTakesItsPlaceWhicheverWayItMoves() {
        var down = canvas()
        let r4 = down.move("a", onto: "c")
        #expect(r4)
        #expect(ids(down, day: 0) == ["b", "c", "a"])
        var up = canvas()
        let r5 = up.move("c", onto: "a")
        #expect(r5)
        #expect(ids(up, day: 0) == ["c", "a", "b"])
        var same = canvas()
        let r6 = same.move("b", onto: "b")
        let r7 = same.move("b", onto: "missing")
        let r8 = same.move("missing", onto: "b")
        #expect(!r6 && !r7 && !r8)
        #expect(!same.hasUserEdits)
    }

    @Test func movingToTheSameSpotChangesNothingAndMarksNothing() {
        var canvas = canvas()
        let r9 = canvas.move("b", toDay: "day-1", at: 1)
        #expect(!r9)
        let r10 = canvas.moveToEnd("c", ofDay: "day-1")
        #expect(!r10)
        let r11 = canvas.move("a", toDay: "no-such-day", at: 0)
        #expect(!r11)
        #expect(ids(canvas, day: 0) == ["a", "b", "c"] && !canvas.hasUserEdits)
    }

    @Test func aPointMovedToAnotherDayLeavesTheFirstAndLandsWhereDropped() {
        var canvas = canvas()
        let r12 = canvas.move("b", toDay: "day-2", at: 1)
        #expect(r12)
        #expect(ids(canvas, day: 0) == ["a", "c"] && ids(canvas, day: 1) == ["d", "b", "e"])
        #expect(canvas.point("b")?.origin == .user && canvas.point("e")?.origin == .lio)
        let r13 = canvas.moveToEnd("a", ofDay: "day-2")
        #expect(r13)
        #expect(ids(canvas, day: 1) == ["d", "b", "e", "a"])
        // An index past the end lands at the end, a negative one at the start.
        let r14 = canvas.move("c", toDay: "day-2", at: 99)
        #expect(r14 && ids(canvas, day: 1).last == "c")
        let r15 = canvas.move("d", toDay: "day-2", at: -5)
        #expect(r15 == false)
        let r16 = canvas.move("e", toDay: "day-2", at: -5)
        #expect(r16 && ids(canvas, day: 1).first == "e")
        #expect(canvas.pointCount == 5 && canvas.isValid)
    }

    @Test func aWayBetweenTwoPointsComesBackWhenTheyAreNextToEachOtherAgain() {
        var canvas = canvas()
        canvas.move("b", toDay: "day-2", at: 0)
        #expect(canvas.leg(after: 0, in: canvas.days[0]) == nil, "a and c were never planned")
        canvas.move("a", toDay: "day-2", at: 0)
        #expect(canvas.leg(from: "a", to: "b") != nil)
        #expect(ids(canvas, day: 1) == ["a", "b", "d", "e"])
        #expect(canvas.leg(after: 0, in: canvas.days[1])?.mode == .walking)
    }

    @Test func shiftingMovesOnePlaceAndStopsAtTheEnds() {
        var canvas = canvas()
        let r17 = canvas.shift("a", by: -1)
        let r18 = canvas.shift("c", by: 1)
        #expect(!r17 && !r18)
        let r19 = canvas.shift("b", by: 1)
        #expect(r19 && ids(canvas, day: 0) == ["a", "c", "b"])
        let r20 = canvas.shift("b", by: -1)
        #expect(r20 && ids(canvas, day: 0) == ["a", "b", "c"])
        let r21 = canvas.shift("missing", by: 1)
        #expect(!r21)
    }

    // MARK: Want to go

    @Test func aPlaceNamedByTheTravellerGoesToTheInboxAsTheirs() throws {
        var canvas = canvas()
        let r22 = canvas.addWish(id: "w1", name: "  外滩 ")
        #expect(r22)
        let wish = try #require(canvas.point("w1"))
        #expect(wish.nameZH == "外滩" && wish.nameEN == "外滩" && wish.origin == .user && wish.kind == .unspecified && wish.time == nil)
        #expect(canvas.wishlist.map(\.id) == ["w1"] && canvas.locate("w1") == .wishlist(index: 0))
        let r23 = canvas.addWish(id: "w2", name: "   ")
        #expect(!r23, "a blank name adds nothing")
        let r24 = canvas.addWish(id: "w1", name: "again")
        #expect(!r24, "an id that is taken adds nothing")
        #expect(canvas.wishlist.count == 1 && canvas.isValid)
    }

    @Test func theInboxIsCapped() {
        var canvas = canvas()
        for index in 0..<LioTripCanvas.maximumWishlist {
            let added = canvas.addWish(id: "w\(index)", name: "地点\(index)")
            #expect(added)
        }
        let r25 = canvas.addWish(id: "extra", name: "多一个")
        #expect(!r25 && canvas.wishlist.count == LioTripCanvas.maximumWishlist)
    }

    @Test func aPointCanGoToTheInboxAndBackOntoADay() {
        var canvas = canvas()
        let r26 = canvas.moveToWishlist("b")
        #expect(r26)
        #expect(ids(canvas, day: 0) == ["a", "c"] && canvas.wishlist.map(\.id) == ["b"] && canvas.point("b")?.origin == .user)
        let r27 = canvas.moveToWishlist("b")
        #expect(!r27, "already last in the inbox")
        canvas.addWish(id: "w", name: "外滩")
        let r28 = canvas.move("w", onto: "b")
        #expect(r28 && canvas.wishlist.map(\.id) == ["w", "b"])
        let r29 = canvas.move("b", toDay: "day-2", at: 0)
        #expect(r29)
        #expect(ids(canvas, day: 1) == ["b", "d", "e"] && canvas.wishlist.map(\.id) == ["w"])
        let r30 = canvas.shift("w", by: 1)
        #expect(r30 == false)
    }

    // MARK: Delete, edit, add a day

    @Test func removingAPointAlsoDropsTheWaysThatTouchedIt() {
        var canvas = canvas()
        let r31 = canvas.remove("a")
        #expect(r31?.nameZH == "天安门广场")
        #expect(canvas.point("a") == nil && ids(canvas, day: 0) == ["b", "c"] && canvas.legs.isEmpty)
        let r32 = canvas.remove("a")
        #expect(r32 == nil)
    }

    @Test func editingAPointMakesItTheTravellersAndKeepsTheOtherLanguageName() throws {
        var canvas = canvas()
        let r33 = canvas.edit("a", name: "天安门", in: .chinese)
        #expect(r33)
        var a = try #require(canvas.point("a"))
        #expect(a.nameZH == "天安门" && a.nameEN == "Tiananmen Square" && a.origin == .user)
        let r34 = canvas.edit("b", name: "The Palace Museum", in: .english)
        #expect(r34)
        let b = try #require(canvas.point("b"))
        #expect(b.nameEN == "The Palace Museum" && b.nameZH == "故宫" && b.origin == .user)
        // A chat plan has one name for both languages; renaming it renames both.
        var plain = LioTripCanvas(plan: LioPlanSummary(tripID: "t", tripVersion: 1, title: "x", startDate: nil, undated: true,
                                                      days: [.init(number: 1, date: nil, items: [.init(id: "i", label: "颐和园", startTime: nil, endTime: nil, fixed: nil)])]))
        let r35 = plain.edit("i", name: "夏宫", in: .english)
        #expect(r35)
        #expect(plain.point("i")?.nameZH == "夏宫" && plain.point("i")?.nameEN == "夏宫")
        // Only the time.
        let r36 = canvas.edit("c", time: .some("18:30"))
        #expect(r36 && canvas.point("c")?.time == "18:30" && canvas.point("c")?.origin == .user)
        let r37 = canvas.edit("c", time: .some(nil))
        #expect(r37 && canvas.point("c")?.time == nil)
        a = try #require(canvas.point("a"))
        #expect(a.time == "09:00")
    }

    @Test func anEditThatChangesNothingOrBlanksTheNameLeavesThePointAlone() {
        var canvas = canvas()
        let r38 = canvas.edit("a", name: "天安门广场", in: .chinese)
        #expect(!r38)
        let r39 = canvas.edit("a", time: .some("09:00"))
        #expect(!r39)
        let r40 = canvas.edit("a", name: "   ")
        #expect(!r40)
        let r41 = canvas.edit("missing", name: "x")
        #expect(!r41)
        #expect(canvas.point("a")?.origin == .lio && !canvas.hasUserEdits)
    }

    @Test func daysAreAddedAtTheEndWithNewIds() {
        var canvas = canvas()
        let r42 = canvas.addDay()
        #expect(r42 == "day-3" && canvas.days.count == 3 && canvas.days[2].points.isEmpty)
        #expect(canvas.dayNumber("day-3") == 3)
        for _ in canvas.days.count..<LioTripCanvas.maximumDays { canvas.addDay() }
        let r43 = canvas.addDay()
        #expect(r43 == nil && canvas.days.count == LioTripCanvas.maximumDays)
    }

    // MARK: Reading it back

    @Test func aCanvasSurvivesEncodingAndRejectsWhatAFileMightBreak() throws {
        var canvas = canvas()
        canvas.addWish(id: "w", name: "外滩")
        canvas.move("b", toDay: "day-2", at: 0)
        let data = try JSONEncoder().encode(canvas)
        #expect(try JSONDecoder().decode(LioTripCanvas.self, from: data) == canvas)

        var duplicated = canvas
        duplicated.wishlist[0] = LioTripCanvas.Point(id: "a", placeID: nil, nameZH: "x", nameEN: "x", address: nil, coordinate: nil,
                                                      time: nil, kind: .sight, origin: .user)
        #expect(!duplicated.isValid)
        var far = canvas
        far.segments[0].days[0].points[0].coordinate = .init(latitude: 400, longitude: 0)
        #expect(!far.isValid)
        var long = canvas
        long.segments[0].days[0].points[0].nameZH = String(repeating: "长", count: LioTripCanvas.maximumNameLength + 1)
        #expect(!long.isValid)
    }

    @Test func aNewerCopyOfThePlanReplacesAnUntouchedCanvasButNeverOneTheTravellerChanged() {
        let stored = canvas(Self.plan(version: 1))
        let newer = Self.plan(version: 2)
        #expect(LioTripCanvas.resolved(stored: stored, plan: newer).sourceVersion == 2)
        #expect(LioTripCanvas.resolved(stored: stored, plan: Self.plan(version: 1)) == stored)
        var edited = stored
        edited.move("c", toDay: "day-1", at: 0)
        #expect(LioTripCanvas.resolved(stored: edited, plan: newer) == edited)
        var wished = stored
        wished.addWish(id: "w", name: "外滩")
        #expect(LioTripCanvas.resolved(stored: wished, plan: newer) == wished)
        #expect(LioTripCanvas.resolved(stored: stored, plan: Self.plan(version: 1, id: "other")).tripID == "other")
        #expect(LioTripCanvas.resolved(stored: nil, plan: newer).sourceVersion == 2)
    }

    // MARK: The file

    @Test func theStoreKeepsOneCanvasPerTripBesideTheTripHomeFile() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let home = LioTripHomeStore(directory: LioTripHomeStore.storageDirectory(inMessageDirectory: directory), isCurrent: { true })
        let store = try #require(LioTripCanvasStore(tripHome: home))
        #expect(try store.load().isEmpty)
        var first = canvas()
        try store.save(first)
        first.move("c", toDay: "day-1", at: 0)
        try store.save(first)
        try store.save(canvas(Self.plan(id: "trip-2")))
        #expect(try store.load().map(\.tripID) == ["trip-2", "trip-1"])
        #expect(try store.canvas(for: "trip-1") == first && (try store.canvas(for: "none")) == nil)
        let folder = LioTripHomeStore.storageDirectory(inMessageDirectory: directory)
        #expect(try FileManager.default.contentsOfDirectory(atPath: folder.path) == [LioTripCanvasStore.fileName])
        #expect(try folder.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup == true)
        try store.remove("trip-2")
        try store.remove("trip-2")
        #expect(try store.load().map(\.tripID) == ["trip-1"])
        #expect(LioTripCanvasStore(tripHome: nil) == nil)
    }

    @Test func anotherAccountCannotReadOrWriteTheCanvas() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        var current = true
        let store = LioTripCanvasStore(directory: directory, isCurrent: { current })
        try store.save(canvas())
        current = false
        #expect(throws: CancellationError.self) { try store.load() }
        #expect(throws: CancellationError.self) { try store.save(canvas()) }
        current = true
        #expect(try store.load().count == 1)
    }

    @Test func aDamagedFileReadsAsEmptyAndABrokenCanvasIsSkippedNotItsNeighbours() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripCanvasStore(directory: directory, isCurrent: { true })
        try store.save(canvas())
        let file = directory.appendingPathComponent(LioTripCanvasStore.fileName)
        let good = try Data(contentsOf: file)
        try Data("not json".utf8).write(to: file)
        #expect(try store.load().isEmpty)
        // A second canvas that is not a canvas.
        var text = try #require(String(data: good, encoding: .utf8))
        text = text.replacingOccurrences(of: "\"canvases\":[", with: "\"canvases\":[{\"tripID\":7},")
        try Data(text.utf8).write(to: file)
        #expect(try store.load().map(\.tripID) == ["trip-1"])
        // One that decodes but is not valid: its inbox is over the cap.
        var over = canvas(Self.plan(id: "over"))
        over.wishlist = (0...LioTripCanvas.maximumWishlist).map {
            .init(id: "w\($0)", placeID: nil, nameZH: "x", nameEN: "x", address: nil, coordinate: nil, time: nil, kind: .unspecified, origin: .user)
        }
        try Data(JSONEncoder().encode(["version": 1] as [String: Int]).dropLast() + Data(",\"canvases\":".utf8)
                 + JSONEncoder().encode([over, canvas()]) + Data("}".utf8)).write(to: file)
        #expect(try store.load().map(\.tripID) == ["trip-1"])
    }

    @Test func aDamagedFileIsCopiedBeforeASaveReplacesItAndAGoodOneIsNot() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripCanvasStore(directory: directory, isCurrent: { true })
        let file = directory.appendingPathComponent(LioTripCanvasStore.fileName)
        func names() throws -> [String] { try FileManager.default.contentsOfDirectory(atPath: directory.path).sorted() }
        try store.save(canvas())
        try store.save(canvas(Self.plan(id: "trip-2")))
        #expect(try names() == [LioTripCanvasStore.fileName])                          // a good file leaves no copy
        let good = try Data(contentsOf: file)
        // One canvas that does not decode, beside two good ones: saving a third keeps the original bytes aside.
        var text = try #require(String(data: good, encoding: .utf8))
        text = text.replacingOccurrences(of: "\"canvases\":[", with: "\"canvases\":[{\"tripID\":7},")
        let oneBad = Data(text.utf8)
        try oneBad.write(to: file)
        try store.save(canvas(Self.plan(id: "trip-3")))
        #expect(try names() == ["trip-canvas.damaged-1.json", LioTripCanvasStore.fileName])
        #expect(try Data(contentsOf: directory.appendingPathComponent(LioTripCanvasStore.damagedCopyNames[0])) == oneBad)
        #expect(try store.load().map(\.tripID) == ["trip-3", "trip-2", "trip-1"])        // the file itself is whole again
        try store.save(canvas(Self.plan(id: "trip-4")))
        #expect(try names().count == 2)                                                  // and now saves leave nothing more
        // An unreadable file: kept too, and a remove of a canvas that is not there neither writes nor copies.
        try Data("not json".utf8).write(to: file)
        try store.remove("nothing-here")
        #expect(try names().count == 2)
        try store.save(canvas())
        #expect(try Data(contentsOf: directory.appendingPathComponent("trip-canvas.damaged-1.json")) == Data("not json".utf8))
        #expect(try Data(contentsOf: directory.appendingPathComponent("trip-canvas.damaged-2.json")) == oneBad)    // the earlier copy moved down
        #expect(try store.load().map(\.tripID) == ["trip-1"])
    }

    @Test func onlyTheNewestFewDamagedCopiesAreKept() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripCanvasStore(directory: directory, isCurrent: { true })
        let file = directory.appendingPathComponent(LioTripCanvasStore.fileName)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        for round in 1...5 {
            try Data("bad \(round)".utf8).write(to: file)
            try store.save(canvas())
        }
        let copies = try FileManager.default.contentsOfDirectory(atPath: directory.path).filter { $0.hasPrefix("trip-canvas.damaged-") }.sorted()
        #expect(copies == LioTripCanvasStore.damagedCopyNames)
        for (index, name) in LioTripCanvasStore.damagedCopyNames.enumerated() {          // newest first: bad 5, bad 4, bad 3
            #expect(try Data(contentsOf: directory.appendingPathComponent(name)) == Data("bad \(5 - index)".utf8))
        }
    }

    @Test func aNewerAppsFileIsNeverWrittenOver() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripCanvasStore(directory: directory, isCurrent: { true })
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent(LioTripCanvasStore.fileName)
        let newer = Data(#"{"version":2,"canvases":[]}"#.utf8)
        try newer.write(to: file)
        #expect(throws: LioTripCanvasStore.UnsupportedVersion.self) { try store.load() }
        #expect(throws: LioTripCanvasStore.UnsupportedVersion.self) { try store.save(canvas()) }
        let kept = try Data(contentsOf: file)
        #expect(kept == newer)
    }

    // MARK: The screen's model

    @Test func everyChangeIsWrittenAndComesBackWhenTheScreenOpensAgain() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripCanvasStore(directory: directory, isCurrent: { true })
        let plan = Self.plan()
        let model = LioTripCanvasModel(plan: plan, store: store)
        #expect(model.persists && !model.canUndo && model.notice == nil)
        #expect(try store.load().isEmpty, "opening a plan writes nothing")
        model.move("c", toDay: "day-1", at: 0)
        model.addWish("外滩")
        model.move("e", toDay: "day-1", at: 1)
        model.remove("d")
        model.addDay()
        let reopened = LioTripCanvasModel(plan: plan, store: store)
        #expect(reopened.canvas == model.canvas)
        #expect(ids(reopened.canvas, day: 0) == ["c", "e", "a", "b"] && reopened.canvas.days.count == 3)
        #expect(reopened.canvas.wishlist.map(\.nameZH) == ["外滩"] && reopened.canvas.point("d") == nil)
        #expect(!model.saveFailed)
    }

    @Test func theLastChangeCanBeUndoneOnceAndIsNamed() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripCanvasStore(directory: directory, isCurrent: { true })
        let model = LioTripCanvasModel(plan: Self.plan(), store: store)
        model.remove("a")
        #expect(model.notice?.kind == .removed && model.notice?.text(.chinese) == "已删除「天安门广场」"
                && model.notice?.text(.english) == "Removed “Tiananmen Square”")
        #expect(model.canUndo && model.canvas.point("a") == nil)
        model.undo()
        #expect(model.canvas.point("a")?.origin == .lio && ids(model.canvas, day: 0) == ["a", "b", "c"])
        #expect(!model.canUndo && model.notice == nil)
        model.undo()
        #expect(try store.canvas(for: "trip-1")?.point("a") != nil, "the undo reached the file")
        model.move("b", toDay: "day-2", at: 0)
        #expect(model.notice?.kind == .moved && model.notice?.text(.english) == "Moved “Forbidden City”")
        model.dismissNotice()
        #expect(model.notice == nil && model.canUndo)
    }

    @Test func aChangeThatDoesNothingLeavesNoNoticeNoUndoAndNoWrite() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioTripCanvasStore(directory: directory, isCurrent: { true })
        let model = LioTripCanvasModel(plan: Self.plan(), store: store)
        model.move("a", toDay: "day-1", at: 0)
        model.addWish("   ")
        model.remove("missing")
        #expect(model.notice == nil && !model.canUndo)
        #expect(!FileManager.default.fileExists(atPath: directory.appendingPathComponent(LioTripCanvasStore.fileName).path))
    }

    @Test func aFileThePhoneCannotReadIsNotWrittenOver() throws {
        let directory = folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent(LioTripCanvasStore.fileName)
        let newer = Data(#"{"version":9,"canvases":[]}"#.utf8)
        try newer.write(to: file)
        let model = LioTripCanvasModel(plan: Self.plan(), store: LioTripCanvasStore(directory: directory, isCurrent: { true }))
        #expect(!model.persists)
        model.move("c", toDay: "day-1", at: 0)
        #expect(ids(model.canvas, day: 0) == ["c", "a", "b"], "the change shows")
        let kept = try Data(contentsOf: file)
        #expect(model.saveFailed && kept == newer, "but is not kept, and says so")
    }

    @Test func withNoStoreTheCanvasWorksForTheSessionAndKeepsNothing() {
        let model = LioTripCanvasModel(plan: nil, store: nil, makeID: { "w-1" })
        #expect(model.canvas.tripID == "local" && model.canvas.isEmpty && !model.persists)
        model.addWish("外滩")
        #expect(model.canvas.wishlist.map(\.id) == ["w-1"] && !model.saveFailed)
        #expect(model.notice?.text(.chinese) == "已加入「外滩」" && model.notice?.text(.english) == "Added “外滩”")
        model.addDay()
        #expect(model.canvas.days.count == 1 && model.notice?.kind == .dayAdded)
    }

    // MARK: The switch

    @Test func theSwitchIsOffByDefaultAndListedButNotOnInTheRelease() throws {
        #expect(LioTripCanvasFeature.infoKey == "G2CTripCanvasEnabled")
        #expect(LioTripCanvasFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "", "NO", "yes", "1", true, 1, "$(G2C_TRIP_CANVAS_ENABLED)"] {
            #expect(!LioTripCanvasFeature.enabled(infoValue: value), "\(String(describing: value))")
        }
        #expect(!LioTripCanvasFeature.enabledInBuild, "the test bundle sets no flag")
        var ios = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { ios.deleteLastPathComponent() }
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        #expect(plist.contains("<key>G2CTripCanvasEnabled</key><string>$(G2C_TRIP_CANVAS_ENABLED)</string>"))
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(!project.contains("G2C_TRIP_CANVAS_ENABLED"), "the setting stays unset in the project")
        let manifestURL = ios.deletingLastPathComponent().appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_TRIP_CANVAS_ENABLED", "plist": "G2CTripCanvasEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        #expect(!(try #require(release["on"] as? [String])).contains("G2C_TRIP_CANVAS_ENABLED"))
    }
}
