import Foundation

/// Display-only future plan labels; no purchase, billing or entitlement API.
enum ShellFuturePlan: String, CaseIterable {
    case first = "US$19.99/month"
    case second = "US$39.99/month"
    func title(_ language: ShellLanguage) -> String {
        switch self {
        case .first: language.text("Future plan 1 placeholder", "未来方案一占位")
        case .second: language.text("Future plan 2 placeholder", "未来方案二占位")
        }
    }
}

/// Confirmed contact destinations only. No subject/body, user data or sending action.
enum ShellContact: CaseIterable {
    case support, contact
    var address: String {
        switch self {
        case .support: "support@go2china.space"
        case .contact: "jtcao@go2china.space"
        }
    }
    var emailURL: URL? { URL(string: "mailto:" + address) }
    func title(_ language: ShellLanguage) -> String {
        switch self {
        case .support: language.text("Email support", "邮件支持")
        case .contact: language.text("Contact", "联系")
        }
    }
}

#if os(iOS)
import SwiftUI

struct LaunchInformationSection: View {
    let language: ShellLanguage
    var body: some View {
        Section(language.text("Launch and plans", "首发与方案")) {
            Text(language.text("Free at launch", "首发免费")).font(.headline)
            Text(language.text("Account verification and invited access are still required where applicable.", "仍须按适用要求验证账号与受邀资格。"))
            ForEach(ShellFuturePlan.allCases, id: \.self) { plan in
                placeholder(plan.title(language), amount: plan.rawValue)
            }
            Text(language.text("These are placeholders for future subscription plans. Plan benefits are not confirmed. No purchase, billing, subscription or paid access is enabled here; a paid service is not being offered.", "以上仅为未来订阅档位展示占位，方案权益尚未确认。此处未启用购买、扣费、订阅或付费权益，不代表已提供付费服务。"))
                .font(.footnote).fixedSize(horizontal: false, vertical: true)
        }
    }
    private func placeholder(_ title: String, amount: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption)
            Text(verbatim: amount).font(.title3).monospacedDigit()
                .fixedSize(horizontal: false, vertical: true)
        }.accessibilityElement(children: .combine)
    }
}

private struct ContactRow: View {
    let contact: ShellContact
    let language: ShellLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let destination = contact.emailURL {
                Link(contact.title(language), destination: destination)
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
                Text(language.text("Use the email links below, or copy an address. Opening a link does not send a message; review and send it in your mail app. This screen does not confirm delivery or a reply.", "可使用下方邮件链接或复制地址。打开链接不会发送邮件，请在邮件应用中审阅后自行发送。此页面不确认送达或回复。"))
            }
            Section(language.text("Support and contact", "支持与联系")) {
                ContactRow(contact: .support, language: language)
                ContactRow(contact: .contact, language: language)
            }
            Section {
                NavigationLink(language.text("Help", "帮助"), value: MemoryRoute.help)
                NavigationLink(language.text("Privacy facts draft", "隐私事实草稿"), value: MemoryRoute.privacy)
            }
        }.navigationTitle(language.text("Support", "支持"))
    }
}

struct PrivacyFactsDraftView: View {
    let language: ShellLanguage
    var body: some View {
        List {
            Section {
                Text(language.text("Facts draft — for review", "事实草稿，供审阅")).font(.headline)
                Text(language.text("This draft describes the current interface and marks unconfirmed information. It is not a published privacy policy or a promise that unavailable data controls are already implemented.", "此草稿说明当前界面事实并标出待确认信息，尚非已发布的隐私政策，也不代表尚未开放的数据控制已经实现。"))
            }
            Section(language.text("Current interface facts", "当前界面事实")) {
                Text(language.text("Your language preference is saved on this device. When connected, Memory can read records and query previous save results. Private memory views are cleared when the account changes or the app leaves the foreground; this does not delete stored records.", "语言偏好保存在此设备。接入后，记忆可以读取条目并查询此前的保存结果。账号变化或应用离开前台时会清空私密记忆页面，但不会删除已存储的记录。"))
                Text(language.text("Stopping future use and cleaning associated storage are separate results. This interface does not offer memory deletion or account closure. Local session cleanup does not delete server records or resolve an unknown action. No immediate remote wipe of disconnected devices is promised.", "停止后续使用与清理关联存储是两项独立结果。此界面暂不提供记忆删除或账号注销。本机会话清理不代表删除服务端记录或核实未知动作，也不承诺即时远程擦除断网设备。"))
            }
            Section(language.text("Pending confirmation", "待确认事项")) {
                Text(language.text("Responsible service entity: pending confirmation.", "服务责任主体：待确认。"))
                Text(language.text("Data retention and backup cleanup periods: pending confirmation.", "数据留存与备份清理期限：待确认。"))
                Text(language.text("Third-party sharing scope, recipients and purposes: pending confirmation.", "第三方共享范围、接收方及用途：待确认。"))
                Text(language.text("Offline validity and reconnection cleanup rules: pending confirmation.", "离线有效期与重连清理规则：待确认。"))
            }
            Section(language.text("Questions about this draft", "草稿咨询")) {
                ContactRow(contact: .contact, language: language)
                NavigationLink(language.text("Support", "支持"), value: MemoryRoute.support)
            }
        }
        .textSelection(.enabled)
        .navigationTitle(language.text("Privacy draft", "隐私草稿"))
    }
}
#endif
