import Foundation
import SwiftUI
import Testing
@testable import CJLioUser

/// #1996 / #1995: the trip canvas drawn on the trip map: the same days, numbers and colours as the timeline.
@MainActor struct LioTripMapCanvasTests {
    private func input(_ canvas: LioTripCanvas = LioTripCanvas(plan: LioTripCanvasTests.plan()),
                       language: LioLanguage = .english) -> LioTripMapInput {
        LioTripMapInput(canvas: canvas, language: language)
    }

    @Test func daysPointsAndNumbersFollowTheTimeline() throws {
        let map = input()
        #expect(map.days.map(\.number) == [1, 2] && map.pointCount == 5)
        #expect(map.days[0].points.map(\.id) == ["a", "b", "c"] && map.days[0].points.map(\.number) == [1, 2, 3])
        #expect(map.days[1].points.map(\.id) == ["d", "e"] && map.days[1].points.map(\.number) == [1, 2])
        #expect(map.days[0].colorSlot != map.days[1].colorSlot)
    }

    @Test func coordinatesGoThroughUnchangedAndAMissingOneStaysMissing() throws {
        let points = input().days[0].points
        #expect(points[0].latitude == 39.9 && points[0].longitude == 116.4)       // GCJ-02, not converted
        #expect(points[1].latitude == 39.92)
        #expect(points[2].latitude == nil && points[2].coordinate == nil)         // not placed: listed under the map
    }

    @Test func namesFollowTheLanguage() {
        #expect(input(language: .english).days[0].points[0].name == "Tiananmen Square")
        #expect(input(language: .chinese).days[0].points[0].name == "天安门广场")
    }

    @Test func aLegBecomesALabelOnlyWhereTheCanvasHasAnEstimate() throws {
        let map = input()
        #expect(map.days[0].segments == [.init(fromID: "a", toID: "b", label: "Walk 10 min")])
        #expect(input(language: .chinese).days[0].segments.first?.label == "步行 10 分钟")
        #expect(map.days[1].segments.isEmpty)
    }

    @Test func legLabelsHandleModesHoursAndBadNumbers() {
        func label(_ mode: LioTripCanvas.Mode, _ seconds: Double, _ language: LioLanguage = .english) -> String? {
            LioTripMapInput.legLabel(.init(fromID: "a", toID: "b", mode: mode, seconds: seconds, metres: 1), language: language)
        }
        #expect(label(.transit, 1500) == "Transit 25 min" && label(.taxi, 5400) == "Taxi 1 h 30 min")
        #expect(label(.taxi, 5400, .chinese) == "打车 1 小时 30 分钟")
        #expect(label(.walking, 0) == nil && label(.walking, -5) == nil && label(.walking, .nan) == nil && label(.walking, .infinity) == nil)
    }

    @Test func daysAreNumberedAcrossCitySegments() throws {
        var canvas = LioTripCanvas(plan: LioTripCanvasTests.plan())
        let second = LioTripCanvas.Segment(id: "segment-2", name: "Shanghai", days: [
            .init(id: "day-s2-1", date: nil, theme: "", area: "", points: [
                .init(id: "x", placeID: nil, nameZH: "外滩", nameEN: "The Bund", address: nil,
                      coordinate: .init(latitude: 31.24, longitude: 121.49), time: nil, kind: .sight, origin: .user),
            ]),
        ])
        canvas.segments.append(second)
        let map = input(canvas)
        #expect(map.days.map(\.number) == [1, 2, 3] && map.days[2].points.first?.id == "x" && map.days[2].points.first?.latitude == 31.24)
        #expect(Set(map.days.map(\.colorSlot)).count == 3)
    }

    @Test func theWantToGoInboxIsNotOnTheMap() {
        var canvas = LioTripCanvas(plan: LioTripCanvasTests.plan())
        canvas.wishlist = [.init(id: "w", placeID: nil, nameZH: "颐和园", nameEN: "Summer Palace", address: nil,
                                 coordinate: .init(latitude: 40.0, longitude: 116.27), time: nil, kind: .sight, origin: .user)]
        #expect(!input(canvas).days.flatMap(\.points).contains { $0.id == "w" })
    }

    @Test func anEmptyCanvasGivesAnEmptyMapAndABadCoordinateIsNotAPin() {
        #expect(input(LioTripCanvas(emptyTripID: "local")).pointCount == 0)
        var canvas = LioTripCanvas(emptyTripID: "local")
        canvas.segments[0].days = [.init(id: "d", date: nil, theme: "", area: "", points: [
            .init(id: "bad", placeID: nil, nameZH: "错", nameEN: "Bad", address: nil,
                  coordinate: .init(latitude: 400, longitude: 0), time: nil, kind: .sight, origin: .user),
        ])]
        #expect(input(canvas).days[0].points[0].coordinate == nil)               // outside -90...90: listed, not drawn
    }

    /// A stand-in for MapKit (which only the iOS build has): the canvas page depends on the layer protocol only.
    private struct RecordingLayer: LioTripMapLayer {
        func content(scene: LioTripMapScene, selectedID: String?, select: @escaping @MainActor (String) -> Void) -> some View {
            Text("pins:\(scene.pins.count)")
        }
    }

    @Test func theMapPageTakesAnyLayerAndOnlyPlacedPointsArePins() {
        let canvas = LioTripCanvas(plan: LioTripCanvasTests.plan())
        let page = LioTripCanvasMapView(canvas: canvas, language: .english, layer: RecordingLayer())
        #expect(page.canvas == canvas)
        let scene = LioTripMapScene(input(canvas), language: .english)
        #expect(scene.pins.count == 2)                                                // a and b have positions; c is listed below
        #expect(scene.unplaced.map(\.pointID).contains("c"))
    }
}
