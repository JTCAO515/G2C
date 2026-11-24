import Foundation
import Testing
@testable import CJLioUser

/// #1454: the bundled METRO.1 map is validated once, then drawn and hit-tested from plain values.
@Suite struct LioMetroMapTests {
    private func file(lines: String, stations: String, version: String = "METRO.1",
                      source: String = #"{"name":"OpenStreetMap contributors","license":"ODbL-1.0","url":"https://www.openstreetmap.org/copyright"}"#) -> Data {
        Data(#"{"version":"\#(version)","city":"test","data_version":"t1","source":\#(source),"lines":[\#(lines)],"stations":[\#(stations)]}"#.utf8)
    }
    private func station(_ id: String, _ lat: Double, _ lng: Double, xy: (Double, Double)? = nil, system: String = "WGS-84") -> String {
        let position = xy.map { #","x":\#($0.0),"y":\#($0.1)"# } ?? ""
        return #"{"id":"\#(id)","name_zh":"站\#(id)","name_en":"Stop \#(id)","lat":\#(lat),"lng":\#(lng),"coordinate_system":"\#(system)"\#(position)}"#
    }

    @Test func schematicPositionsHitTestingAndInterchanges() throws {
        let map = try LioMetroMapWire.read(file(
            lines: #"{"id":"l1","name_zh":"1号线","name_en":"Line 1","color":"\u0023C8102E","stations":["a","b","c"]},{"id":"l2","name_zh":"2号线","name_en":"Line 2","color":"\u00230057B8","stations":["d","b"]}"#,
            stations: [station("a", 23.1, 113.2, xy: (0.1, 0.5)), station("b", 23.1, 113.3, xy: (0.5, 0.5)),
                       station("c", 23.1, 113.4, xy: (0.9, 0.5)), station("d", 23.2, 113.3, xy: (0.5, 0.1), system: "GCJ-02")]
                .joined(separator: ",")))
        let interchange = try #require(map.station("b"))
        #expect(interchange.isInterchange && interchange.lines == ["l1", "l2"])
        #expect(map.lines(at: interchange).map(\.id) == ["l1", "l2"])
        #expect(map.station(near: 0.52, 0.49, radius: 0.05)?.id == "b")
        #expect(map.station(near: 0.3, 0.3, radius: 0.05) == nil)
        #expect(map.station("d")?.referenceSystem == .gcj02 && map.station("a")?.referenceSystem == .wgs84)
        #expect(map.source.license == "ODbL-1.0")
    }

    @Test func coordinatesAreFittedIntoTheUnitSquareWithoutALayout() throws {
        let map = try LioMetroMapWire.read(file(
            lines: #"{"id":"l1","name_zh":"1号线","name_en":"Line 1","color":"\u0023000000","stations":["a","b","c"]}"#,
            stations: [station("a", 31.20, 121.40), station("b", 31.25, 121.45), station("c", 31.30, 121.50)].joined(separator: ",")))
        for item in map.stations { #expect((0...1).contains(item.x) && (0...1).contains(item.y)) }
        // North is up: the northernmost station has the smallest y.
        #expect(map.station("c")!.y < map.station("a")!.y)
        #expect(map.station("a")!.x < map.station("c")!.x)
    }

    @Test func malformedMapsAreRejected() {
        let ok = [station("a", 1, 1), station("b", 1, 2)].joined(separator: ",")
        let line = #"{"id":"l1","name_zh":"1号线","name_en":"Line 1","color":"\u0023123456","stations":["a","b"]}"#
        #expect(throws: LioMetroMapFailure.invalid("version")) { try LioMetroMapWire.read(file(lines: line, stations: ok, version: "METRO.2")) }
        #expect(throws: LioMetroMapFailure.invalid("source")) {
            try LioMetroMapWire.read(file(lines: line, stations: ok, source: #"{"name":"x","license":"y","url":"http://insecure.example"}"#))
        }
        let unknownStop = #"{"id":"l1","name_zh":"1号线","name_en":"Line 1","color":"\u0023123456","stations":["a","zz"]}"#
        #expect(throws: LioMetroMapFailure.invalid("line l1")) { try LioMetroMapWire.read(file(lines: unknownStop, stations: ok)) }
        let badColor = #"{"id":"l1","name_zh":"1号线","name_en":"Line 1","color":"red","stations":["a","b"]}"#
        #expect(throws: LioMetroMapFailure.invalid("line l1")) { try LioMetroMapWire.read(file(lines: badColor, stations: ok)) }
        let duplicate = [station("a", 1, 1), station("a", 1, 2)].joined(separator: ",")
        #expect(throws: LioMetroMapFailure.invalid("duplicate station")) { try LioMetroMapWire.read(file(lines: line, stations: duplicate)) }
        let offMap = [station("a", 1, 1, xy: (0.5, 1.5)), station("b", 1, 2, xy: (0.5, 0.5))].joined(separator: ",")
        #expect(throws: LioMetroMapFailure.invalid("station a")) { try LioMetroMapWire.read(file(lines: line, stations: offMap)) }
        #expect(throws: LioMetroMapFailure.unreadable) { try LioMetroMapWire.read(Data("{}".utf8)) }
    }

    #if DEBUG
    @Test func demoNetworkIsValidAndHasInterchanges() throws {
        let demo = try LioMetroMapWire.read(LioMetroMapPreview.json)
        #expect(demo.lines.count == 3 && demo.stations.count == 13)
        #expect(demo.stations.filter(\.isInterchange).map(\.id).sorted() == ["c", "e", "h", "j"])
    }
    #endif
}
