import Foundation
import Testing
@testable import CJLioUser

/// #1450 item 2: the bundled maps for Beijing, Shanghai and Guangzhou are complete and consistent.
struct LioMetroMapDataTests {
    static let mapped: [LioMetroCity] = [.beijing, .shanghai, .guangzhou]

    @Test func onlyCitiesWithCheckedDataHaveAMap() throws {
        #expect(LioMetroCity.allCases.filter { $0.mapResource != nil } == Self.mapped)
        #expect(throws: LioMetroMapFailure.missing) { try LioMetroMap.bundled(.chengdu) }
    }

    @Test(arguments: mapped)
    func everyLineHasStationsInBothLanguagesAndAnOfficialColour(city: LioMetroCity) throws {
        let map = try LioMetroMap.bundled(city)
        #expect(map.city == city)
        #expect(map.lines.count >= 18)
        #expect(map.stations.count >= 300)
        for line in map.lines {
            #expect(LioMetroMap.isColor(line.color), "\(line.id)")
            #expect(!line.nameZH.isEmpty && !line.nameEN.isEmpty)
            #expect(line.segments.allSatisfy { $0.count >= 2 })
            #expect(line.edges.allSatisfy { map.station($0.0) != nil && map.station($0.1) != nil })
        }
        for station in map.stations {
            #expect(!station.nameZH.isEmpty && !station.nameEN.isEmpty, "\(station.id)")
            #expect(station.nameEN == station.nameEN.trimmingCharacters(in: .whitespaces))
            #expect(!station.nameEN.contains("  "))
            #expect(!station.lines.isEmpty)
            #expect((0...map.width).contains(station.x) && (0...map.height).contains(station.y))
        }
    }

    /// Interchanges agree both ways: a station names every line that lists it, and only those.
    @Test(arguments: mapped)
    func interchangesAgreeInBothDirections(city: LioMetroCity) throws {
        let map = try LioMetroMap.bundled(city)
        for station in map.stations {
            for line in map.lines(at: station) {
                #expect(line.segments.joined().contains(station.id), "\(station.nameZH) \(line.id)")
            }
        }
        for line in map.lines {
            for id in Set(line.segments.joined()) {
                #expect(map.station(id)?.lines.contains(line.id) == true, "\(line.id) \(id)")
            }
        }
        // Every line connects to the rest of the network through at least one interchange.
        for line in map.lines where map.lines.count > 1 {
            #expect(line.segments.joined().contains { map.station($0)?.isInterchange == true }, "\(line.id)")
        }
    }

    @Test(arguments: mapped)
    func sourceNamesTheOperatorSiteAndCheckDay(city: LioMetroCity) throws {
        let map = try LioMetroMap.bundled(city)
        #expect(map.source.checkedOn == "2026-11-24")
        #expect(map.source.urls.allSatisfy { $0.scheme == "https" })
        let hosts = Set(map.source.urls.compactMap(\.host))
        switch city {
        case .beijing: #expect(hosts == ["map.bjsubway.com", "map_en.bjsubway.com"])
        case .shanghai: #expect(hosts == ["service.shmetro.com"])
        case .guangzhou: #expect(hosts == ["wx.gzmtr.com", "cs.gzmtr.com"])
        case .chengdu: Issue.record("no map")
        }
        #expect(map.sourceLine(in: .english).contains("checked 24 Nov 2026"))
        #expect(map.sourceLine(in: .chinese).contains("核对于2026年11月24日"))
    }

    /// Spot checks against the operators' sites on the check day.
    @Test func wellKnownInterchangesMatchTheOperators() throws {
        func lines(_ city: LioMetroCity, _ name: String) throws -> [String] {
            let map = try LioMetroMap.bundled(city)
            let station = try #require(map.stations.first { $0.nameZH == name }, "\(name)")
            return map.lines(at: station).map(\.nameZH)
        }
        #expect(try lines(.beijing, "西直门") == ["2号线", "4号线大兴线", "13号线"])
        #expect(try lines(.shanghai, "人民广场") == ["1号线", "2号线", "8号线"])
        #expect(try lines(.shanghai, "世纪大道") == ["2号线", "4号线", "6号线", "9号线"])
        #expect(try lines(.guangzhou, "体育西路") == ["1号线", "3号线"])
        #expect(try lines(.guangzhou, "广州南站") == ["2号线", "7号线", "22号线"])
        let guangzhou = try LioMetroMap.bundled(.guangzhou)
        #expect(guangzhou.stations.first { $0.nameZH == "广州南站" }?.nameEN == "Guangzhou South Railway Station")
    }

    @Test func loopsCloseAndBranchesShareTheirJunction() throws {
        let beijing = try LioMetroMap.bundled(.beijing)
        let line2 = try #require(beijing.line("bj-02"))
        #expect(line2.loop && line2.edges.count == line2.segments[0].count)
        let shanghai = try LioMetroMap.bundled(.shanghai)
        let line10 = try #require(shanghai.line("sh-10"))
        #expect(line10.segments.count == 2)
        #expect(shanghai.station(line10.segments[1].last!)?.nameZH == "龙溪路")
        let guangzhou = try LioMetroMap.bundled(.guangzhou)
        #expect(guangzhou.line("gz-11")?.loop == true)
    }
}

struct LioMetroMapBehaviourTests {
    private static func file(_ edit: (inout [String: Any]) -> Void = { _ in }) throws -> Data {
        var object: [String: Any] = [
            "schema": "lio.metro.v1", "city": "beijing",
            "source": ["operatorZH": "北京地铁", "operatorEN": "Beijing Subway",
                       "urls": ["https://map.bjsubway.com/"], "checkedOn": "2026-11-24"],
            "canvas": ["width": 200, "height": 100],
            "lines": [["id": "a", "nameZH": "1号线", "nameEN": "Line 1", "color": "#C23A30", "loop": false,
                       "segments": [["s1", "s2"]]],
                      ["id": "b", "nameZH": "2号线", "nameEN": "Line 2", "color": "#006098", "loop": false,
                       "segments": [["s2", "s3"]]]],
            "stations": [["id": "s1", "nameZH": "苹果园", "nameEN": "Pingguoyuan", "x": 10, "y": 10, "lines": ["a"]],
                         ["id": "s2", "nameZH": "复兴门", "nameEN": "Fuxingmen", "x": 100, "y": 50, "lines": ["a", "b"]],
                         ["id": "s3", "nameZH": "长椿街", "nameEN": "Changchunjie", "x": 100, "y": 90, "lines": ["b"]]],
        ]
        edit(&object)
        return try JSONSerialization.data(withJSONObject: object)
    }

    @Test func readsAValidFileAndFindsTheNearestStation() throws {
        let map = try LioMetroMap.read(Self.file(), city: .beijing)
        #expect(map.station(nearX: 96, y: 52, radius: 10)?.nameZH == "复兴门")
        #expect(map.station(nearX: 150, y: 10, radius: 10) == nil)
        #expect(map.station("s2")?.isInterchange == true)
        #expect(map.stations(matching: "fuxing").map(\.id) == ["s2"])
        #expect(map.stations(matching: "苹果").map(\.id) == ["s1"])
        #expect(map.stations(matching: "").first?.id == "s2") // interchanges first
        #expect(map.searchName(for: map.station("s1")!) == "苹果园地铁站")
    }

    @Test func rejectsBrokenFiles() throws {
        #expect(throws: LioMetroMapFailure.unreadable) { try LioMetroMap.read(Data("{}".utf8), city: .beijing) }
        #expect(throws: LioMetroMapFailure.invalid("city")) { try LioMetroMap.read(Self.file(), city: .shanghai) }
        #expect(throws: LioMetroMapFailure.invalid("source")) {
            try LioMetroMap.read(Self.file { $0["source"] = ["operatorZH": "x", "operatorEN": "x",
                                                             "urls": ["http://example.com"], "checkedOn": "2026-11-24"] },
                                 city: .beijing)
        }
        // A colour that is not #RRGGBB.
        #expect(throws: LioMetroMapFailure.invalid("line a")) {
            try LioMetroMap.read(Self.file { object in
                var lines = object["lines"] as! [[String: Any]]
                lines[0]["color"] = "red"
                object["lines"] = lines
            }, city: .beijing)
        }
        // An interchange that only one side knows about.
        #expect(throws: LioMetroMapFailure.invalid("station lines s2")) {
            try LioMetroMap.read(Self.file { object in
                var stations = object["stations"] as! [[String: Any]]
                stations[1]["lines"] = ["a"]
                object["stations"] = stations
            }, city: .beijing)
        }
        // A missing English name.
        #expect(throws: LioMetroMapFailure.invalid("station s3")) {
            try LioMetroMap.read(Self.file { object in
                var stations = object["stations"] as! [[String: Any]]
                stations[2]["nameEN"] = " "
                object["stations"] = stations
            }, city: .beijing)
        }
        // A line that lists a station the file does not have.
        #expect(throws: LioMetroMapFailure.invalid("line b")) {
            try LioMetroMap.read(Self.file { object in
                var lines = object["lines"] as! [[String: Any]]
                lines[1]["segments"] = [["s2", "s9"]]
                object["lines"] = lines
            }, city: .beijing)
        }
    }

    @Test func taxiPicksTheStationResultAndDirectionsSearchByName() {
        let station = LioMetroMap.Station(id: "s", nameZH: "体育西路", nameEN: "Tiyu Xilu", x: 0, y: 0, lines: ["a"])
        let coordinate = LioTaxiPlace.Coordinate(latitude: 23.13, longitude: 113.32, referenceSystem: .gcj02)
        let mall = LioTaxiPlace(nameZH: "体育西路商场", nameEN: "Mall", addressZH: nil, coordinate: coordinate)
        let stop = LioTaxiPlace(nameZH: "体育西路(地铁站)", nameEN: "Tiyu Xilu Station", addressZH: nil, coordinate: coordinate)
        #expect(LioMetroStationAction.bestPlace([mall, stop], for: station) == stop)
        #expect(LioMetroStationAction.bestPlace([], for: station) == nil)
        let urls = LioMetroStationAction.directionURLs(cityZH: "广州", name: "体育西路地铁站")
        #expect(urls.map(\.scheme) == ["iosamap", "https"])
        #expect(urls[0].absoluteString.contains("poi?sourceApplication=Go2China"))
        let name = URLComponents(url: urls[0], resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "name" }?.value
        #expect(name == "广州体育西路地铁站")
    }
}
