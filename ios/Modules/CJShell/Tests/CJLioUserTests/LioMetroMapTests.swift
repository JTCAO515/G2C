import Foundation
import Testing
@testable import CJLioUser

/// #1450 item 2: every bundled map is complete and consistent.
struct LioMetroMapDataTests {
    static let mapped: [LioMetroCity] = LioMetroCity.allCases
    /// Built from the operator's own data; the rest from AMap's network maps (JT 2026-11-25).
    static let fromOperators: Set<String> = ["beijing", "shanghai", "guangzhou", "shenzhen", "xian"]

    @Test func everyListedCityHasAMap() throws {
        // The operator-built cities stay; any AMap-based city can be removed by deleting its file.
        #expect(Self.fromOperators.isSubset(of: Set(Self.mapped.map(\.id))))
        for city in Self.mapped { #expect(throws: Never.self) { try LioMetroMap.bundled(city) } }
    }

    @Test(arguments: mapped)
    func everyLineHasStationsInBothLanguagesAndAnOfficialColour(city: LioMetroCity) throws {
        let map = try LioMetroMap.bundled(city)
        #expect(map.city == city)
        #expect(map.lines.count >= 2)
        #expect(map.stations.count >= 25)
        #expect(Set(map.lines.map(\.nameZH)).count == map.lines.count) // a branch is a segment, not a second line
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
            // No capital inside a word ("ShaTian"): the operators' own style capitalises words only.
            #expect(station.nameEN.range(of: "[a-z][A-Z]", options: .regularExpression) == nil, "\(station.nameEN)")
            // Names we generate (not an operator's own, like Beijing's "Sihui Dong(E)"): words start with a
            // capital and a bracket stands apart, "Chengdu Yixueyuan (Xindu Xiaoqu)".
            if map.source.provider != nil {
                #expect(station.nameEN.range(of: #"^[a-z]|\S\(|\(\s*[a-z]|Railway$"#, options: .regularExpression) == nil,
                        "\(station.nameEN)")
            }
        }
        // Two stations never share an English name (Shenzhen's file once gave Buyong its neighbour's).
        let english = map.stations.map { $0.nameEN.lowercased() }
        #expect(Set(english).count == english.count)
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
        // Lines connect through interchanges. Some real lines stand alone (Suzhou's Line 11 meets
        // Shanghai's, not Suzhou's), so only the operator-built maps require it of every line.
        #expect(map.stations.contains { $0.isInterchange })
        if Self.fromOperators.contains(city.id) {
            for line in map.lines where map.lines.count > 1 {
                #expect(line.segments.joined().contains { map.station($0)?.isInterchange == true }, "\(line.id)")
            }
        }
    }

    @Test(arguments: mapped)
    func sourceNamesWhereTheMapCameFromAndTheCheckDay(city: LioMetroCity) throws {
        let map = try LioMetroMap.bundled(city)
        let early: Set<String> = ["beijing", "shanghai", "guangzhou"]
        #expect(map.source.checkedOn == (early.contains(city.id) ? "2026-11-24" : "2026-11-25"))
        #expect(map.source.urls.allSatisfy { $0.scheme == "https" })
        let hosts = Set(map.source.urls.compactMap(\.host))
        switch city.id {
        case "beijing": #expect(hosts == ["map.bjsubway.com", "map_en.bjsubway.com"])
        case "shanghai": #expect(hosts == ["service.shmetro.com"])
        case "guangzhou": #expect(hosts == ["wx.gzmtr.com", "cs.gzmtr.com"])
        case "shenzhen": #expect(hosts == ["www.szmc.net"])
        case "xian": #expect(hosts == ["m.xianrail.com"])
        default:
            // Made from AMap's network maps into our own bundled map, and the page says so.
            #expect(hosts == ["www.amap.com"])
            #expect(map.source.provider?.nameZH == "高德地图地铁线网图")
            #expect(map.sourceLine(in: .english).contains("based on AMap metro network maps"))
            #expect(map.sourceLine(in: .chinese).contains("参考高德地图地铁线网图"))
        }
        #expect((map.source.provider != nil) == !Self.fromOperators.contains(city.id))
        // English names come from the operator except where it publishes none (#1450, JT 2026-11-25).
        #expect((map.source.english == nil) == ["beijing", "shanghai", "guangzhou", "shenzhen"].contains(city.id))
        if map.source.english != nil {
            #expect(map.sourceLine(in: .english).contains("English names:"))
            #expect(map.sourceLine(in: .chinese).contains("英文站名："))
        }
        let day = early.contains(city.id) ? 24 : 25
        #expect(map.sourceLine(in: .english).contains("checked \(day) Nov 2026"))
        #expect(map.sourceLine(in: .chinese).contains("核对于2026年11月\(day)日"))
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
        #expect(try lines(.shenzhen, "车公庙") == ["1号线", "7号线", "9号线", "11号线"])
        #expect(try lines(.shenzhen, "深圳北") == ["4号线", "5号线", "6号线"])
        #expect(try lines(.xian, "钟楼") == ["2号线", "6号线"])
        #expect(try lines(.xian, "北大街") == ["1号线", "2号线"])
        let xian = try LioMetroMap.bundled(.xian)
        #expect(xian.line("xa-8")?.loop == true)
        #expect(xian.stations.first { $0.nameZH == "钟楼" }?.nameEN == "Zhonglou")
        let shenzhen = try LioMetroMap.bundled(.shenzhen)
        #expect(shenzhen.stations.first { $0.nameZH == "步涌" }?.nameEN == "Buyong")
        let guangzhou = try LioMetroMap.bundled(.guangzhou)
        #expect(guangzhou.stations.first { $0.nameZH == "广州南站" }?.nameEN == "Guangzhou South Railway Station")
        // Cities added in batches: checked while bundled, so removing one needs no test change.
        let spotChecks: [(String, String, [String])] = [
            ("chengdu", "天府广场", ["1号线", "2号线"]), ("tianjin", "西站", ["1号线", "4号线", "6号线"]), ("nanjing", "新街口", ["1号线", "2号线"]),
            ("wuhan", "洪山广场", ["2号线", "4号线"]), ("chongqing", "小什字", ["1号线", "6号线"]),
            ("hangzhou", "武林广场", ["1号线", "3号线"]), ("shenyang", "青年大街", ["1号线", "2号线"]),
            ("shijiazhuang", "新百广场", ["1号线", "3号线"]), ("taiyuan", "大南门", ["1号线", "2号线"]),
            ("huhehaote", "新华广场", ["1号线", "2号线"]), ("zhengzhou", "郑州大学", ["1号线", "8号线"]),
            ("luoyang", "解放路", ["1号线", "2号线"]), ("jinan", "王府庄", ["1号线", "2号线"]),
        ]
        for (id, station, expected) in spotChecks {
            guard let city = LioMetroCity.named(id) else { continue }
            #expect(try lines(city, station) == expected, "\(id) \(station)")
        }
        if let chongqing = LioMetroCity.named("chongqing") {
            #expect(try LioMetroMap.bundled(chongqing).stations.first { $0.nameZH == "鱼嘴" }?.nameEN == "Yuzui")
        }
    }

    /// #1450 look: schematic rivers drawn behind the lines, only where the city has one worth showing.
    @Test func schematicWaterIsNamedAndInsideTheMap() throws {
        let guangzhou = try LioMetroMap.bundled(.guangzhou), shanghai = try LioMetroMap.bundled(.shanghai)
        #expect(guangzhou.water.map(\.nameZH) == ["珠江"])
        #expect(shanghai.water.map(\.nameEN) == ["Huangpu River"])
        #expect(try LioMetroMap.bundled(.beijing).water.isEmpty)
        #expect(try LioMetroMap.bundled(.shenzhen).water.isEmpty)
        #expect(try LioMetroMap.bundled(.xian).water.isEmpty)
        for map in [guangzhou, shanghai] {
            for water in map.water {
                #expect(water.points.count >= 8)
                #expect(water.points.allSatisfy { (0...map.width).contains($0.x) && (0...map.height).contains($0.y) })
            }
        }
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
        // Water outside the map, or with a single point.
        #expect(throws: LioMetroMapFailure.invalid("water 江")) {
            try LioMetroMap.read(Self.file { $0["water"] = [["nameZH": "江", "nameEN": "River", "points": [[10, 10], [500, 10]]]] },
                                 city: .beijing)
        }
        #expect(throws: LioMetroMapFailure.invalid("water 江")) {
            try LioMetroMap.read(Self.file { $0["water"] = [["nameZH": "江", "nameEN": "River", "points": [[10, 10]]]] },
                                 city: .beijing)
        }
        #expect(try LioMetroMap.read(Self.file { $0["water"] = [["nameZH": "江", "nameEN": "River",
                                                                 "points": [[10, 10], [150, 60]]]] },
                                     city: .beijing).water.first?.points.count == 2)
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

/// Zoom and pan: gestures are drawn on top of a committed viewport and commit only when they end.
struct LioMetroViewportTests {
    private static func close(_ a: CGSize, _ b: CGSize) -> Bool {
        abs(a.width - b.width) < 1e-9 && abs(a.height - b.height) < 1e-9
    }

    @Test func pinchKeepsThePointUnderTheFingersStill() {
        let start = LioMetroViewport(zoom: 2, pan: CGSize(width: 30, height: -10))
        let anchor = CGPoint(x: 80, y: 40)
        let end = start.pinched(by: 1.5, about: anchor)
        #expect(end.zoom == 3)
        // A map point drawn at the anchor before the pinch is still drawn there afterwards.
        let before = (x: (anchor.x - start.pan.width) / start.zoom, y: (anchor.y - start.pan.height) / start.zoom)
        let after = (x: (anchor.x - end.pan.width) / end.zoom, y: (anchor.y - end.pan.height) / end.zoom)
        #expect(abs(before.x - after.x) < 1e-9 && abs(before.y - after.y) < 1e-9)
    }

    @Test func zoomStaysBetweenTheWholeMapAndTheMaximum() {
        #expect(LioMetroViewport().pinched(by: 0.2, about: .zero).zoom == 1)
        #expect(LioMetroViewport(zoom: 10).pinched(by: 5, about: .zero).zoom == LioMetroViewport.maximumZoom)
    }

    /// The case review found: a pinch that ends while the drag is still live, then the drag ends.
    @Test func endingOneGestureBeforeTheOtherNeverMovesThePicture() {
        let committed = LioMetroViewport(zoom: 1.5, pan: CGSize(width: -40, height: 25))
        let anchor = CGPoint(x: -60, y: 90), drag = CGSize(width: 33, height: -18)
        let onScreen = committed.showing(magnification: 2, anchor: anchor, drag: drag)

        // Pinch lifts first; the drag is still live, so the picture is the new viewport plus that drag.
        let afterPinch = committed.endingPinch(by: 2, about: anchor, liveDrag: drag)
        let stillDragging = afterPinch.showing(magnification: nil, anchor: .zero, drag: drag)
        #expect(stillDragging.zoom == onScreen.zoom && Self.close(stillDragging.pan, onScreen.pan))
        // Then the drag lifts and commits; nothing moves.
        let afterDrag = afterPinch.dragged(by: drag)
        #expect(afterDrag.zoom == onScreen.zoom && Self.close(afterDrag.pan, onScreen.pan))

        // Drag lifts first instead; the live pinch is drawn on the moved viewport, then commits.
        let dragFirst = committed.dragged(by: drag)
        let stillPinching = dragFirst.showing(magnification: 2, anchor: anchor, drag: .zero)
        #expect(stillPinching.zoom == onScreen.zoom && Self.close(stillPinching.pan, onScreen.pan))
        let bothDone = dragFirst.endingPinch(by: 2, about: anchor, liveDrag: .zero)
        #expect(bothDone.zoom == onScreen.zoom && Self.close(bothDone.pan, onScreen.pan))
    }

    @Test func aCancelledGestureLeavesTheCommittedViewport() {
        let committed = LioMetroViewport(zoom: 3, pan: CGSize(width: 12, height: 8))
        // While live the gesture is drawn on top; once cancelled nothing was committed.
        #expect(committed.showing(magnification: 1.7, anchor: CGPoint(x: 5, y: 5), drag: CGSize(width: 9, height: 9)) != committed)
        #expect(committed.showing(magnification: nil, anchor: .zero, drag: .zero) == committed)
    }

    @Test func panKeepsPartOfTheMapOnScreen() {
        let view = CGSize(width: 400, height: 800), content = CGSize(width: 400, height: 300)
        let far = LioMetroViewport(zoom: 2, pan: CGSize(width: 5000, height: -5000)).clamped(content: content, view: view)
        #expect(far.pan == CGSize(width: 200 + 100, height: -200))
        let near = LioMetroViewport(zoom: 2, pan: CGSize(width: 50, height: 20))
        #expect(near.clamped(content: content, view: view) == near)
    }
}
