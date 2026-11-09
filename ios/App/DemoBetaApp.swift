#if G2C_DEMO_BETA && os(iOS)
import SwiftUI
import CJShell
import CJLioUser

struct DemoBetaRootView: View {
    let shell: ShellState
    let root: DevelopmentAccountRoot
    @Environment(\.scenePhase) private var phase
    var body: some View {
        Group {
            if root.finishingDemoCleanup {
                NavigationStack { LioAccountDeletion(shell: shell, root: root) }
            } else if case .signedIn = root.accounts.state, let trip = root.trip {
                LioHome(language: shell.language.lio, service: trip.messages.lio, isDemo: false, tripLibrary: trip.lioTripLibrary) {
                    LioLanguagePicker(shell: shell)
                    NavigationLink(shell.language.text("Delete account", "注销账号")) {
                        LioAccountDeletion(shell: shell, root: root)
                    }
                    Button(shell.language.text("Sign out", "退出登录")) { root.accounts.signOut() }
                }
                .id(trip.id)
            } else {
                DemoInviteView(shell: shell, accounts: root.accounts)
            }
        }
        .onChange(of: phase) { _, current in
            guard !root.finishingDemoCleanup else { return }
            if current == .active { root.accounts.resume() }
            else { root.accounts.suspend() }
        }
        .task(id: phase) {
            guard phase == .active else { return }
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(20)) } catch { return }
                if !root.finishingDemoCleanup { await root.accounts.recheckDemoSession() }
            }
        }
    }

}

private struct LioAccountDeletion: View {
    let shell: ShellState
    let root: DevelopmentAccountRoot
    @Environment(\.scenePhase) private var phase
    @State private var confirmed = false

    private var language: ShellLanguage { shell.language }

    var body: some View {
        Form {
            Text(language.text(
                "This requests deletion of your G2C account and its data. Saved content may still be visible on other devices while they’re offline. Backups roll off after 30 days. Other services manage their own copies.",
                "注销会申请删除你的 G2C 账号及其数据。其他设备离线时可能仍能看到已保存的内容。备份按 30 天滚动保留，其他服务的副本由各自管理。"))
            if let host = root.cleanup {
                controls(host)
            } else {
                Text(language.text("Account deletion is temporarily unavailable.", "暂时无法注销账号。"))
            }
        }
        .navigationTitle(language.text("Delete account", "注销账号"))
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private func controls(_ host: AccountCleanupContainerHost) -> some View {
        let value = host.presentation
        if value.controlsFinalized {
            Text(language.text("Your account was deleted and data on this device was cleared.", "账号已注销，本机数据已清理。"))
            Button(language.text("Done", "完成")) { root.finishDemoCleanup() }
                .accessibilityIdentifier("demo.cleanup.done")
        } else if value.unavailable || value.unknown {
            Text(language.text("Account deletion information is temporarily unavailable. Keep this device connected.",
                               "暂时无法显示注销信息，请保持联网。"))
        } else if value.businessStopped {
            Text(language.text("You can’t use this account on this device while cleanup continues.",
                               "清理期间，暂时无法在本机使用此账号。"))
        }
        if host.busy || value.preparing { ProgressView() }
        if value.canReview {
            Button(language.text("Continue", "继续")) { host.perform(.review) }
                .disabled(host.busy)
        }
        if value.canConfirm {
            Toggle(language.text("I understand that this deletes my account and its data.",
                                 "我已了解，注销会删除我的账号和数据。"), isOn: $confirmed)
            Button(language.text("Delete my account", "注销我的账号"), role: .destructive) {
                confirmed = false
                host.perform(.confirm)
            }
            .disabled(!confirmed || host.busy)
        }
        if value.canCleanDevice {
            Button(language.text("Clear data on this device", "清除本机数据"), role: .destructive) {
                host.perform(.cleanDevice)
            }
            .disabled(host.busy)
        }
        if value.canFinalizeControls {
            Button(language.text("Finish clearing this device", "清理本机剩余数据"), role: .destructive) {
                host.perform(.finalizeControls)
            }
            .disabled(host.busy)
        }
        Color.clear.frame(height: 0).accessibilityHidden(true)
            .task(id: phase) {
                guard phase == .active else { return }
                await followUp(host)
            }
    }

    private func followUp(_ host: AccountCleanupContainerHost) async {
        var preferDevice = false
        while !Task.isCancelled, root.cleanup === host, !host.presentation.controlsFinalized {
            let value = host.presentation
            if !host.busy {
                let needsAccountUpdate = value.canRead && (value.unknown || value.businessStopped)
                if value.canReportDevice {
                    // The journal permits a new receipt only for an eligible
                    // device result and blocks reuse after an ambiguous write.
                    host.perform(.reportDevice)
                } else if value.canReadDevice, preferDevice || !needsAccountUpdate {
                    host.perform(.checkDevice)
                    preferDevice = false
                } else if needsAccountUpdate {
                    host.perform(.checkOriginal)
                    preferDevice = true
                }
            }
            do { try await Task.sleep(for: .seconds(20)) } catch { return }
        }
    }
}

private struct DemoInviteView: View {
    let shell: ShellState
    let accounts: DevelopmentAccountHost
    @State private var code = ""
    @State private var pendingConsent: ConsentAction?
    @FocusState private var enteringCode: Bool
    private var language: ShellLanguage { shell.language }

    private enum ConsentAction: String, Identifiable {
        case signIn, restore
        var id: Self { self }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LioLanguagePicker(shell: shell)
                }
                Section {
                    SecureField(language.text("Invitation code", "邀请码"), text: $code)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($enteringCode)
                        .accessibilityIdentifier("demo.invite.code")
                    Button(language.text("Continue", "继续")) {
                        enteringCode = false
                        pendingConsent = .signIn
                    }
                    .disabled(code.isEmpty || accounts.state == .checking)
                    .accessibilityIdentifier("demo.invite.continue")
                    Button(language.text("Continue with your account", "继续使用账号")) {
                        enteringCode = false
                        pendingConsent = .restore
                    }
                    .disabled(accounts.state == .checking)
                    .accessibilityIdentifier("demo.invite.restore")
                }
                if let notice {
                    Section { Text(notice).accessibilityIdentifier("demo.invite.status") }
                }
            }
            .navigationTitle(language.text("Internal demo", "内部演示"))
        }
        .sheet(item: $pendingConsent) { action in
            NavigationStack {
                DemoV2ConsentView(
                    language: language, canAgree: accounts.state != .checking && (action != .signIn || !code.isEmpty),
                    onAgree: { completeConsent(action) }, onBack: { pendingConsent = nil })
            }
        }
    }

    private func completeConsent(_ action: ConsentAction) {
        guard pendingConsent == action, accounts.state != .checking else { return }
        pendingConsent = nil
        switch action {
        case .signIn:
            let candidate = code
            guard !candidate.isEmpty else { return }
            code = ""
            let starter: DemoStarterLanguage = language == .chinese ? .zh : .en
            accounts.signIn { try await DemoInviteClient.exchange(code: candidate, consent: true, language: starter) }
        case .restore:
            code = ""
            accounts.restore()
        }
    }

    private var notice: String? {
        switch accounts.state {
        case .checking: language.text("Signing you in…", "正在登录…")
        case .expired: language.text("Your sign-in expired. Use an invitation code to sign in again.", "登录已过期，请使用邀请码重新登录。")
        case .rejected: language.text("We couldn’t sign you in. Ask your demo organizer for access.", "暂时无法登录，请联系演示组织者。")
        case .networkUnknown: language.text("We couldn’t sign you in. Check your connection and try again.", "暂时无法登录，请检查网络后重试。")
        case .storageUnavailable: language.text("Sign-in is temporarily unavailable.", "暂时无法登录。")
        case .paused, .signedOut, .signedIn: nil
        }
    }
}
#endif
