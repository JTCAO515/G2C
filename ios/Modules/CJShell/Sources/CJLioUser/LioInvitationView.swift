#if os(iOS)
import SwiftUI
import CJRunClient

public struct LioPortrait: View {
    let size: CGFloat

    public init(size: CGFloat) { self.size = size }

    public var body: some View {
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
    @Environment(\.colorScheme) private var colorScheme
    @FocusState private var enteringCode: Bool
    @State private var invalidFormat = false
    @ScaledMetric(relativeTo: .body) private var codeHeight = 44

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
                                RunReadableText(text: language.text("Use your invitation to start chatting.", "输入邀请码，开始聊你的旅行。"), color: LioTheme.ink)
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    Section {
                        SecureField(language.text("Invitation code", "邀请码"), text: $code,
                                    prompt: Text(language.text("Code", "邀请码")).foregroundColor(LioTheme.inkSecondary))
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.asciiCapable)
                            .foregroundColor(LioTheme.ink)
                            .focused($enteringCode)
                            .frame(minHeight: codeHeight)
                            .accessibilityIdentifier("demo.invite.code")
                            .background(LioInvitationInputTraits().accessibilityHidden(true))
                        Button {
                            enteringCode = false
                            guard LioInvitationInput.accepts(code) else { invalidFormat = true; return }
                            invalidFormat = false
                            consent = .invite
                        } label: {
                            RunReadableText(text: language.text("Continue", "继续"),
                                color: code.isEmpty || isBusy ? LioTheme.inkSecondary : LioTheme.vermilion)
                        }
                        .buttonStyle(LioInvitationActionStyle())
                        .disabled(code.isEmpty || isBusy)
                        .accessibilityIdentifier("demo.invite.continue")
                        Button {
                            enteringCode = false
                            consent = .continueAccount
                        } label: {
                            RunReadableText(text: language.text("Continue with your account", "继续使用账号"),
                                color: isBusy ? LioTheme.inkSecondary : LioTheme.vermilion)
                        }
                        .buttonStyle(LioInvitationActionStyle())
                        .disabled(isBusy)
                        .accessibilityIdentifier("demo.invite.restore")
                    }
                    if invalidFormat {
                        Section {
                            RunReadableText(text: LioInvitationInput.formatMessage(language), color: LioTheme.ink)
                                .accessibilityIdentifier("demo.invite.format")
                        }
                    }
                    if let notice {
                        Section {
                            RunReadableText(text: notice, color: LioTheme.ink)
                                .accessibilityIdentifier("demo.invite.status")
                        }
                    }
                    Section { settings }
                }
                .lioRow()
            }
            .lioPage()
            .navigationTitle(language.text("Internal demo", "内部演示"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(LioTheme.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(colorScheme, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    RunReadableText(text: language.text("Internal demo", "内部演示"), style: .headline, color: LioTheme.ink)
                        .fixedSize()
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier("lio.invite.heading")
                }
            }

        }
        .tint(LioTheme.vermilion)
        .onChange(of: code) { _, _ in invalidFormat = false }
        .sheet(item: $consent) { action in
            NavigationStack {
                consentPage(action)
            }
            .tint(LioTheme.vermilion)
        }
    }

    private func consentPage(_ action: Consent) -> some View {
        LioDemoNoticePage(language: language) {
            Button {
                agree(to: action)
            } label: {
                RunReadableText(text: language.text("Agree and continue", "同意并继续"), color: LioTheme.ink)
                    .frame(minHeight: 44, alignment: .leading)
            }
            .buttonStyle(.bordered)
            .disabled(isBusy || (action == .invite && code.isEmpty))
            .accessibilityIdentifier("demo.invite.signin")
            Button {
                consent = nil
            } label: {
                RunReadableText(text: language.text("Back", "返回"), color: LioTheme.ink)
                    .frame(minHeight: 44, alignment: .leading)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("lio.invite.back")
        }
    }

    private func agree(to action: Consent) {
        guard consent == action, !isBusy else { return }
        consent = nil
        switch action {
        case .invite:
            let invitation = code
            guard LioInvitationInput.accepts(invitation) else { invalidFormat = true; return }
            code = ""
            onInvite(invitation)
        case .continueAccount:
            code = ""
            onRestore()
        }
    }
}
#endif

#if os(iOS)
private struct LioInvitationActionStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
            .opacity(configuration.isPressed && isEnabled ? 0.85 : 1)
    }
}
#endif
