import Testing
@testable import CJLioUser

struct LioConsulateDirectoryTests {
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
        #expect(consulates.contains { $0.districtZh == nil })
    }
}
