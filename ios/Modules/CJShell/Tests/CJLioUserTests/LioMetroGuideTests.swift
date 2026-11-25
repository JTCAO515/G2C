import Foundation
import Testing
@testable import CJLioUser

/// Cities the tests name: the five built from operator data, which stay bundled. Cities taken from AMap
/// (Chengdu and the later batches) are looked up with `named(_:)`, so removing one needs no test change.
extension LioMetroCity {
    static var beijing: LioMetroCity { named("beijing")! }
    static var shanghai: LioMetroCity { named("shanghai")! }
    static var guangzhou: LioMetroCity { named("guangzhou")! }
    static var shenzhen: LioMetroCity { named("shenzhen")! }
    static var xian: LioMetroCity { named("xian")! }
}

/// #1450: the city list is the bundled maps, best-known first, then by pinyin; each card opens its map.
struct LioMetroGuideTests {
    @Test func theListIsTheBundledMapsBestKnownFirst() throws {
        let cities = LioMetroCity.allCases
        #expect(Set(["beijing", "shanghai", "guangzhou", "shenzhen", "xian"]).isSubset(of: Set(cities.map(\.id))))
        #expect(Set(cities.map(\.id)).count == cities.count)
        // Every bundled map file made it into the list: none was skipped as unreadable or as a second copy.
        #expect(LioMetroCity.mapFiles.count == cities.count)
        #expect(cities.first?.id == "beijing")
        for city in cities { #expect(throws: Never.self) { try LioMetroMap.bundled(city) } }
        // No regions (JT 2026-11-25): the best-known cities in a fixed order, then the rest by pinyin.
        let best = ["beijing", "shanghai", "guangzhou", "shenzhen", "chengdu", "hangzhou", "xian", "chongqing"]
        let bundledBest = best.filter { id in cities.contains { $0.id == id } }
        #expect(Array(cities.map(\.id).prefix(bundledBest.count)) == bundledBest)
        let rest = cities.dropFirst(bundledBest.count).map(\.id)
        #expect(rest == rest.sorted())
        #expect(LioMetroCity.xian.nameEN == "Xi'an")
    }

    /// NOTICE.md (generated from the map files) names every bundled city, its source and English names.
    @Test func theSourceNoticeListsEveryBundledCity() throws {
        let url = try #require(LioMetroCity.noticeURL)
        let notice = try String(contentsOf: url, encoding: .utf8)
        for city in LioMetroCity.allCases {
            let row = try #require(notice.split(separator: "\n").first { $0.contains("（\(city.id)）") }, "\(city.id)")
            let map = try LioMetroMap.bundled(city)
            #expect(row.contains(map.source.checkedOn))
            #expect(row.contains(map.source.provider == nil ? "官网" : "参考高德地图"))
        }
        #expect(notice.contains("整城移除"))
    }

    @Test func taxiOnlyWhereTaxiSearchCoversTheCity() {
        let taxi = Set(LioTaxiCity.allCases.map(\.rawValue))
        for city in LioMetroCity.allCases { #expect((city.taxiCity != nil) == taxi.contains(city.id), "\(city.id)") }
        #expect(LioMetroCity.beijing.taxiCity == .beijing)
    }

    @Test func readsOnlyAValidCityEntry() {
        let good = Data(#"{"city":"a","cityInfo":{"nameZH":"甲","nameEN":"A","provinceZH":"省","featured":2}}"#.utf8)
        #expect((try? LioMetroCity.read(entry: good))?.featured == 2)
        let plain = Data(#"{"city":"b","cityInfo":{"nameZH":"乙","nameEN":"B","provinceZH":"省"}}"#.utf8)
        #expect((try? LioMetroCity.read(entry: plain))?.city.nameEN == "B")
        #expect((try? LioMetroCity.read(entry: plain))?.featured == nil)
        #expect(throws: LioMetroMapFailure.unreadable) { try LioMetroCity.read(entry: Data("{}".utf8)) }
        let noName = Data(#"{"city":"a","cityInfo":{"nameZH":"","nameEN":"A","provinceZH":"省"}}"#.utf8)
        #expect(throws: LioMetroMapFailure.invalid("city entry")) { try LioMetroCity.read(entry: noName) }
        let badRank = Data(#"{"city":"a","cityInfo":{"nameZH":"甲","nameEN":"A","provinceZH":"省","featured":0}}"#.utf8)
        #expect(throws: LioMetroMapFailure.invalid("city entry")) { try LioMetroCity.read(entry: badRank) }
        // Featured by rank, then the rest by pinyin.
        let city = { (id: String) in LioMetroCity(id: id, nameZH: "城", nameEN: id, provinceZH: "省") }
        #expect(LioMetroCity.sorted([city("dalian"), city("xian"), city("anshan"), city("beijing")],
                                    featured: ["beijing": 1, "xian": 2]).map(\.id) == ["beijing", "xian", "anshan", "dalian"])
    }
}

/// #1421 item 4: choose a city first, then its map opens.
struct LioMetroCityPickerTests {
    @Test func everyCityCardShowsTheChineseNameOrProvince() {
        #expect(LioMetroCity.beijing.nativeName == "北京")
        #expect(LioMetroCity.guangzhou.detail(in: .english) == "广州")
        #expect(LioMetroCity.guangzhou.detail(in: .chinese) == "广东省")
        if let chengdu = LioMetroCity.named("chengdu") { #expect(chengdu.nativeName == "成都") }
        for city in LioMetroCity.allCases {
            #expect(city.detail(in: .english) == city.nameZH && city.detail(in: .chinese) == city.provinceZH)
            #expect(city.identifier == "lio.metro.city." + city.rawValue)
        }
    }

    @Test func searchFindsCitiesByEitherNameOrProvince() {
        #expect(LioMetroCity.cities(matching: "广州").map(\.id) == ["guangzhou"])
        #expect(LioMetroCity.cities(matching: " Shenzhen ").map(\.id) == ["shenzhen"])
        let guangdong = LioMetroCity.cities(matching: "广东")
        #expect(Set(["guangzhou", "shenzhen"]).isSubset(of: Set(guangdong.map(\.id))))
        #expect(guangdong.allSatisfy { $0.provinceZH == "广东省" })
        #expect(LioMetroCity.cities(matching: "nowhere").isEmpty)
        #expect(LioMetroCity.cities().map(\.id) == LioMetroCity.allCases.map(\.id))
    }
}
