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
            // A station never follows itself (AMap once listed Zhengzhou's 新郑机场 twice in a row).
            #expect(line.segments.allSatisfy { segment in zip(segment, segment.dropFirst()).allSatisfy { $0 != $1 } },
                    "\(line.id)")
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
    /// Station surroundings (#1450, JT 2026-11-25) search around each station's real position. Every
    /// station of a map built from AMap's network data has one; the operator-built maps list a few newer
    /// stations AMap does not have yet. Positions sit near their city and neighbours along a line are close,
    /// which catches a position matched to the wrong station.
    @Test(arguments: mapped)
    func stationsHaveTheirRealPositions(city: LioMetroCity) throws {
        let map = try LioMetroMap.bundled(city)
        let placed = map.stations.compactMap(\.geo)
        if map.source.provider != nil {
            #expect(placed.count == map.stations.count, "\(city.id)")
        } else {
            #expect(Double(placed.count) >= 0.95 * Double(map.stations.count), "\(city.id)")
        }
        func km(_ a: LioTaxiPlace.Coordinate, _ b: LioTaxiPlace.Coordinate) -> Double {
            let dLat = (b.latitude - a.latitude) * .pi / 180, dLng = (b.longitude - a.longitude) * .pi / 180
            let h = sin(dLat / 2) * sin(dLat / 2)
                + cos(a.latitude * .pi / 180) * cos(b.latitude * .pi / 180) * sin(dLng / 2) * sin(dLng / 2)
            return 2 * 6371 * asin(sqrt(h))
        }
        let centre = LioTaxiPlace.Coordinate(latitude: placed.map(\.latitude).sorted()[placed.count / 2],
                                             longitude: placed.map(\.longitude).sorted()[placed.count / 2],
                                             referenceSystem: .gcj02)
        for station in map.stations {
            guard let geo = station.geo else { continue }
            #expect(geo.referenceSystem == .gcj02)
            #expect(km(geo, centre) < 150, "\(city.id) \(station.nameZH)")
        }
        for line in map.lines {
            for (a, b) in line.edges {
                guard let p = map.station(a)?.geo, let q = map.station(b)?.geo else { continue }
                #expect(km(p, q) < 60, "\(city.id) \(line.nameZH) \(a)–\(b)")
            }
        }
    }

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
            ("zhengzhou", "南四环", ["2号线", "城郊线"]),
            ("dalian", "西安路", ["1号线", "2号线"]), ("changchun", "人民广场", ["1号线", "5号线"]),
            ("haerbin", "博物馆", ["1号线", "2号线"]), ("lanzhou", "东方红广场", ["1号线", "2号线"]),
            ("wulumuqi", "南门", ["1号线", "2号线"]),
            ("wuxi", "三阳广场", ["1号线", "2号线"]), ("xuzhou", "彭城广场", ["1号线", "2号线"]),
            ("changzhou", "文化宫", ["1号线", "2号线"]), ("suzhou", "乐桥", ["1号线", "4号线"]),
            ("nantong", "文峰", ["1号线", "2号线"]),
            ("ningbo", "鼓楼", ["1号线", "2号线"]), ("shaoxing", "梅山广场", ["1号线", "2号线"]),
            ("hefei", "合肥南站", ["1号线", "4号线", "5号线"]), ("fuzhou", "东街口", ["1号线", "4号线"]),
            ("xiamen", "吕厝", ["1号线", "2号线"]), ("nanchang", "八一广场", ["1号线", "2号线"]),
            ("qingdao", "青岛北站", ["1号线", "3号线", "8号线"]), ("hangzhou", "奥体中心", ["6号线", "7号线"]),
            ("changsha", "五一广场", ["1号线", "2号线"]), ("foshan", "魁奇路", ["佛山2号线", "广佛线"]),
            ("dongguan", "市民中心", ["1号线", "2号线"]), ("nanning", "朝阳广场", ["1号线", "2号线"]),
            ("guiyang", "喷水池", ["1号线", "2号线"]), ("kunming", "环城南路", ["1号线", "2号线"]),
        ]
        for (id, station, expected) in spotChecks {
            guard let city = LioMetroCity.named(id) else { continue }
            #expect(try lines(city, station) == expected, "\(id) \(station)")
        }
        // Hand-checked English where AMap's pinyin was swapped or a character reads locally.
        for (id, station, english) in [("jinan", "梁王", "Liangwang"), ("jinan", "梁王西", "Liangwang Xi"),
                                       ("zhengzhou", "祭城", "Zhaicheng"), ("tianjin", "人民医院", "Renminyiyuan"),
                                       ("tianjin", "泰达", "TEDA"), ("chengdu", "杉板桥", "Shabanqiao"),
                                       ("chengdu", "涌泉", "Yongquan"), ("zhengzhou", "南五里堡", "Nanwulibao"),
                                       ("shijiazhuang", "柏林庄", "Bailinzhuang"), ("haerbin", "哈尔滨北站", "Harbin North Railway Station"),
                                       ("huhehaote", "呼和浩特东站", "Hohhot East Railway Station"), ("dalian", "革镇堡", "Gezhenpu"),
                                       ("dalian", "和平路", "Heping Road"), ("wulumuqi", "大地窝堡", "Dadiwopu"),
                                       ("suzhou", "尹山湖", "Yinshanhu"), ("nanjing", "小行", "Xiaohang"),
                                       ("nanjing", "湖北路·二中", "Hubeilu · Erzhong"),
                                       ("nanjing", "南京站", "Nanjing Railway Station"), ("wuxi", "北栅口", "Beizhakou"),
                                       ("hefei", "合肥南站", "Hefei South Railway Station"), ("chengdu", "火车北站", "Chengdu North Railway Station"),
                                       ("ningbo", "长江路", "Changjiang Road"), ("hangzhou", "火车站", "Shaoxing Railway Station"),
                                       ("hangzhou", "之江文化中心", "Zhijiang Cultural Center"), ("hangzhou", "西文街", "Xiwen Street"),
                                       ("suzhou", "高铁苏州北站", "Suzhou North Railway Station"), ("ningbo", "丽园南路", "Liyuan South Road"),
                                       ("kunming", "昆明南火车站", "Kunming South Railway Station"),
                                       ("nanning", "安吉客运站", "Anji Coach Station"), ("dongguan", "虎门火车站", "Humen Railway Station"),
                                       ("foshan", "林岳东(2号线)", "Linyue Dong (Line 2)"), ("hangzhou", "奥体中心", "Olympic Sports Center"),
                                       ("foshan", "朝安", "Chao'an"), ("wuhan", "沌阳大道", "Zhuanyang Boulevard"),
                                       ("changsha", "黄花机场T1T2", "Huanghua Jichang T1 T2"),
                                       ("chongqing", "重庆东站", "Chongqing East Railway Station")] {
            guard let city = LioMetroCity.named(id) else { continue }
            #expect(try LioMetroMap.bundled(city).stations.first { $0.nameZH == station }?.nameEN == english, "\(id) \(station)")
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
        // A station position outside mainland China's range, or not a [longitude, latitude] pair.
        for geo in [[200.0, 39.9], [116.3], [39.9, 116.3]] {
            #expect(throws: LioMetroMapFailure.invalid("station position s1")) {
                try LioMetroMap.read(Self.file { object in
                    var stations = object["stations"] as! [[String: Any]]
                    stations[0]["geo"] = geo
                    object["stations"] = stations
                }, city: .beijing)
            }
        }
        let placed = try LioMetroMap.read(Self.file { object in
            var stations = object["stations"] as! [[String: Any]]
            stations[0]["geo"] = [116.177, 39.926]
            object["stations"] = stations
        }, city: .beijing)
        #expect(placed.station("s1")?.geo == .init(latitude: 39.926, longitude: 116.177, referenceSystem: .gcj02))
        #expect(placed.station("s2")?.geo == nil)
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
