import SwiftUI
import Testing
@testable import CJLioUser

/// #1996 (T-3): the trip map's input, scene, replaceable layer and the saved-plans conversion.
@MainActor
struct LioTripMapTests {
    // MARK: Fixtures

    private static func point(_ id: String, _ number: Int, _ lat: Double?, _ lng: Double?, name: String? = nil) -> LioTripMapInput.Point {
        .init(id: id, name: name ?? "Place \(id)", latitude: lat, longitude: lng, number: number)
    }

    private static func day(_ number: Int, slot: Int? = nil, _ points: [LioTripMapInput.Point],
                            segments: [LioTripMapInput.Segment] = []) -> LioTripMapInput.Day {
        .init(number: number, colorSlot: slot ?? number - 1, points: points, segments: segments)
    }

    private static func scene(_ days: [LioTripMapInput.Day], _ language: LioLanguage = .english) -> LioTripMapScene {
        LioTripMapScene(LioTripMapInput(days: days), language: language)
    }

    private static func place(_ zh: String, _ en: String, _ lat: Double?, _ lng: Double?, matched: Bool = true) -> LioRichItinerary.Place {
        .init(nameZH: zh, nameEN: en, address: nil, matched: matched, point: lat.flatMap { lat in lng.map { .init(latitude: lat, longitude: $0) } })
    }

    private static func stop(_ id: String, _ place: LioRichItinerary.Place) -> LioRichItinerary.Stop {
        .init(id: id, kind: .sight, text: "", time: nil, place: place, note: nil, tip: nil)
    }

    private static func leg(_ from: String, _ to: String, _ mode: LioRichItinerary.Leg.Mode?, minutes: Double) -> LioRichItinerary.Leg {
        .init(fromID: from, toID: to, estimate: mode.map { .init(mode: $0, seconds: minutes * 60, metres: 1000) })
    }

    private static func richDay(_ number: Int, _ stops: [LioRichItinerary.Stop], legs: [LioRichItinerary.Leg] = []) -> LioRichItinerary.Day {
        .init(number: number, date: nil, theme: "", area: "", stops: stops, legs: legs)
    }

    private static func itinerary(_ days: [LioRichItinerary.Day]) -> LioRichItinerary {
        .init(title: "Beijing", undated: true, days: days, lodgingArea: "", hotels: [])
    }

    // MARK: Colours and numbers

    @Test func everyDayHasItsOwnColourAndTheSixthDayIsFollowedByTheFirstColourAgain() {
        let days = (1...8).map { number in
            Self.richDay(number, [Self.stop("s\(number)", Self.place("地\(number)", "P\(number)", 39.9, 116.4))])
        }
        let input = LioTripMapInput(itinerary: Self.itinerary(days), language: .english)
        #expect(input.days.map(\.colorSlot) == [0, 1, 2, 3, 4, 5, 0, 1])
        #expect(Set(input.days.prefix(LioTripMapPalette.slotCount).map(\.colorSlot)).count == LioTripMapPalette.slotCount)
        let scene = LioTripMapScene(input, language: .english)
        #expect(scene.pins.map(\.colorSlot) == [0, 1, 2, 3, 4, 5, 0, 1])
        #expect(scene.legend.map(\.dayNumber) == Array(1...8))
        #expect(LioTripMapPalette.normalized(-1) == 5)
        #expect(LioTripMapPalette.normalized(13) == 1)
        #expect(Self.scene([Self.day(1, slot: -2, [Self.point("a", 1, 39.9, 116.4)])]).pins.first?.colorSlot == 4)
    }

    @Test func aDayWithoutStopsKeepsItsColourForTheDaysAfterIt() {
        let input = LioTripMapInput(itinerary: Self.itinerary([
            Self.richDay(1, [Self.stop("a", Self.place("甲", "A", 39.9, 116.4))]),
            Self.richDay(2, []),
            Self.richDay(3, [Self.stop("c", Self.place("丙", "C", 39.8, 116.3))])
        ]), language: .english)
        #expect(input.days.map(\.colorSlot) == [0, 1, 2])
        let scene = LioTripMapScene(input, language: .english)
        #expect(scene.legend.map(\.dayNumber) == [1, 3])
        #expect(scene.legend.map(\.colorSlot) == [0, 2])
    }

    @Test func numbersFollowTheDayOrderEvenWhenSomePointsHaveNoPosition() {
        let scene = Self.scene([Self.day(1, [
            Self.point("a", 1, 39.90, 116.40), Self.point("b", 2, nil, nil),
            Self.point("c", 3, 39.92, 116.41), Self.point("d", 4, 39.93, 116.43)
        ])])
        #expect(scene.pins.map(\.number) == [1, 3, 4])
        #expect(scene.pins.map(\.id) == ["a", "c", "d"])
        #expect(scene.unplaced.map(\.number) == [2])
        #expect(scene.unplaced.map(\.pointID) == ["b"])
        // The line joins the points that are drawn, in order.
        #expect(scene.lines.map(\.key) == ["0-1-3", "0-3-4"])
    }

    @Test func eachPinHasAnAccessibleNameWithDayStopAndPlace() {
        let input = [Self.day(2, [Self.point("a", 1, 39.9, 116.4, name: "Palace Museum")])]
        #expect(Self.scene(input, .english).pins.first?.accessibilityLabel == "Day 2, stop 1: Palace Museum")
        #expect(Self.scene(input, .chinese).pins.first?.accessibilityLabel == "第 2 天，第 1 站：Palace Museum")
    }

    // MARK: Points without a position

    @Test func pointsWithoutAUsablePositionAreListedAndNeverDrawn() {
        let scene = Self.scene([Self.day(1, [
            Self.point("none", 1, nil, nil),
            Self.point("half", 2, 39.9, nil),
            Self.point("nan", 3, .nan, 116.4),
            Self.point("inf", 4, 39.9, .infinity),
            Self.point("latRange", 5, 91, 116.4),
            Self.point("lngRange", 6, 39.9, -181),
            Self.point("ok", 7, 39.9, 116.4)
        ])])
        #expect(scene.pins.map(\.id) == ["ok"])
        #expect(scene.unplaced.map(\.pointID) == ["none", "half", "nan", "inf", "latRange", "lngRange"])
        #expect(scene.lines.isEmpty)
        #expect(!scene.isEmpty && !scene.hasNoPoints)
    }

    @Test func whenNoPointHasAPositionTheMapIsEmptyAndEveryPointIsStillListed() {
        let scene = Self.scene([
            Self.day(1, [Self.point("a", 1, nil, nil), Self.point("b", 2, nil, nil)]),
            Self.day(2, [Self.point("c", 1, nil, nil)])
        ])
        #expect(scene.isEmpty)
        #expect(!scene.hasNoPoints)
        #expect(scene.unplaced.map(\.pointID) == ["a", "b", "c"])
        #expect(scene.unplaced.map(\.dayNumber) == [1, 1, 2])
        #expect(scene.legend.isEmpty && scene.lines.isEmpty)
        #expect(scene.fit == nil)
    }

    @Test func aTripWithoutPointsHasNothingToShowOrList() {
        for days in [[], [Self.day(1, [])]] as [[LioTripMapInput.Day]] {
            let scene = Self.scene(days)
            #expect(scene.isEmpty && scene.hasNoPoints && scene.unplaced.isEmpty && scene.fit == nil)
        }
    }

    // MARK: Edges: one point, several days, repeated places

    @Test func onePointIsShownWithAStreetLevelRegionAndNoLine() throws {
        let scene = Self.scene([Self.day(1, [Self.point("only", 1, 31.2304, 121.4737)])])
        #expect(scene.pins.count == 1 && scene.lines.isEmpty)
        let fit = try #require(scene.fit)
        #expect(fit.centerLatitude == 31.2304 && fit.centerLongitude == 121.4737)
        #expect(fit.latitudeSpan == LioTripMapRegion.minimumSpan && fit.longitudeSpan == LioTripMapRegion.minimumSpan)
    }

    @Test func daysAreNeverJoinedToEachOtherAndTheRegionHoldsEveryDay() throws {
        let scene = Self.scene([
            Self.day(1, [Self.point("a", 1, 39.90, 116.40), Self.point("b", 2, 39.92, 116.41)]),
            Self.day(2, [Self.point("c", 1, 40.43, 116.57), Self.point("d", 2, 39.93, 116.45)])
        ])
        #expect(scene.lines.map(\.dayNumber) == [1, 2])
        #expect(scene.lines.map(\.colorSlot) == [0, 1])
        let fit = try #require(scene.fit)
        for pin in scene.pins {
            #expect(abs(pin.coordinate.latitude - fit.centerLatitude) <= fit.latitudeSpan / 2)
            #expect(abs(pin.coordinate.longitude - fit.centerLongitude) <= fit.longitudeSpan / 2)
        }
        #expect(fit.latitudeSpan > 40.43 - 39.90)
        #expect(fit.latitudeSpan == (40.43 - 39.90) * LioTripMapRegion.padding)
    }

    @Test func repeatedCoordinatesKeepEveryPinAndDropOnlyTheZeroLengthLine() throws {
        // A hotel at both ends of the day, and the same hotel again on day 2.
        let scene = Self.scene([
            Self.day(1, [Self.point("h1", 1, 39.91, 116.41), Self.point("h1b", 2, 39.91, 116.41),
                         Self.point("x", 3, 39.95, 116.45)]),
            Self.day(2, [Self.point("h2", 1, 39.91, 116.41)])
        ])
        #expect(scene.pins.count == 4)
        #expect(scene.lines.map(\.key) == ["0-2-3"])
        let fit = try #require(scene.fit)
        #expect(fit.centerLatitude > 39.91 && fit.centerLatitude < 39.95)
        let same = Self.scene([Self.day(1, [Self.point("a", 1, 39.9, 116.4), Self.point("b", 2, 39.9, 116.4)])])
        #expect(same.pins.count == 2 && same.lines.isEmpty)
        #expect(same.fit?.latitudeSpan == LioTripMapRegion.minimumSpan)
        #expect(same.fit?.longitudeSpan == LioTripMapRegion.minimumSpan)
    }

    @Test func aRepeatedPointIDDoesNotMakeTwoPinsShareAnIdentity() {
        let scene = Self.scene([
            Self.day(1, [Self.point("same", 1, 39.90, 116.40), Self.point("same", 2, 39.92, 116.42)]),
            Self.day(2, [Self.point("same", 1, 39.95, 116.45)])
        ])
        #expect(Set(scene.pins.map(\.key)).count == 3)
        #expect(scene.pins.map(\.id) == ["same", "same", "same"])
    }

    // MARK: Leg labels on lines

    @Test func aLineCarriesTheLabelOfExactlyItsOwnLeg() {
        let scene = Self.scene([Self.day(1, [
            Self.point("a", 1, 39.90, 116.40), Self.point("b", 2, 39.92, 116.41),
            Self.point("c", 3, nil, nil), Self.point("d", 4, 39.95, 116.45)
        ], segments: [
            .init(fromID: "a", toID: "b", label: "Metro 25 min"),
            .init(fromID: "b", toID: "c", label: "Walk 5 min"),
            .init(fromID: "c", toID: "d", label: "Taxi 10 min")
        ])])
        // b and d are joined across the point without a position; neither leg describes that stretch.
        #expect(scene.lines.map(\.label) == ["Metro 25 min", nil])
    }

    @Test func emptyAndMissingLabelsStayLabelFree() {
        let scene = Self.scene([Self.day(1, [Self.point("a", 1, 39.9, 116.4), Self.point("b", 2, 39.92, 116.42)],
                                         segments: [.init(fromID: "a", toID: "b", label: "")])])
        #expect(scene.lines.first?.label == nil)
        #expect(Self.scene([Self.day(1, [Self.point("a", 1, 39.9, 116.4), Self.point("b", 2, 39.92, 116.42)])]).lines.first?.label == nil)
    }

    @Test func aLineMidpointIsBetweenItsEnds() throws {
        let line = try #require(Self.scene([Self.day(1, [Self.point("a", 1, 39.90, 116.40), Self.point("b", 2, 39.94, 116.44)])]).lines.first)
        #expect(abs(line.midpoint.latitude - 39.92) < 1e-9 && abs(line.midpoint.longitude - 116.42) < 1e-9)
    }

    // MARK: A replaceable map layer

    /// A map that is not MapKit: it only records what the page asks it to draw, and can "tap" a point.
    @MainActor private final class FakeLayer: LioTripMapLayer {
        var scenes: [LioTripMapScene] = []
        var selectedIDs: [String?] = []
        var select: (@MainActor (String) -> Void)?

        func content(scene: LioTripMapScene, selectedID: String?, select: @escaping @MainActor (String) -> Void) -> some View {
            scenes.append(scene)
            selectedIDs.append(selectedID)
            self.select = select
            return Text("fake map: \(scene.pins.count) pins")
        }

        func tap(_ id: String) { select?(id) }
    }

    @Test func thePageDrawsThroughWhateverLayerItIsGivenAndForwardsTaps() {
        let input = LioTripMapInput(days: [Self.day(1, [Self.point("a", 1, 39.90, 116.40), Self.point("b", 2, 39.92, 116.42)])])
        var selected: [String] = []
        let layer = FakeLayer()
        let page = LioTripMapView(input: input, language: .english, selectedPointID: "b", layer: layer) { selected.append($0) }

        _ = page.body
        #expect(layer.scenes == [LioTripMapScene(input, language: .english)])
        #expect(layer.selectedIDs == ["b"])

        layer.tap("a")
        layer.tap("b")
        #expect(selected == ["a", "b"])
    }

    @Test func twoDifferentLayersGetTheSameSceneAndEitherCanBeSwappedIn() {
        let input = LioTripMapInput(days: [Self.day(1, [Self.point("a", 1, 39.90, 116.40)])])
        let first = FakeLayer(), second = FakeLayer()
        var taps: [String] = []
        _ = LioTripMapView(input: input, language: .chinese, layer: first) { taps.append("first:" + $0) }.mapContent
        _ = LioTripMapView(input: input, language: .chinese, layer: second) { taps.append("second:" + $0) }.mapContent
        #expect(first.scenes == second.scenes && first.scenes.count == 1)
        first.tap("a")
        second.tap("a")
        #expect(taps == ["first:a", "second:a"])
    }

    @Test func theEmptyStateAndTheUnplacedListAreThePagesOwnAndDoNotNeedALayer() {
        let layer = FakeLayer()
        let page = LioTripMapView(input: LioTripMapInput(days: [Self.day(1, [Self.point("a", 1, nil, nil)])]),
                                  language: .english, layer: layer) { _ in }
        _ = page.body
        #expect(page.scene.isEmpty && page.scene.unplaced.count == 1)
        // Nothing is drawn when nothing can be placed: the layer is not asked for a map to show.
        #expect(layer.scenes.isEmpty)
    }

    // MARK: Saved plans

    @Test func aSavedPlanBecomesDaysOfNumberedPointsWithPositionsOnlyForMatchedPlaces() throws {
        let plan = LioPlanSummary(tripID: "t1", tripVersion: 1, source: .template, startDate: nil, itinerary: Self.itinerary([
            Self.richDay(1, [
                Self.stop("a", Self.place("天安门广场", "Tian'anmen Square", 39.9055, 116.3976)),
                Self.stop("b", Self.place("烤鸭店", "Roast duck", 39.9135, 116.4035, matched: false)),
                Self.stop("c", Self.place("故宫", "Palace Museum", 39.9163, 116.3972))
            ], legs: [Self.leg("a", "b", .walking, minutes: 12), Self.leg("b", "c", .transit, minutes: 25)]),
            Self.richDay(2, [Self.stop("d", Self.place("长城", "Great Wall", 40.4319, 116.5704))])
        ]))
        let input = LioTripMapInput(plan: plan, language: .chinese)
        #expect(input.days.map(\.number) == [1, 2])
        let first = input.days[0].points
        #expect(first.map(\.id) == ["a", "b", "c"])
        #expect(first.map(\.number) == [1, 2, 3])
        #expect(first.map(\.name) == ["天安门广场", "烤鸭店", "故宫"])
        #expect(first[0].coordinate == LioTripMapCoordinate(latitude: 39.9055, longitude: 116.3976))
        // A place the library did not confirm has no usable position, even if a point rides along.
        #expect(first[1].latitude == nil && first[1].longitude == nil && first[1].coordinate == nil)
        // GCJ-02 values go through exactly as stored.
        #expect(first[2].latitude == 39.9163 && first[2].longitude == 116.3972)
        #expect(input.days[0].segments == [
            .init(fromID: "a", toID: "b", label: "步行 12 分钟"),
            .init(fromID: "b", toID: "c", label: "公共交通 25 分钟")
        ])
        let english = LioTripMapInput(plan: plan, language: .english)
        #expect(english.days[0].points.map(\.name) == ["Tian'anmen Square", "Roast duck", "Palace Museum"])
        #expect(english.days[0].segments.map(\.label) == ["Walk 12 min", "Transit 25 min"])

        let scene = LioTripMapScene(input, language: .chinese)
        #expect(scene.pins.map(\.id) == ["a", "c", "d"])
        #expect(scene.unplaced.map(\.pointID) == ["b"])
        // a-c are joined without the unconfirmed place; no leg describes that stretch.
        #expect(scene.lines.map(\.label) == [nil])
    }

    @Test func aChatPlanSavedWithoutPlacesHasPointsButNoPositions() {
        let plan = LioPlanSummary(tripID: "chat", tripVersion: 2, title: "Beijing", startDate: nil, undated: true, days: [
            .init(number: 1, date: nil, items: [
                .init(id: "i1", label: "故宫", startTime: "09:00", endTime: nil, fixed: nil),
                .init(id: "i2", label: "景山", startTime: nil, endTime: nil, fixed: nil)
            ])
        ])
        let scene = LioTripMapScene(LioTripMapInput(plan: plan, language: .chinese), language: .chinese)
        #expect(scene.isEmpty && !scene.hasNoPoints)
        #expect(scene.unplaced.map(\.name) == ["故宫", "景山"])
        #expect(scene.unplaced.map(\.number) == [1, 2])
    }

    @Test func aPlanWithoutDaysIsAnEmptyInput() {
        let plan = LioPlanSummary(tripID: "empty", tripVersion: 0, source: .chat, startDate: nil, itinerary: Self.itinerary([]))
        let input = LioTripMapInput(plan: plan, language: .english)
        #expect(input.days.isEmpty && input.pointCount == 0)
    }

    @Test func legLabelsNameTheModeAndRoundTheTimeUpInBothLanguages() {
        func label(_ mode: LioRichItinerary.Leg.Mode?, _ minutes: Double, _ language: LioLanguage) -> String? {
            LioTripMapInput.legLabel(Self.leg("a", "b", mode, minutes: minutes), language: language)
        }
        #expect(label(.walking, 15, .english) == "Walk 15 min")
        #expect(label(.transit, 25, .chinese) == "公共交通 25 分钟")
        #expect(label(.taxi, 10.2, .chinese) == "打车 11 分钟")
        #expect(label(.taxi, 90, .english) == "Taxi 1 h 30 min")
        #expect(label(.taxi, 120, .chinese) == "打车 2 小时")
        #expect(label(nil, 0, .english) == nil)
        #expect(label(.walking, 0, .english) == nil)
        #expect(label(.walking, .nan, .english) == nil)
    }
}
