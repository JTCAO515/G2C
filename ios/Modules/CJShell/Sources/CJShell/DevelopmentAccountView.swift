#if os(iOS)
import SwiftUI

struct DevelopmentAccountView: View {
    let host: DevelopmentAccountHost
    let language: ShellLanguage

    var body: some View {
        List {
            Section {
                Text(language.text("Development session", "开发会话")).font(.headline)
                Text(status).accessibilityIdentifier("account.development.status")
                if host.state == .checking { ProgressView() }
            }
            Section {
                ForEach(host.choices) { choice in
                    Button(language.text("Sign in as \(choice.label)", "使用 \(choice.label) 登录")) {
                        host.signIn(choice.id)
                    }.accessibilityIdentifier("account.development.signin.\(choice.id)")
                }
                Button(language.text("Restore saved session", "恢复已保存的会话")) { host.restore() }
                    .accessibilityIdentifier("account.development.restore")
                Button(language.text("Sign out", "退出登录")) { host.signOut() }
                    .accessibilityIdentifier("account.development.signout")
            }
        }.navigationTitle(language.text("Account", "账号"))
    }

    private var status: String {
        switch host.state {
        case .signedOut: language.text("Signed out", "未登录")
        case .checking: language.text("Checking session…", "正在验证会话…")
        case .signedIn(let account): language.text("Signed in as \(account)", "已登录：\(account)")
        case .paused: language.text("Session paused", "会话已暂停")
        case .rejected: language.text("Sign-in was rejected. Check the account and try again.", "登录被拒绝，请核对账号后重试。")
        case .expired: language.text("This session has expired. Sign in again.", "会话已过期，请重新登录。")
        case .networkUnknown: language.text("Cannot verify the session right now. Saved credentials have been kept.", "暂时无法验证会话，已保留保存的凭据。")
        case .storageUnavailable: language.text("Secure session storage is unavailable.", "安全会话存储暂不可用。")
        }
    }
}
#endif
