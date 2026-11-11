#if os(iOS)
import SwiftUI
import CJRunClient

struct LioPortrait: View {
    let size: CGFloat

    var body: some View {
        Image("LioAvatar", bundle: .module)
            .resizable()
            .scaledToFill()
            .frame(width: size, height: size)
            .clipShape(Circle())
            .accessibilityHidden(true)
    }
}

public struct LioInvitationView<Settings: View>: View {
    private enum Consent: String, Identifiable {
        case invite, continueAccount
        var id: Self { self }
    }

    private let language: LioLanguage
    private let isBusy: Bool
    private let notice: String?
    private let onInvite: (String) -> Void
    private let onRestore: () -> Void
    private let settings: Settings
    @State private var code = ""
    @State private var consent: Consent?
    @FocusState private var enteringCode: Bool

    public init(language: LioLanguage, isBusy: Bool, notice: String?,
                onInvite: @escaping (String) -> Void, onRestore: @escaping () -> Void,
                @ViewBuilder settings: () -> Settings) {
        self.language = language
        self.isBusy = isBusy
        self.notice = notice
        self.onInvite = onInvite
        self.onRestore = onRestore
        self.settings = settings()
    }

    public var body: some View {
        NavigationStack {
            Form {
                Group {
                    Section {
                        HStack(spacing: 14) {
                            LioPortrait(size: 58)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(language.text("Meet Lio", "和 Lio 聊聊"))
                                .font(LioTheme.display(.headline))
                                .fixedSize(horizontal: false, vertical: true)
                                RunReadableText(text: language.text("Use your invitation to start chatting.", "输入邀请码，开始聊你的旅行。"))
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    Section {
                        SecureField(language.text("Invitation code", "邀请码"), text: $code)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .focused($enteringCode)
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("demo.invite.code")
                        Button(language.text("Continue", "继续")) {
                            enteringCode = false
                            consent = .invite
                        }
                        .disabled(code.isEmpty || isBusy)
                        .accessibilityIdentifier("demo.invite.continue")
                        Button(language.text("Continue with your account", "继续使用账号")) {
                            enteringCode = false
                            consent = .continueAccount
                        }
                        .disabled(isBusy)
                        .accessibilityIdentifier("demo.invite.restore")
                    }
                    if let notice {
                        Section {
                            RunReadableText(text: notice)
                                .accessibilityIdentifier("demo.invite.status")
                        }
                    }
                    Section { settings }
                }
                .lioRow()
            }
            .lioPage()
            .navigationTitle(language.text("Internal demo", "内部演示"))
        }
        .tint(LioTheme.vermilion)
        .sheet(item: $consent) { action in
            NavigationStack {
                consentPage(action)
            }
            .tint(LioTheme.vermilion)
        }
    }

    private func consentPage(_ action: Consent) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                LioPortrait(size: 58)
                Text(language.text("Use fictional trip details", "请使用虚构旅行信息"))
                    .font(LioTheme.display(.headline))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                // Interim internal-demo wording until #225 is decided.
                RunReadableText(text: language.text(
                    "This is an internal demo. Please use fictional trip details and leave out personal information.",
                    "这是内部演示。请使用虚构的旅行信息，别填写个人信息。"))
                    .accessibilityIdentifier("demo.invite.consent")
                Button {
                    agree(to: action)
                } label: {
                    RunReadableText(text: language.text("Agree and continue", "同意并继续"))
                        .frame(minHeight: 44, alignment: .leading)
                }
                .buttonStyle(.bordered)
                .disabled(isBusy || (action == .invite && code.isEmpty))
                .accessibilityIdentifier("demo.invite.signin")
                Button {
                    consent = nil
                } label: {
                    RunReadableText(text: language.text("Back", "返回"))
                        .frame(minHeight: 44, alignment: .leading)
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("lio.invite.back")
            }
            .frame(maxWidth: 480, alignment: .leading)
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Internal demo consent", "内部演示同意"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func agree(to action: Consent) {
        guard consent == action, !isBusy else { return }
        consent = nil
        switch action {
        case .invite:
            let invitation = code
            guard !invitation.isEmpty else { return }
            code = ""
            onInvite(invitation)
        case .continueAccount:
            code = ""
            onRestore()
        }
    }
}
#endif
