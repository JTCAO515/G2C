import Testing
@testable import CJLioUser

struct LioPaymentGuideTests {
    @Test func bothProvidersHaveBilingualSetupStepsAndOfficialSources() {
        let providers = LioPaymentGuideProvider.allCases
        #expect(providers == [.alipay, .weixin])
        #expect(providers.compactMap { $0.officialInstructions.host } == ["english.beijing.gov.cn", "www.tenpayglobal.com"])
        for provider in providers {
            #expect(provider.officialInstructions.scheme == "https")
            for language in [LioLanguage.chinese, .english] {
                let steps = provider.steps(in: language)
                #expect(steps.map(\.id) == ["register", "find-card", "add-card", "verify"])
                #expect(steps.allSatisfy { !$0.title.isEmpty && !$0.detail.isEmpty && !$0.icon.isEmpty })
                #expect(LioPaymentGuideProvider.problems(in: language).map(\.id) == ["sms", "issuer", "identity"])
            }
        }
    }
}
