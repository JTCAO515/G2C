import Foundation
import Testing
@testable import CJShell

/// #1880: the in-app privacy summary matches the Go2China Privacy Policy 1.0 and drops the beta notice's claims that
/// #225 found untrue (old provider, Singapore hosting, email sign-in, 30/30/30/180 days).
struct PrivacySummaryTests {
    private func everything(_ language: ShellLanguage) -> String {
        ([PrivacySummary.title(language), PrivacySummary.operatorLine(language), PrivacySummary.intro(language)]
            + PrivacySummary.paragraphs(language).flatMap { [$0.title, $0.text] }).joined(separator: "\n")
    }

    @Test func namesTheOperatorAndLinksTheFullPolicyInBothLanguages() {
        #expect(PrivacySummary.operatorLine(.english) == "Go2China is operated by Guangzhou Chuangjing Technology Co., Ltd.")
        #expect(PrivacySummary.operatorLine(.chinese) == "Go2China 由广州创竞科技有限公司运营。")
        #expect(PrivacySummary.policyURL == "https://go2china.space/privacy")
        for language in [ShellLanguage.english, .chinese] {
            #expect(PrivacySummary.intro(language).contains(PrivacySummary.policyURL))
        }
        #expect(PrivacySummary.title(.english) == "Privacy summary" && PrivacySummary.title(.chinese) == "隐私摘要")
    }

    @Test func coversTheApprovedPointsInBothLanguages() {
        let ids = PrivacySummary.paragraphs(.english).map(\.id)
        #expect(ids == ["process", "where", "not", "keep", "choices", "adults"])
        #expect(PrivacySummary.paragraphs(.chinese).map(\.id) == ids)
        let english = everything(.english), chinese = everything(.chinese)
        for word in ["invite code", "Hong Kong", "Model Studio", "AMap", "DiDi", "VariFlight", "system prompt", "18", "hello@go2china.space"] {
            #expect(english.contains(word), "\(word)")
        }
        for word in ["邀请码", "中国香港", "阿里云百炼", "高德", "滴滴", "飞常准", "系统弹窗", "18 周岁", "hello@go2china.space"] {
            #expect(chinese.contains(word), "\(word)")
        }
    }

    @Test func dropsTheBetaNoticeClaimsFoundUntrue() throws {
        let file = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/CJShell/PublicInformation.swift")
        let source = try String(contentsOf: file, encoding: .utf8)
        for claim in ["Context Jump", "Singapore", "新加坡", "email service for sign-in", "登录验证的邮件服务",
                      "within a further 30 days", "up to 180 days", "最多保留 180 天", "Privacy notice (beta)", "隐私说明（内测版）"] {
            #expect(!source.contains(claim), "\(claim)")
        }
        for language in [ShellLanguage.english, .chinese] {
            #expect(!everything(language).localizedStandardContains("separate consent"), "the in-app location consent is off in build 58")
            #expect(!everything(language).contains("单独同意"))
        }
    }
}
