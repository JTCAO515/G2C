import Testing
@testable import CJLioUser

struct LioMetroGuideTests {
    @Test func eachCityHasAnOfficialMapAndBilingualInstructions() {
        let cities = LioMetroCity.allCases
        #expect(cities == [.beijing, .shanghai, .guangzhou, .shenzhen, .chengdu])
        #expect(cities.compactMap { $0.mapURL.host } == ["map.bjsubway.com", "service.shmetro.com", "cs.gzmtr.com", "www.szmc.net", "www.chengdurail.com"])
        for city in cities {
            #expect(city.mapURL.scheme == "https")
            #expect(city.guideURL.scheme == "https")
            for language in [LioLanguage.english, .chinese] {
                #expect(!city.buying(in: language).isEmpty)
                #expect(!city.security(in: language).isEmpty)
                #expect(!city.entering(in: language).isEmpty)
            }
        }
    }
}

/// #1421 item 4: choose a city first, then open its guide.
struct LioMetroCityPickerTests {
    @Test func everyCityCardHasANativeNameAndOneLine() {
        #expect(LioMetroCity.beijing.nativeName == "北京")
        #expect(LioMetroCity.shanghai.nativeName == "上海")
        #expect(LioMetroCity.guangzhou.nativeName == "广州")
        #expect(LioMetroCity.shenzhen.nativeName == "深圳")
        #expect(LioMetroCity.chengdu.nativeName == "成都")
        for city in LioMetroCity.allCases {
            for language in [LioLanguage.english, .chinese] {
                let line = city.summary(in: language)
                #expect(!line.isEmpty && line.count <= (language == .chinese ? 16 : 48))
            }
            #expect(city.identifier == "lio.metro.city." + city.rawValue)
        }
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
