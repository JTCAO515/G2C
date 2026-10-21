#if os(iOS)
import SwiftUI
import CJAuth

private enum EmailMode: String, CaseIterable {
    case signIn, register, recovery
    var action: AuthAction {
        switch self { case .signIn: .emailSignIn; case .register: .emailRegister; case .recovery: .emailRecovery }
    }
    func title(_ language: ShellLanguage) -> String {
        switch self {
        case .signIn: language.text("Sign in", "登录")
        case .register: language.text("Register", "注册")
        case .recovery: language.text("Recover password", "找回密码")
        }
    }
}

struct AccountView: View {
    @Bindable var host: AccountHost
    let shell: ShellState
    @State private var mode = EmailMode.signIn
    @State private var email = ""
    @State private var password = ""
    @FocusState private var editing: Bool
    private var language: ShellLanguage { shell.language }

    var body: some View {
        Form {
            Section {
                Text(language.text("Account access is not yet verified. Signing in does not grant invited-beta access.", "账号准入尚未验证。登录不代表获得受邀内测资格。"))
                Text(statusText).accessibilityIdentifier("account.status")
                if host.inputMissing {
                    Text(language.text("Enter the required email and password.", "请输入所需的邮箱和密码。"))
                }
                if host.requiresReconciliation {
                    Text(language.text("The original result must be checked before another attempt. Recovery checking is not connected yet.", "再次尝试前须核对原操作结果。目前尚未接入结果核对。"))
                }
            }
            Section(language.text("Email", "邮箱")) {
                Picker(language.text("Action", "操作"), selection: $mode) {
                    ForEach(EmailMode.allCases, id: \.self) { value in Text(value.title(language)).tag(value) }
                }
                .disabled(host.isWaiting || host.requiresReconciliation)
                TextField(language.text("Email address", "邮箱地址"), text: $email)
                    .keyboardType(.emailAddress).textContentType(.emailAddress)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .focused($editing).accessibilityIdentifier("account.email")
                if mode != .recovery {
                    SecureField(language.text("Password", "密码"), text: $password)
                        .textContentType(mode == .register ? .newPassword : .password)
                        .focused($editing).accessibilityIdentifier("account.password")
                }
                actionButton(mode.action, title: mode.title(language))
                if let reason = host.unavailableReason(for: mode.action) { Text(reasonText(reason)).font(.footnote) }
            }
            .disabled(host.isWaiting || host.requiresReconciliation)
            Section(language.text("Other sign-in options", "其他登录方式")) {
                actionButton(.googleSignIn, title: language.text("Continue with Google", "使用 Google 登录"))
                if let reason = host.unavailableReason(for: .googleSignIn) { Text(reasonText(reason)).font(.footnote) }
                actionButton(.appleSignIn, title: language.text("Continue with Apple", "使用 Apple 登录"))
                if let reason = host.unavailableReason(for: .appleSignIn) { Text(reasonText(reason)).font(.footnote) }
            }
            if host.isWaiting {
                Button(language.text("Cancel locally", "取消本地等待")) {
                    password = ""; email = ""; editing = false; host.cancel()
                }
            }
        }
        .navigationTitle(language.text("Account", "账号"))
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button(language.text("Done", "完成")) { editing = false }
            }
        }
        .onChange(of: mode) { _, _ in password = "" }
        .onChange(of: shell.generation) { _, _ in password = ""; email = ""; editing = false }
        .onDisappear { password = ""; email = ""; host.cancel() }
    }

    private func actionButton(_ action: AuthAction, title: String) -> some View {
        Button(title) {
            editing = false
            host.submit(action, email: email, password: &password)
        }
        .disabled(host.unavailableReason(for: action) != nil || host.isWaiting || host.requiresReconciliation)
    }

    private func reasonText(_ reason: UnavailableReason) -> String {
        switch reason {
        case .missingConfiguration: language.text("Not available — account services are not configured.", "尚未开放：账号服务未配置。")
        case .missingRuntimeMaterial: language.text("Not available — secure sign-in material is missing.", "尚未开放：缺少安全登录材料。")
        case .sdkAdapterNotInstalled: language.text("Not available — sign-in integration is missing.", "尚未开放：登录组件未接入。")
        case .hostCapabilityRequired: language.text("Not available — this device flow is not connected.", "尚未开放：设备登录流程未接入。")
        }
    }

    private var statusText: String {
        switch host.state {
        case .idle: language.text("No verified account session.", "尚无已验证的账号会话。")
        case .unavailable(let reason): reasonText(reason)
        case .waiting: language.text("Waiting for the account provider…", "正在等待账号提供方…")
        case .identityNeedsServerCheck: language.text("Identity returned; server verification is still required. Access is not granted.", "已返回身份信息，仍需服务端验证，尚未授予访问权限。")
        case .emailVerificationRequired: language.text("Email verification is required. Verification callback is not connected yet.", "需要验证邮箱，验证回调尚未接入。")
        case .verificationPending: language.text("Registration response received; email verification remains pending.", "已收到注册响应，仍待邮箱验证。")
        case .recoveryRequestAcknowledged: language.text("Recovery request acknowledged; email delivery and password reset are not verified.", "恢复请求已获响应，尚未核实邮件送达或密码重置。")
        case .passwordUpdatedRequiresSignIn: language.text("Password update reported; sign in again. Access is not granted.", "已返回密码更新结果，请重新登录，尚未授予访问权限。")
        case .cancelledLocally: language.text("Local waiting cancelled. Remote effects may still have occurred.", "已取消本地等待，远端操作仍可能已发生。")
        case .networkUnknown: language.text("The operation result is unknown. Do not resubmit.", "操作结果未知，请勿重复提交。")
        case .rejected: language.text("This attempt was rejected. Existing credentials were not deleted by this screen.", "本次尝试被拒绝，此页面未删除已有凭据。")
        case .callbackPurposeMismatch: language.text("The response does not match this action; it was not accepted.", "响应与本次操作不匹配，未接受该响应。")
        }
    }
}
#endif
