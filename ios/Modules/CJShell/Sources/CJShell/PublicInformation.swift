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
                NavigationLink(language.text("Privacy notice (beta)", "隐私说明（内测版）"), value: MemoryRoute.privacy)
            }
        }.navigationTitle(language.text("Support", "支持"))
    }
}

struct PrivacyNoticeView: View {
    let language: ShellLanguage
    var body: some View {
        List {
            Section {
                Text(language.text("This beta notice describes the planned service. External service connections and the data controls described below are not yet available in this version.", "本内测说明介绍计划提供的服务。此版本尚未接入外部服务，以下数据控制功能也尚未开放。"))
            }
            Section(language.text("Provider", "服务方")) {
                Text(language.text("Go2China is provided by Context Jump LLC, with local support from its affiliate Guangzhou Chuangjing Technology. Questions: hello@go2china.space.", "Go2China 由 Context Jump LLC 提供，关联公司广州创竞科技提供本地支持。如有疑问请联系 hello@go2china.space。"))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Section(language.text("What we process", "我们处理的数据")) {
                Text(language.text("Your account email, the messages you send, trip plans and confirmations, memories you save, usage counts, and reports you choose to submit. Your language preference stays on this device.", "你的账号邮箱、你发送的消息、行程方案与确认记录、你保存的记忆、用量计数，以及你主动提交的问题反馈。语言偏好只保存在本设备。"))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Section(language.text("Service providers (planned)", "服务提供方（计划）")) {
                Text(language.text("We do not sell your data or share it for advertising. To run the service we use providers that process data on our behalf: an AI model provider (Alibaba Cloud Qwen, processed in mainland China) to generate replies; cloud hosting and database (Singapore); an email service for sign-in verification; and Apple for in-app purchases. Only the data needed for each task is sent.", "我们不出售你的数据，也不用于广告共享。为提供服务，我们使用代我们处理数据的服务提供方：AI 模型服务（阿里云通义千问，处理地在中国大陆）用于生成回答；云主机与数据库（新加坡）；用于登录验证的邮件服务；以及用于 App 内购买的 Apple。每项任务只发送完成该任务所需的数据。"))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Section(language.text("Retention", "留存")) {
                Text(language.text("Your trips, memories and chats are kept while your account exists. We never delete them because of inactivity or a plan change. When you delete an item or close your account, it is removed from active systems within 30 days and from backups within a further 30 days. Service logs are kept for up to 30 days; feedback reports for up to 180 days.", "账号存续期间，你的行程、记忆和对话会一直保存，不会因长期未使用或方案变更而被删除。你删除某条内容或注销账号后，相关数据会在 30 天内从在用系统中删除，并在其后 30 天内从备份中清除。服务日志最多保留 30 天；问题反馈最多保留 180 天。"))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Section(language.text("Offline (coming soon)", "离线（即将提供）")) {
                Text(language.text("Your last synced trip can be viewed offline. The offline copy is stored encrypted on this device, shows when it was last synced, and is removed 30 days after the last sync, or when you sign out, switch or close your account. A device that stays offline cannot be wiped remotely; it is cleaned up the next time it connects.", "最近一次同步的正式行程可离线查看。离线副本加密保存在本设备，会显示最后同步时间；距最后同步满 30 天，或你退出、切换、注销账号时，离线副本会被删除。持续断网的设备无法被远程清除，会在下次联网时清理。"))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Section(language.text("Your choices", "你的选择")) {
                Text(language.text("You can delete memories and close your account in the app when these features are available. Until then, email hello@go2china.space and we will handle your request.", "相关功能开放后，你可以在 App 内删除记忆和注销账号。在此之前，请发邮件至 hello@go2china.space，我们会处理你的请求。"))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Section {
                ContactRow(contact: .support, language: language)
                NavigationLink(language.text("Support", "支持"), value: MemoryRoute.support)
            }
        }
        .textSelection(.enabled)
        .navigationTitle(language.text("Privacy notice (beta)", "隐私说明（内测版）"))
    }
}
#endif
