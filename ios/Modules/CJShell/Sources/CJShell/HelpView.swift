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
                    .accessibilityIdentifier("help.account.registration")
                NavigationLink(language.text("Open Account", "进入账号"), value: MemoryRoute.account)
                NavigationLink(language.text("Change language", "切换语言"), value: MemoryRoute.language)
            }
            Section(language.text("Invited access", "受邀资格")) {
                paragraph("Registering or signing in does not grant invited-beta access. Server verification is required. A pending, failed or unknown result does not grant access. Invitation distribution and eligibility rules have not been published here.",
                          "注册或登录不代表获得受邀内测资格，仍需服务端验证。待验证、失败或未知结果均不代表已获准访问。此处尚未公布邀请发放及资格规则。")
                    .accessibilityIdentifier("help.invited.access")
            }
            Section(language.text("Reviewing and rejecting a draft", "审阅与拒绝草稿")) {
                paragraph("A draft is not a formal trip. Review its sources, unverified details and the proposed scope before deciding. Use the available controls to accept or reject a draft or save changes. Closing a draft leaves your previous decision and formal trip unchanged.",
                          "草稿不是正式行程。决定前请审阅来源、待核实事项及拟修改范围。使用可用的按钮采用或拒绝草稿，或保存修改。关闭草稿会保留此前的决定和正式行程。")
                    .accessibilityIdentifier("help.trip.actions")
                paragraph("If an earlier action has an unknown result, query that original action when available. Do not create a replacement submission to guess its outcome.",
                          "此前动作结果未知时，应在可用时查询该原动作，不要另建一次提交来猜测结果。")
            }
            Section(language.text("Offline availability", "离线与有效期限")) {
                paragraph("Offline reading is limited to an eligible, previously synced formal trip. When offline reading is available, the trip is readable for up to 14 days from the last successful sync. Check the expiry in Trips. After expiry, reconnect to verify your account and sync the trip again. Changes and submissions require a connection.",
                          "离线读取仅适用于符合条件、此前已同步的正式行程。离线读取可用时，期限从最近一次成功同步起算，最长 14 天。请在行程页查看截止时间。到期后请联网核验账号并重新同步行程。修改和提交需联网。")
                    .accessibilityIdentifier("help.trip.offline")
            }
            Section(language.text("Reading original usage", "查询原调用用量")) {
                paragraph("In Assistant, open Original usage status. First resolve the selected accepted message's original link, then explicitly read the original attempt status. A link alone does not confirm execution, payment or usage. Missing resources or association leave the read unavailable; these actions do not start or resend a call.",
                          "在助手中打开原调用用量。先解析所选已接受原消息的关联，再明确查询原调用状态。仅有关联不代表已执行、已付款或已产生用量。缺少读取资源或关联时保持不可用；这两项操作不会启动或重发调用。")
            }
            Section(language.text("Deletion and local cleanup", "删除与本机清理边界")) {
                paragraph("When a deletion control is available in Memory or Account, review its scope and confirm the action. Stopping future use and cleaning associated stored data are separate results; a hidden item is not proof of completed deletion. Local sign-out and clear, when configured, only clean local session material. They do not delete server records, revoke a server session or resolve an unknown action.",
                          "记忆或账号页有可用的删除入口时，请先核对范围，再确认删除。停止后续使用与清理关联存储是两项独立结果；条目不再显示不代表删除完成。配置后可用的本机退出并清理仅清理本机会话材料，不代表删除服务端记录、撤销服务端会话或核实未知动作。")
                    .accessibilityIdentifier("help.account.deletion")
                paragraph("No immediate remote wipe of a disconnected device is promised. Check the offline expiry and cleanup status on the relevant screen. Previous-product data is outside these local cleanup actions.",
                          "不承诺即时远程擦除断网设备。请在相应页面查看离线截止时间和清理状态。旧产品数据不属于这些本机清理操作的范围。")
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
