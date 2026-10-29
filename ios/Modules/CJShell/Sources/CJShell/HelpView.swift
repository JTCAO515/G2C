#if os(iOS)
import SwiftUI

/// Describes the available interface and confirmed boundaries, without granting
/// account access, deciding a draft, or implying a configured retention policy.
struct HelpView: View {
    let language: ShellLanguage

    var body: some View {
        List {
            Section {
                Text(language.text("Help", "帮助")).font(.headline)
                paragraph("This guide reflects the current interface. Unavailable features remain unavailable; this guide does not grant access or promise a service outcome.", "本说明反映当前界面。尚未开放的功能仍不可用；本说明不授予访问权限，也不承诺服务结果。")
            }
            Section(language.text("Getting started", "首次使用与建号")) {
                paragraph("Use Assistant, Trips, Plugins and Memory. Account and language settings are in Memory. Plugins are not available yet.",
                          "通过助手、行程、插件和记忆四个标签使用应用。账号和语言设置位于记忆内。插件暂未开放。")
                paragraph("This is a new account system. Previous accounts, chats, trips, memories and subscriptions are not transferred. When account services are connected, open Account and choose Register; complete email verification if requested. Disabled actions mean registration is unavailable here.",
                          "本产品使用全新账号体系，不迁移旧账号、聊天、行程、记忆或订阅。账号服务接入后，可进入账号并选择注册；如提示验证邮箱，须完成验证。操作禁用时，此处尚不能建号。")
                NavigationLink(language.text("Open Account", "进入账号"), value: MemoryRoute.account)
                NavigationLink(language.text("Change language", "切换语言"), value: MemoryRoute.language)
            }
            Section(language.text("Invited access", "受邀资格")) {
                paragraph("Registering or signing in does not grant invited-beta access. Server verification is required. A pending, failed or unknown result does not grant access. Invitation distribution and eligibility rules have not been published here.",
                          "注册或登录不代表获得受邀内测资格，仍需服务端验证。待验证、失败或未知结果均不代表已获准访问。此处尚未公布邀请发放及资格规则。")
            }
            Section(language.text("Reviewing and rejecting a draft", "审阅与拒绝草稿")) {
                paragraph("A draft is not a formal trip. Review its sources, unverified details and the proposed scope before deciding. In Trips, available drafts can currently be read only: accepting, rejecting and saving changes are not connected. Closing a draft does not reject or accept it, and does not save changes to the formal trip.",
                          "草稿不是正式行程。决定前请审阅来源、待核实事项及拟修改范围。目前行程中的可用草稿仅供读取，接受、拒绝与保存修改尚未接入。关闭草稿不代表拒绝或接受，也不会将修改保存到正式行程。")
                paragraph("If an earlier action has an unknown result, query that original action when available. Do not create a replacement submission to guess its outcome.",
                          "此前动作结果未知时，应在可用时查询该原动作，不要另建一次提交来猜测结果。")
            }
            Section(language.text("Offline availability", "离线与有效期限")) {
                paragraph("Offline reading is limited to an eligible, previously synced formal trip. This interface has no connected offline reader or configured validity period. Do not rely on it for offline access or assume a record remains valid indefinitely. Reconnect and verify availability before relying on it; offline changes and submissions are not available.",
                          "离线读取仅适用于符合条件、此前已同步的正式行程。目前此界面尚未接入离线读取，有效期限也未配置。请勿依赖此处离线访问，也不要假定记录永久有效；使用前须联网核验可用性。离线修改与提交尚不可用。")
            }
            Section(language.text("Reading original usage", "查询原调用用量")) {
                paragraph("In Assistant, open Original usage status. First resolve the selected accepted message's original link, then explicitly read the original attempt status. A link alone does not confirm execution, payment or usage. Missing resources or association leave the read unavailable; these actions do not start or resend a call.",
                          "在助手中打开原调用用量。先解析所选已接受原消息的关联，再明确查询原调用状态。仅有关联不代表已执行、已付款或已产生用量。缺少读取资源或关联时保持不可用；这两项操作不会启动或重发调用。")
            }
            Section(language.text("Deletion and local cleanup", "删除与本机清理边界")) {
                paragraph("Memory deletion and account closure are not available from this interface. Stopping future use and cleaning associated stored data are separate results; a hidden item is not proof of completed deletion. Local sign-out and clear, when configured, only clean local session material. They do not delete server records, revoke a server session or resolve an unknown action.",
                          "此界面暂不提供记忆删除或账号注销。停止后续使用与清理关联存储是两项独立结果；条目不再显示不代表删除完成。配置后可用的本机退出并清理仅清理本机会话材料，不代表删除服务端记录、撤销服务端会话或核实未知动作。")
                paragraph("No immediate remote wipe of a disconnected device is promised. Offline expiry, reconnection cleanup and data retention terms are not configured here. Previous-product data is outside these local cleanup actions.",
                          "不承诺即时远程擦除断网设备。离线失效、重连清理及数据留存条款尚未在此配置。旧产品数据不属于这些本机清理操作的范围。")
                NavigationLink(language.text("Privacy notice (beta)", "隐私说明（内测版）"), value: MemoryRoute.privacy)
                NavigationLink(language.text("Support and contact", "支持与联系"), value: MemoryRoute.support)
            }
            LaunchInformationSection(language: language)
        }
        .navigationTitle(language.text("Help", "帮助"))
    }

    private func paragraph(_ english: String, _ chinese: String) -> some View {
        Text(language.text(english, chinese))
            .fixedSize(horizontal: false, vertical: true)
            .textSelection(.enabled)
    }
}
#endif
