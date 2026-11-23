import Testing
@testable import CJLioUser

struct LioConsulateDirectoryTests {
    @Test(arguments: [
        ("英国", "大不列颠及北爱尔兰联合王国", 4), ("UK", "大不列颠及北爱尔兰联合王国", 4),
        ("美国", "美利坚合众国", 4), ("US", "美利坚合众国", 4),
        ("韩国", "大韩民国", 7), ("South Korea", "大韩民国", 7),
        ("朝鲜", "朝鲜民主主义人民共和国", 1), ("North Korea", "朝鲜民主主义人民共和国", 1),
    ])
    func commonCountryNamesSelectOnlyTheMatchingCountry(alias: String, official: String, count: Int) throws {
        let matched = try LioConsulateDirectory.bundled().filter { $0.matches(alias) }
        #expect(matched.count == count)
        #expect(Set(matched.map(\.countryZh)) == [official])
    }

    @Test func officialDirectorySupportsCountryCityAndDistrictSearch() throws {
        let consulates = try LioConsulateDirectory.bundled()
        #expect(consulates.count == 199)
        #expect(Set(consulates.map(\.id)).count == consulates.count)
        let shanghai = try #require(consulates.first {
            $0.nameZh == "澳大利亚驻上海总领事馆"
        })
        #expect(shanghai.matches("Australia"))
        #expect(shanghai.matches("上海"))
        #expect(shanghai.matches("江苏"))
        #expect(!shanghai.matches("lorem-unknown"))
        #expect(shanghai.districtEn?.contains("Jiangsu") == true)
        let guangzhou = try #require(consulates.first { $0.source.lastPathComponent == "t20090802_9330086.shtml" })
        #expect(guangzhou.districtZh == nil)
        #expect(guangzhou.districtEn == nil)
        #expect(guangzhou.additionalDistrictSource?.host == "www.bmeia.gv.at")
        #expect(shanghai.additionalDistrictSource == nil)
    }
}
