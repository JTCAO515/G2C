#if os(iOS)
import SwiftUI

/// Safe presentation while the existing account host verifies saved sign-in.
/// It contains no private chat content and grants no client or sending access.
public struct LioSessionRecoveryView: View {
    private let language: LioLanguage
    private let showsRetry: Bool
    private let retry: () -> Void
    private let signOut: () -> Void

    public init(language: LioLanguage, showsRetry: Bool,
                retry: @escaping () -> Void, signOut: @escaping () -> Void) {
        self.language = language
        self.showsRetry = showsRetry
        self.retry = retry
        self.signOut = signOut
    }

    public var body: some View {
        VStack(spacing: LioTheme.Spacing.lg) {
            VStack(spacing: LioTheme.Spacing.xs) {
                LioPortrait(size: 44)
                Text("Lio")
                    .font(.headline)
                    .foregroundStyle(LioTheme.ink)
            }
            .padding(.top, LioTheme.Spacing.md)
            Spacer(minLength: LioTheme.Spacing.lg)
            VStack(spacing: LioTheme.Spacing.md) {
                if showsRetry {
                    Text(language.text("Couldn’t connect. Your sign-in is still saved.",
                                       "暂时连接不上，登录信息仍已保留。"))
                        .font(.body)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("lio.session.notice")
                    Button(action: retry) {
                        Text(language.text("Try again", "重试"))
                            .frame(minHeight: 44)
                    }
                    .buttonStyle(.borderedProminent)
                    .foregroundStyle(LioTheme.onVermilion)
                    .accessibilityIdentifier("lio.session.retry")
                } else {
                    ProgressView {
                        Text(language.text("Restoring your chat…", "正在恢复对话…"))
                            .font(.body)
                            .foregroundStyle(LioTheme.inkSecondary)
                    }
                    .accessibilityIdentifier("lio.session.progress")
                }
            }
            .frame(maxWidth: 420)
            Spacer(minLength: LioTheme.Spacing.lg)
            Button(action: signOut) {
                Text(language.text("Sign out", "退出登录"))
                    .font(.body)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .frame(minHeight: 44)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.session.signout")
        }
        .padding(.horizontal, LioTheme.Spacing.lg)
        .padding(.bottom, LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(LioTheme.paper)
        .tint(LioTheme.vermilion)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("lio.session.recovery")
    }
}
#endif
