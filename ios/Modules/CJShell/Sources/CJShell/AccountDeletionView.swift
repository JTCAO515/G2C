#if os(iOS)
import SwiftUI
import CJRunClient

struct AccountDeletionLink: View {
    let language: ShellLanguage
    var body: some View {
        NavigationLink {
            AccountDeletionView(language: language)
        } label: {
            RunReadableText(text: language.text("Delete account", "注销账号"))
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: 44)
        }.accessibilityIdentifier("account.deletion.open")
    }
}

/// Scope explanation only until the canonical account-deletion operation is connected.
/// Opening this page does not create an operation, submit a request or erase a file.
struct AccountDeletionView: View {
    let language: ShellLanguage
    var body: some View {
        List {
            section(language.text("Availability", "当前状态")) {
                paragraph(language.text(
                    "Account deletion is not available yet. No deletion request has been sent.",
                    "账号注销尚未开放，未发送注销请求。"), id: "account.deletion.unavailable")
            }
            section(language.text("Memory and account deletion", "删除记忆与注销账号")) {
                paragraph(language.text(
                    "Deleting one memory stops its future use and cleans its related records. It keeps your account and original chat. Signing out on this device also keeps your account.",
                    "删除一条记忆会停止后续使用并清理关联记录，保留账号和原聊天。本机退出登录也会保留账号。"), id: "account.deletion.memoryScope")
                paragraph(language.text(
                    "Account deletion covers this G2C account's chats, trips, candidates, memories and sources, feedback, execution records and device caches. It does not cover accounts or data from older products.",
                    "注销账号涵盖此 G2C 账号的聊天、行程、候选、记忆及来源、反馈、执行记录和设备缓存，不涉及旧产品账号或数据。"), id: "account.deletion.accountScope")
            }
            section(language.text("Stopping use and cleanup progress", "停止使用与清理进度")) {
                paragraph(language.text(
                    "Stopping access and completing cleanup are separate results. Cleanup may be in progress, blocked, failed or unknown. Only confirmed results can be shown as complete.",
                    "停止访问与清理完成是两项独立结果。清理可能处于进行中、受阻、失败或未知状态；只有核实后的结果才能显示完成。"), id: "account.deletion.progressScope")
            }
            section(language.text("Devices and retained copies", "设备与留存副本")) {
                paragraph(language.text(
                    "Offline trips are readable for up to 14 days from the last successful sync; every successful sync starts a new period. Reading stops at expiry. After reconnecting, an invalid or expired cache is cleared; reading resumes only after online verification. Another offline device cannot be erased immediately from here.",
                    "离线行程从最后成功同步起最多可读 14 天，每次成功同步重新起算。到期停止读取；重连后发现失效或到期会清理缓存，联网核验后才恢复读取。此处无法即时擦除另一台断网设备。"), id: "account.deletion.offlineScope")
                paragraph(language.text(
                    "The backup retention period is 30 rolling days. Deleted data in backups disappears as those backups expire. Already displayed history and requests already sent to a model cannot be recalled; external providers may retain their copies.",
                    "备份留存期限为 30 天滚动，备份中的已删数据随备份到期消除。已展示的历史和已发给模型的请求无法撤回，外部提供方可能留有副本。"), id: "account.deletion.retentionScope")
            }
        }.padding(.bottom, 8).clipped().navigationTitle(language.text("Delete account", "注销账号"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(uiColor: .systemBackground), for: .navigationBar, .tabBar)
            .toolbarBackground(.visible, for: .navigationBar, .tabBar)
    }

    private func paragraph(_ text: String, id: String) -> some View {
        RunReadableText(text: text)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier(id)
    }

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        Section(content: content, header: { ShellSectionHeading(title: title) })
    }
}
#endif
