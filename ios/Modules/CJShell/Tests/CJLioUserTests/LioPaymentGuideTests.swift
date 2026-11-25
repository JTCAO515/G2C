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

    /// JT 2026-11-25 (coordination): what to do when a payment fails, each item with an official source.
    @Test func paymentFailuresAreBilingualSourcedAndDoNotRepeatTheSetupProblems() {
        for language in [LioLanguage.chinese, .english] {
            let failures = LioPaymentGuideProvider.paymentFailures(in: language)
            #expect(failures.map(\.id) == ["declined", "limit", "unverified", "fee", "transfer", "cash"])
            #expect(Set(failures.map(\.id)).isDisjoint(with: LioPaymentGuideProvider.problems(in: language).map(\.id)))
            for item in failures {
                #expect(!item.title.isEmpty && !item.detail.isEmpty && !item.icon.isEmpty)
                let source = item.source
                #expect(source?.url.scheme == "https", "\(item.id) needs an official https source")
                #expect(!(source?.name.isEmpty ?? true))
                if item.detail.contains(where: { $0.isASCII && $0.isNumber }) {
                    #expect(item.detail.lowercased().contains(language.text("the payment page shows", "以付款页面显示为准")),
                            "\(item.id) \(language): numbers can change, so the payment page has the final word")
                }
            }
        }
        let hosts = LioPaymentGuideProvider.paymentFailures(in: .english).compactMap { $0.source?.url.host }
        #expect(hosts == ["www.gd.gov.cn", "english.www.gov.cn", "blog.wechat.com", "www.szns.gov.cn", "help.wechat.com",
                          "www.gd.gov.cn"])
    }

    @Test func theServiceFeeIsSaidToApplyToInternationalCardsInTheseAppsOnly() {
        let chinese = LioPaymentGuideProvider.paymentFailures(in: .chinese).first { $0.id == "fee" }?.detail ?? ""
        #expect(chinese.contains("微信支付") && chinese.contains("支付宝") && chinese.contains("外卡"))
        let english = LioPaymentGuideProvider.paymentFailures(in: .english).first { $0.id == "fee" }?.detail ?? ""
        #expect(english.contains("Weixin Pay") && english.contains("Alipay") && english.contains("international card"))
    }

    @Test func setupStepsKeepNoSource() {
        for provider in LioPaymentGuideProvider.allCases {
            #expect(provider.steps(in: .english).allSatisfy { $0.source == nil })
        }
    }
}
