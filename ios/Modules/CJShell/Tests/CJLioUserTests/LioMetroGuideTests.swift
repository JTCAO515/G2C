import Foundation
import Testing
@testable import CJLioUser

/// #1450: all 41 mainland metro cities, grouped by region; six keep their operator-checked guide.
struct LioMetroGuideTests {
    @Test func theCatalogueListsEveryMetroCityByRegion() throws {
        let cities = LioMetroCity.allCases
        #expect(cities.count == 41)
        #expect(Set(cities.map(\.id)).count == cities.count)
        #expect(cities.first?.id == "beijing")
        for region in LioMetroRegion.allCases {
            #expect(!LioMetroCity.cities(in: region).isEmpty, "\(region)")
        }
        // Grouped: once a region ends it does not come back.
        let regions = cities.map(\.region)
        #expect(regions == regions.sorted { LioMetroRegion.allCases.firstIndex(of: $0)! < LioMetroRegion.allCases.firstIndex(of: $1)! })
        #expect(LioMetroCity.named("wulumuqi")?.nameEN == "Ürümqi")
        #expect(LioMetroCity.named("haerbin")?.nameEN == "Harbin")
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
        let taxi = LioMetroCity.allCases.filter { $0.taxiCity != nil }.map(\.id)
        #expect(Set(taxi) == Set(LioTaxiCity.allCases.map(\.rawValue)))
        #expect(LioMetroCity.named("tianjin")?.taxiCity == nil)
    }

    @Test func readsOnlyAValidCatalogue() {
        #expect(throws: LioMetroMapFailure.unreadable) { try LioMetroCity.read(catalogue: Data("{}".utf8)) }
        let duplicate = Data(#"[{"id":"a","nameZH":"甲","nameEN":"A","provinceZH":"省","region":"north"},{"id":"a","nameZH":"乙","nameEN":"B","provinceZH":"省","region":"east"}]"#.utf8)
        #expect(throws: LioMetroMapFailure.invalid("catalogue")) { try LioMetroCity.read(catalogue: duplicate) }
        let unknownRegion = Data(#"[{"id":"a","nameZH":"甲","nameEN":"A","provinceZH":"省","region":"moon"}]"#.utf8)
        #expect(throws: LioMetroMapFailure.unreadable) { try LioMetroCity.read(catalogue: unknownRegion) }
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
        #expect(LioMetroCity.cities(in: .south, matching: "广东").count == 4)
        #expect(LioMetroCity.cities(in: .east, matching: "suzhou").map(\.id) == ["suzhou"])
        #expect(LioMetroCity.cities(in: .east, matching: "江苏").count == 6)
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
