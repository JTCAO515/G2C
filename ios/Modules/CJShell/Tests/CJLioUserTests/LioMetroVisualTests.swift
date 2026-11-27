import Foundation
import Testing
@testable import CJLioUser

/// #2008: the map opens on the city centre, lines carry the operators' own colours, and stations can be paired
/// with places from the curated library.
struct LioMetroVisualTests {
    @Test func bigNetworksOpenOnTheirCentreAndSmallOnesWhole() throws {
        for city in LioMetroCity.allCases {
            let map = try LioMetroMap.bundled(city)
            let focus = map.centreFocus
            if map.stations.count < LioMetroMap.centreFocusMinimumStations {
                #expect(focus == nil, "\(city.id)")
            } else {
                let found = try #require(focus, "\(city.id)")
                #expect((0...map.width).contains(found.x) && (0...map.height).contains(found.y), "\(city.id)")
                #expect(found.zoom > 1)
            }
        }
    }

    @Test func theNamedCentresExistInTheirMaps() throws {
        for (id, names) in LioMetroMap.centreStations {
            let map = try LioMetroMap.bundled(try #require(LioMetroCity.named(id)))
            for name in names {
                #expect(map.stations.contains { $0.nameZH == name }, "\(id) \(name)")
            }
        }
        // The six cities C5 named all have a centre, and Shanghai's lies between People's Square and Lujiazui.
        #expect(Set(LioMetroMap.centreStations.keys) == ["beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", "chongqing"])
        let shanghai = try LioMetroMap.bundled(.shanghai)
        let focus = try #require(shanghai.centreFocus)
        let square = try #require(shanghai.stations.first { $0.nameZH == "人民广场" })
        let lujiazui = try #require(shanghai.stations.first { $0.nameZH == "陆家嘴" })
        #expect(focus.x > min(square.x, lujiazui.x) && focus.x < max(square.x, lujiazui.x))
    }

    #if canImport(CoreGraphics)
    @Test func theOpeningViewportCentresTheFocus() throws {
        let map = try LioMetroMap.bundled(.beijing)
        let focus = try #require(map.centreFocus)
        let view = CGSize(width: 390, height: 700)
        let viewport = LioMetroViewport.opening(on: focus, map: map, view: view)
        #expect(viewport.zoom == CGFloat(focus.zoom))
        // The focus point lands within a few points of the view's centre.
        let fit = min(view.width / map.width, view.height / map.height)
        let scale = fit * viewport.zoom
        let x = view.width / 2 + (focus.x - map.width / 2) * scale + viewport.pan.width
        let y = view.height / 2 + (focus.y - map.height / 2) * scale + viewport.pan.height
        #expect(abs(x - view.width / 2) < 1 && abs(y - view.height / 2) < 1)
        // A view with no size falls back to the whole map instead of dividing by zero.
        #expect(LioMetroViewport.opening(on: focus, map: map, view: .zero) == LioMetroViewport())
    }
    #endif

    @Test func linesUseTheOperatorsOwnColours() throws {
        func colour(_ city: LioMetroCity, _ nameZH: String) throws -> String {
            try #require(try LioMetroMap.bundled(city).lines.first { $0.nameZH == nameZH }).color
        }
        // C5 line-colour table (operators' own pages, 2026-11-27).
        #expect(try colour(.beijing, "13号线") == "#F9E700")
        #expect(try colour(.shanghai, "2号线") == "#82BF25")
        #expect(try colour(.shanghai, "3号线") == "#FCD600")
        #expect(try colour(.guangzhou, "5号线") == "#C70541")
        #expect(try colour(.shenzhen, "2号线") == "#B75020")
        #expect(try colour(.shenzhen, "8号线") == "#B75020")
        #expect(try colour(LioMetroCity.named("chongqing")!, "9号线") == "#9A3334")
        #expect(try colour(LioMetroCity.named("chongqing")!, "环线") == "#DAC17C")
        // Chengdu publishes no text colours: its existing colours stay (C5: keep them where the table is empty).
        #expect(try colour(LioMetroCity.named("chengdu")!, "1号线") == "#2249A3")
    }

    @Test func stationPlaceLinksAreCheckedAtTheBoundary() throws {
        let good = Data(#"{"schema":"lio.metro.places.v1","links":[{"city":"beijing","station":"bj001","place":"pl_bj_tiananmen"}]}"#.utf8)
        let places = try LioMetroStationPlaces.read(good)
        #expect(places.place(city: "beijing", station: "bj001") == "pl_bj_tiananmen")
        #expect(places.place(city: "beijing", station: "bj002") == nil)
        for bad in [
            #"{"schema":"x","links":[]}"#,
            #"{"schema":"lio.metro.places.v1","links":[{"city":"beijing","station":"a","place":"Tiananmen"}]}"#,
            #"{"schema":"lio.metro.places.v1","links":[{"city":"beijing","station":"a","place":"pl_bj_a"},{"city":"beijing","station":"a","place":"pl_bj_b"}]}"#,
        ] {
            #expect(throws: LioMetroStationPlaces.Failure.self) { _ = try LioMetroStationPlaces.read(Data(bad.utf8)) }
        }
        #expect(throws: LioMetroStationPlaces.Failure.unreadable) { _ = try LioMetroStationPlaces.read(Data("[]".utf8)) }
    }

    @Test func everyBundledLinkPointsAtARealStation() throws {
        for link in LioMetroStationPlaces.bundled.links {
            let city = try #require(LioMetroCity.named(link.city), "\(link.city)")
            let map = try LioMetroMap.bundled(city)
            #expect(map.station(link.station) != nil, "\(link.city) \(link.station)")
        }
    }
}
