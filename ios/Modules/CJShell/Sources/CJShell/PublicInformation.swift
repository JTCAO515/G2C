import Foundation

/// JT-approved beta information; display only, never an entitlement grant.
enum ShellBetaInformation {
    static func plans(_ language: ShellLanguage) -> String {
        language.text("Go2China is free during the invited beta. Waitlist members join as Early Access users and receive the paid-plan benefits at no cost. Plan pricing will be announced later. No purchase or billing is available in this version.", "受邀内测期间 Go2China 免费使用。候补名单用户将成为 Early Access 用户，免费享有付费档权益。方案价格将另行公布。此版本不提供任何购买或扣费。")
    }
}

/// Confirmed contact destinations only. No subject/body, user data or sending action.
enum ShellContact: CaseIterable {
    case support
    var address: String {
        switch self {
        case .support: "hello@go2china.space"
        }
    }
    var emailURL: URL? { URL(string: "mailto:" + address) }
    func title(_ language: ShellLanguage) -> String {
        switch self {
        case .support: language.text("Email support", "邮件支持")
        }
    }
}

#if os(iOS)
import SwiftUI

struct LaunchInformationSection: View {
    let language: ShellLanguage
    var body: some View {
        Section {
            Text(ShellBetaInformation.plans(language))
                .fixedSize(horizontal: false, vertical: true)
        } header: { ShellSectionHeading(title: language.text("Plans", "方案")) }
    }
}

private struct ContactRow: View {
    let contact: ShellContact
    let language: ShellLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let destination = contact.emailURL {
                Link(contact.title(language), destination: destination)
                    .accessibilityIdentifier("support.email")
                    .accessibilityLabel(contact.title(language) + ": " + contact.address)
                    .accessibilityHint(language.text("Opens your mail app. Review and send the message there.", "打开邮件应用，由你审阅并发送邮件。"))
            } else {
                Text(language.text("Email link unavailable", "邮件链接不可用"))
            }
            Text(contact.address).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct SupportInformationView: View {
    let language: ShellLanguage
    var body: some View {
        List {
            Section {
                Text(language.text("Email hello@go2china.space. Opening the link starts a draft in your mail app; review and send it there. This screen does not confirm delivery or a reply.", "发送邮件至 hello@go2china.space。点击链接会在邮件应用中生成草稿，请审阅后自行发送。此页面不确认送达或回复。"))
            }
            Section(language.text("Support and contact", "支持与联系")) {
                ContactRow(contact: .support, language: language)
            }
            Section {
                NavigationLink(language.text("Help", "帮助"), value: MemoryRoute.help)
                NavigationLink(PrivacySummary.title(language), value: MemoryRoute.privacy)
            }
        }.navigationTitle(language.text("Support", "支持"))
    }
}

public struct PrivacyNoticeView: View {
    let language: ShellLanguage
    /// The engineering shell links on to its Support page; Lio's Me tab has no such route (#1880).
    let showsSupportLink: Bool
    public init(language: ShellLanguage, showsSupportLink: Bool = true) {
        self.language = language
        self.showsSupportLink = showsSupportLink
    }
    public var body: some View {
        List {
            Section {
                Text(PrivacySummary.operatorLine(language))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("privacy.summary.operator")
                Text(PrivacySummary.intro(language))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("privacy.summary.intro")
            }
            if localAMapConfigured {
                Section(language.text("AMap in this build", "此构建中的高德地图")) {
                    Text(language.text("AMap (北京高德图强科技有限公司) independently processes the viewed map region and device/network information for map display and security. Optional analytics are disabled. Your location is not requested. Loading requires separate explicit consent; the text itinerary remains available without a map.", "高德（北京高德图强科技有限公司）独立处理查看区域及设备、网络信息，用于地图展示与安全保障。可选统计分析已关闭，不申请你的位置。加载地图需要另行明确同意；不加载也可完整阅读文字行程。"))
                        .fixedSize(horizontal:false,vertical:true)
                    Link(language.text("AMap SDK privacy policy", "高德 SDK 隐私政策"),destination:URL(string:"https://lbs.amap.com/pages/privacy/")!)
                        .accessibilityIdentifier("privacy.amap.policy")
                }
            }
            // #1880: a short summary of the Go2China Privacy Policy 1.0 (approved by the coordinator under JT's
            // pre-authorisation, 2026-11-26). The full page generated from the policy text comes with #1747.
            ForEach(PrivacySummary.paragraphs(language), id: \.id) { paragraph in
                Section(paragraph.title) {
                    Text(paragraph.text)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("privacy.summary." + paragraph.id)
                }
            }
            Section {
                ContactRow(contact: .support, language: language)
                if showsSupportLink {
                    NavigationLink(language.text("Support", "支持"), value: MemoryRoute.support)
                }
            }
        }
        .textSelection(.enabled)
        .navigationTitle(PrivacySummary.title(language))
    }
    private var localAMapConfigured: Bool {
        #if DEBUG && G2C_AMAP_LOCAL && canImport(MAMapKit) && !targetEnvironment(simulator)
        AMapRecordedPlaceMap.isConfigured
        #else
        false
        #endif
    }
}
#endif
