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
            #expect(failures.map(\.id) == ["scan-fails", "limit", "fee", "transfer", "cash"])
            #expect(Set(failures.map(\.id)).isDisjoint(with: LioPaymentGuideProvider.problems(in: language).map(\.id)))
            for item in failures {
                #expect(!item.title.isEmpty && !item.detail.isEmpty && !item.icon.isEmpty)
                let source = item.source
                #expect(source?.url.scheme == "https", "\(item.id) needs an official https source")
                #expect(!(source?.name.isEmpty ?? true))
                if item.detail.contains(where: { $0.isASCII && $0.isNumber }) {
                    #expect(item.detail.lowercased().contains(language.text("check the payment page", "以付款页面显示为准")),
                            "\(item.id) \(language): numbers can change, so the payment page has the final word")
                }
            }
        }
        let hosts = LioPaymentGuideProvider.paymentFailures(in: .english).compactMap { $0.source?.url.host }
        // Sources checked against the pages on 2026-11-25 (review of #1623): each item states only what its page says.
        #expect(hosts == ["www.gd.gov.cn", "help.wechat.com", "www.eguizhou.gov.cn", "help.wechat.com", "www.gd.gov.cn"])
    }

    @Test func theServiceFeeIsSaidToApplyToInternationalCardsInTheseAppsOnly() {
        let chinese = LioPaymentGuideProvider.paymentFailures(in: .chinese).first { $0.id == "fee" }?.detail ?? ""
        #expect(chinese.contains("微信支付") && chinese.contains("支付宝") && chinese.contains("外卡"))
        let english = LioPaymentGuideProvider.paymentFailures(in: .english).first { $0.id == "fee" }?.detail ?? ""
        #expect(english.contains("Weixin Pay") && english.contains("Alipay") && english.contains("international card"))
    }

    @Test func adviceStaysWithinWhatTheSourcesSay() {
        // Review of #1623: no claim about card issuers (the cited page has none), no unsourced RMB 15,000 figure,
        // and the limit uses Weixin Pay's own numbers rather than the older policy announcement.
        for language in [LioLanguage.chinese, .english] {
            let text = LioPaymentGuideProvider.paymentFailures(in: language).map(\.detail).joined(separator: " ")
            #expect(!text.contains("15,000") && !text.contains("5,000 美元") && !text.contains("US$5,000"))
            #expect(!text.contains("多半") && !text.lowercased().contains("usually"))
            #expect(!text.contains("发卡行") && !text.lowercased().contains("issuer"))
        }
        let limit = LioPaymentGuideProvider.paymentFailures(in: .chinese).first { $0.id == "limit" }?.detail ?? ""
        #expect(limit.contains("6,500") && limit.contains("65,000") && limit.contains("支付宝的外卡限额请看付款页面"))
        #expect(!limit.contains("都有限额"), "Alipay's limit is not stated by the linked page")
        // Second review of #1623: the WeChat page says nothing about personal payment codes.
        for language in [LioLanguage.chinese, .english] {
            let transfer = LioPaymentGuideProvider.paymentFailures(in: language).first { $0.id == "transfer" }
            #expect(!(transfer?.detail.contains(language.text("personal code", "个人收款码")) ?? true))
            #expect(!(transfer?.title.contains(language.text("pay a person", "付给个人")) ?? true))
        }
    }

    @Test func setupStepsKeepNoSource() {
        for provider in LioPaymentGuideProvider.allCases {
            #expect(provider.steps(in: .english).allSatisfy { $0.source == nil })
        }
    }
}
