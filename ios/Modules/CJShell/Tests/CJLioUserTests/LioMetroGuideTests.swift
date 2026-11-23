import Testing
@testable import CJLioUser

struct LioMetroGuideTests {
    @Test func eachCityHasAnOfficialMapAndBilingualInstructions() {
        let cities = LioMetroCity.allCases
        #expect(cities == [.beijing, .shanghai, .chengdu])
        #expect(cities.compactMap { $0.mapURL.host } == ["map.bjsubway.com", "service.shmetro.com", "www.chengdurail.com"])
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
