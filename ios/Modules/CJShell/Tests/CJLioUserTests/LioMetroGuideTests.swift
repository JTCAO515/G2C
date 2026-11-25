import Foundation
import Testing
@testable import CJLioUser

/// Cities the tests name. Each exists while its map is bundled; the operator-built ones always are.
extension LioMetroCity {
    static var beijing: LioMetroCity { named("beijing")! }
    static var shanghai: LioMetroCity { named("shanghai")! }
    static var guangzhou: LioMetroCity { named("guangzhou")! }
    static var shenzhen: LioMetroCity { named("shenzhen")! }
    static var xian: LioMetroCity { named("xian")! }
    static var chengdu: LioMetroCity { named("chengdu")! }
}

/// #1450: the city list is the bundled maps, grouped by region; six cities keep an operator-checked guide.
struct LioMetroGuideTests {
    @Test func theListIsTheBundledMapsGroupedByRegion() throws {
        let cities = LioMetroCity.allCases
        #expect(cities.count >= 6)
        #expect(Set(cities.map(\.id)).count == cities.count)
        #expect(cities.first?.id == "beijing")
        for city in cities { #expect(throws: Never.self) { try LioMetroMap.bundled(city) } }
        // Grouped: once a region ends it does not come back.
        let regions = cities.map(\.region)
        #expect(regions == regions.sorted { LioMetroRegion.allCases.firstIndex(of: $0)! < LioMetroRegion.allCases.firstIndex(of: $1)! })
        #expect(LioMetroCity.xian.nameEN == "Xi'an" && LioMetroCity.xian.region == .northwest)
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

    @Test func checkedGuidesKeepTheirOfficialLinks() {
        let guided = LioMetroCity.allCases.filter { $0.guide != nil }.map(\.id)
        #expect(Set(guided) == ["beijing", "shanghai", "guangzhou", "shenzhen", "xian", "chengdu"])
        #expect(LioMetroCity.beijing.guide?.mapURL.host == "map.bjsubway.com")
        #expect(LioMetroCity.shenzhen.guide?.mapURL.host == "www.szmc.net")
        for city in LioMetroCity.allCases {
            if let guide = city.guide {
                #expect(guide.mapURL.scheme == "https" && guide.guideURL.scheme == "https")
            }
            for language in [LioLanguage.english, .chinese] {
                #expect(!city.buying(in: language).isEmpty)
                #expect(!city.security(in: language).isEmpty)
                #expect(!city.entering(in: language).isEmpty)
            }
        }
    }

    @Test func taxiOnlyWhereTaxiSearchCoversTheCity() {
        let taxi = Set(LioTaxiCity.allCases.map(\.rawValue))
        for city in LioMetroCity.allCases { #expect((city.taxiCity != nil) == taxi.contains(city.id), "\(city.id)") }
        #expect(LioMetroCity.beijing.taxiCity == .beijing)
    }

    @Test func readsOnlyAValidCityEntry() {
        let good = Data(#"{"city":"a","cityInfo":{"nameZH":"甲","nameEN":"A","provinceZH":"省","region":"north","order":2}}"#.utf8)
        #expect((try? LioMetroCity.read(entry: good))?.city.nameEN == "A")
        #expect(throws: LioMetroMapFailure.unreadable) { try LioMetroCity.read(entry: Data("{}".utf8)) }
        let unknownRegion = Data(#"{"city":"a","cityInfo":{"nameZH":"甲","nameEN":"A","provinceZH":"省","region":"moon","order":1}}"#.utf8)
        #expect(throws: LioMetroMapFailure.unreadable) { try LioMetroCity.read(entry: unknownRegion) }
        let noName = Data(#"{"city":"a","cityInfo":{"nameZH":"","nameEN":"A","provinceZH":"省","region":"north","order":1}}"#.utf8)
        #expect(throws: LioMetroMapFailure.invalid("city entry")) { try LioMetroCity.read(entry: noName) }
        // Region order first, then the catalogue's order inside a region.
        let east = LioMetroCity(id: "e", nameZH: "东", nameEN: "E", provinceZH: "省", region: .east)
        let north2 = LioMetroCity(id: "n2", nameZH: "北二", nameEN: "N2", provinceZH: "省", region: .north)
        let north1 = LioMetroCity(id: "n1", nameZH: "北一", nameEN: "N1", provinceZH: "省", region: .north)
        #expect(LioMetroCity.sorted([east, north2, north1], order: ["e": 1, "n2": 2, "n1": 1]).map(\.id) == ["n1", "n2", "e"])
    }
}

/// #1421 item 4: choose a city first, then open its guide.
struct LioMetroCityPickerTests {
    @Test func everyCityCardHasANativeNameAndOneLine() {
        #expect(LioMetroCity.beijing.nativeName == "北京")
        #expect(LioMetroCity.guangzhou.nativeName == "广州")
        #expect(LioMetroCity.xian.nativeName == "西安")
        #expect(LioMetroCity.chengdu.nativeName == "成都")
        for city in LioMetroCity.allCases {
            for language in [LioLanguage.english, .chinese] {
                let line = city.summary(in: language)
                #expect(!line.isEmpty && line.count <= (language == .chinese ? 16 : 48))
            }
            #expect(city.identifier == "lio.metro.city." + city.rawValue)
        }
    }

    @Test func searchFindsCitiesByEitherNameOrProvince() {
        #expect(LioMetroCity.cities(in: .south, matching: "广州").map(\.id) == ["guangzhou"])
        #expect(LioMetroCity.cities(in: .south, matching: "Shenzhen").map(\.id) == ["shenzhen"])
        let guangdong = LioMetroCity.cities(in: .south, matching: "广东")
        #expect(Set(["guangzhou", "shenzhen"]).isSubset(of: Set(guangdong.map(\.id))))
        #expect(guangdong.allSatisfy { $0.provinceZH == "广东省" })
        #expect(LioMetroCity.cities(in: .north, matching: "nowhere").isEmpty)
    }

    @Test func guideSectionsKeepTheirOrderAndIdentifiers() {
        #expect(LioMetroGuideSection.allCases.map(\.identifier) == ["lio.metro.ticket", "lio.metro.security", "lio.metro.gates"])
        for section in LioMetroGuideSection.allCases {
            for city in LioMetroCity.allCases {
                #expect(!section.text(for: city, in: .chinese).isEmpty)
            }
        }
    }
}
