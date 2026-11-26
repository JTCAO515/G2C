import Foundation

/// #1891: the new first screen (email, Apple and Google placeholders, then a small way in to the internal test
/// sign-in), behind `G2CNewSignInScreenEnabled`, off unless the build says YES. The three channels are
/// placeholders until #1883: tapping one only explains that it is coming soon. Nothing is sent and nothing is
/// collected. The invitation sign-in itself is unchanged; only its page is new.
enum LioNewSignInFeature {
    static let infoKey = "G2CNewSignInScreenEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool {
        if enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) { return true }
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-new-signin-preview")
        #else
        return false
        #endif
    }
}

/// The sign-in channels shown as placeholders in build 58.
enum LioSignInChannel: String, CaseIterable, Identifiable, Sendable {
    case apple, google, email
    var id: Self { self }

    /// Titles follow Apple's and Google's own button wording.
    func title(_ language: LioLanguage) -> String {
        switch self {
        case .apple: language.text("Sign in with Apple", "通过 Apple 登录")
        case .google: language.text("Sign in with Google", "使用 Google 账号登录")
        case .email: language.text("Sign in with email", "使用邮箱登录")
        }
    }

    func comingSoon(_ language: LioLanguage) -> String {
        switch self {
        case .apple: language.text("Sign in with Apple is coming soon. For now, please use your internal test invitation code.",
                                   "Apple 登录即将开放，请先使用内部测试邀请码。")
        case .google: language.text("Sign in with Google is coming soon. For now, please use your internal test invitation code.",
                                    "Google 登录即将开放，请先使用内部测试邀请码。")
        case .email: language.text("Email sign-in is coming soon. For now, please use your internal test invitation code.",
                                   "邮箱登录即将开放，请先使用内部测试邀请码。")
        }
    }
}

/// Colours of the sign-in screen as numbers, so a host test can check contrast in both appearances. Apple's and
/// Google's button colours come from their brand guidelines and do not follow the Lio theme.
enum LioSignInColors {
    struct Pair: Sendable, Equatable {
        let light: UInt32
        let dark: UInt32
    }

    static let base = Pair(light: 0xF7F6F4, dark: 0x09090B)
    static let ink = Pair(light: 0x0E0E11, dark: 0xF4F4F6)
    static let inkSecondary = Pair(light: 0x3A3A42, dark: 0xD2D2DA)
    /// Decorative outlines only; never used for text.
    static let line = Pair(light: 0xDEDCD8, dark: 0x2A2A30)
    /// The email button, the code field and small cards.
    static let field = Pair(light: 0xFFFFFF, dark: 0x17171B)
    static let ember = Pair(light: 0xFF5B3A, dark: 0xFF5B3A)
    static let amber = Pair(light: 0xFFB34D, dark: 0xF2A23A)
    static let iris = Pair(light: 0x8A6CFF, dark: 0x6E52FF)
    /// The glows' opacity at their centre. Text can sit where all three overlap, so the test checks text against
    /// all three stacked at this opacity.
    static let glowPeakLight = 0.24
    static let glowPeakDark = 0.28

    // Apple: black on light backgrounds, white on dark (Sign in with Apple, Human Interface Guidelines).
    static let appleFill = Pair(light: 0x000000, dark: 0xFFFFFF)
    static let appleText = Pair(light: 0xFFFFFF, dark: 0x000000)
    // Google: the light and dark themes of the Sign in with Google branding guidelines.
    static let googleFill = Pair(light: 0xFFFFFF, dark: 0x131314)
    static let googleStroke = Pair(light: 0x747775, dark: 0x8E918F)
    static let googleText = Pair(light: 0x1F1F1F, dark: 0xE3E3E3)
}

#if os(iOS)
import SwiftUI
import UIKit
import CJRunClient

// MARK: - Palette

/// SwiftUI colours for `LioSignInColors`.
enum LioSignInPalette {
    static func color(_ pair: LioSignInColors.Pair) -> Color {
        Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? uiColor(pair.dark) : uiColor(pair.light) })
    }

    static func uiColor(_ hex: UInt32) -> UIColor {
        UIColor(red: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }

    static let base = color(LioSignInColors.base)
    static let ink = color(LioSignInColors.ink)
    static let inkSecondary = color(LioSignInColors.inkSecondary)
    static let line = color(LioSignInColors.line)
    static let field = color(LioSignInColors.field)
    static let ember = color(LioSignInColors.ember)
    static let amber = color(LioSignInColors.amber)
    static let iris = color(LioSignInColors.iris)
    static let appleFill = color(LioSignInColors.appleFill)
    static let appleText = color(LioSignInColors.appleText)
    static let googleFill = color(LioSignInColors.googleFill)
    static let googleStroke = color(LioSignInColors.googleStroke)
    static let googleText = color(LioSignInColors.googleText)
}

// MARK: - Centered label

/// A centered multiline UIKit label. Like `RunReadableText`, it measures in UIKit so long text wraps fully at the
/// largest accessibility size, where a SwiftUI `Text` over the backdrop failed the contrast audit.
struct LioSignInCenteredText: UIViewRepresentable {
    let text: String
    let color: Color
    @Environment(\.dynamicTypeSize) private var size

    func makeUIView(context: Context) -> UILabel {
        let label = UILabel()
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        label.textAlignment = .center
        label.adjustsFontForContentSizeCategory = true
        label.setContentCompressionResistancePriority(.required, for: .vertical)
        return label
    }

    func updateUIView(_ label: UILabel, context: Context) {
        label.text = text
        label.textColor = UIColor(color)
        let preferred = UIFont.preferredFont(forTextStyle: .body,
            compatibleWith: UITraitCollection(preferredContentSizeCategory: UIContentSizeCategory(size)))
        let medium = preferred.fontDescriptor.addingAttributes([.traits: [UIFontDescriptor.TraitKey.weight: UIFont.Weight.medium]])
        label.font = UIFont(descriptor: medium, size: preferred.pointSize)
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UILabel, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        let measured = uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
        return CGSize(width: width, height: measured.height)
    }
}

// MARK: - Backdrop

enum LioSignInMotion {
    /// Seconds the entrance takes; after that the screen is still.
    static let settle: Double = 1.6
}

/// Soft glows behind the content. They drift into place once when the page appears and then
/// stay still, so nothing keeps moving behind the text; no motion at all when Reduce Motion is on.
struct LioSignInBackdrop: View {
    var quiet = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme
    @State private var drift = false

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            let height = proxy.size.height
            ZStack {
                LioSignInPalette.base
                glow(LioSignInPalette.ember, size: width * 0.95)
                    .offset(x: drift ? -width * 0.30 : -width * 0.12, y: -height * (drift ? 0.30 : 0.36))
                glow(LioSignInPalette.amber, size: width * 0.70)
                    .offset(x: drift ? width * 0.32 : width * 0.18, y: -height * (drift ? 0.38 : 0.30))
                glow(LioSignInPalette.iris, size: width * 0.80)
                    .offset(x: drift ? width * 0.05 : width * 0.25, y: -height * (drift ? 0.16 : 0.22))
            }
            .frame(width: width, height: height)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .allowsHitTesting(false)
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeOut(duration: LioSignInMotion.settle)) { drift = true }
        }
    }

    private var glowOpacity: Double {
        let dark = colorScheme == .dark
        let base = dark ? LioSignInColors.glowPeakDark : LioSignInColors.glowPeakLight
        return quiet ? base * 0.55 : base
    }

    /// A radial gradient rather than a blurred shape: it draws the same soft light without an offscreen blur layer.
    private func glow(_ color: Color, size: CGFloat) -> some View {
        Circle()
            .fill(RadialGradient(colors: [color.opacity(glowOpacity), color.opacity(glowOpacity * 0.45), color.opacity(0)],
                                 center: .center, startRadius: .zero, endRadius: size * 0.75))
            .frame(width: size * 1.5, height: size * 1.5)
    }
}

// MARK: - Emblem

/// Lio's portrait in a gradient ring that turns once as the page appears.
struct LioSignInEmblem: View {
    @ScaledMetric(relativeTo: .largeTitle) private var size: CGFloat = 76
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var turn = false
    private let ringWidth: CGFloat = 2.5

    var body: some View {
        let portrait = min(size, 120)
        ZStack {
            Circle()
                .fill(RadialGradient(colors: [LioSignInPalette.ember.opacity(0.30), LioSignInPalette.ember.opacity(0)],
                                     center: .center, startRadius: portrait * 0.45, endRadius: portrait * 0.62))
                .frame(width: portrait * 1.24, height: portrait * 1.24)
            Circle()
                .stroke(AngularGradient(colors: ringColors, center: .center), lineWidth: ringWidth)
                .frame(width: portrait + 10, height: portrait + 10)
                .rotationEffect(.degrees(turn ? 360 : 0))
            LioPortrait(size: portrait)
        }
        .frame(width: portrait + 14, height: portrait + 14)
        .accessibilityHidden(true)
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeInOut(duration: LioSignInMotion.settle)) { turn = true }
        }
    }

    private let ringColors = [LioSignInPalette.ember, LioSignInPalette.amber, LioSignInPalette.iris, LioSignInPalette.ember]
}

// MARK: - Buttons

struct LioSignInPressStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            // Disabled controls change colour instead of fading, so their text keeps its contrast.
            .opacity(isEnabled && configuration.isPressed ? 0.82 : 1)
            .scaleEffect(configuration.isPressed && isEnabled ? 0.985 : 1)
            .animation(LioTheme.Motion.micro, value: configuration.isPressed)
    }
}

/// One channel button. Apple and Google use their own colours, logo and wording; email follows the screen's look.
struct LioSignInChannelButton: View {
    let channel: LioSignInChannel
    let language: LioLanguage
    let action: () -> Void
    @ScaledMetric(relativeTo: .body) private var height: CGFloat = 52
    @ScaledMetric(relativeTo: .body) private var logo: CGFloat = 19
    private let strokeWidth: CGFloat = 1

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                mark
                Text(channel.title(language))
                    .font(.body.weight(.semibold))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(text)
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.vertical, LioTheme.Spacing.xs)
            .frame(maxWidth: .infinity, minHeight: height)
            .background(fill, in: Capsule())
            .overlay { Capsule().stroke(stroke, lineWidth: strokeWidth).accessibilityHidden(true) }
            .contentShape(Capsule())
        }
        .buttonStyle(LioSignInPressStyle())
        .accessibilityLabel(channel.title(language))
        .accessibilityHint(language.text("Coming soon", "即将开放"))
        .accessibilityIdentifier("lio.signin.\(channel.rawValue)")
    }

    @ViewBuilder private var mark: some View {
        switch channel {
        case .apple:
            Image(systemName: "apple.logo").font(.system(size: logo, weight: .medium)).accessibilityHidden(true)
        case .google:
            Image("GoogleG", bundle: .module).resizable().scaledToFit()
                .frame(width: logo, height: logo).accessibilityHidden(true)
        case .email:
            Image(systemName: "envelope").font(.system(size: logo * 0.92, weight: .medium)).accessibilityHidden(true)
        }
    }

    private var fill: Color {
        switch channel {
        case .apple: LioSignInPalette.appleFill
        case .google: LioSignInPalette.googleFill
        case .email: LioSignInPalette.field
        }
    }
    private var stroke: Color {
        switch channel {
        case .apple: .clear
        case .google: LioSignInPalette.googleStroke
        case .email: LioSignInPalette.line
        }
    }
    private var text: Color {
        switch channel {
        case .apple: LioSignInPalette.appleText
        case .google: LioSignInPalette.googleText
        case .email: LioSignInPalette.ink
        }
    }
}

/// A status line in a soft card, for the format hint and the sign-in notice.
struct LioSignInMessage: View {
    let text: String
    let symbol: String
    let identifier: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
            Image(systemName: symbol).foregroundStyle(LioTheme.vermilion).accessibilityHidden(true)
            Text(text).font(.subheadline).foregroundStyle(LioSignInPalette.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier(identifier)
            Spacer(minLength: 0)
        }
        .padding(LioTheme.Spacing.sm)
        .background(LioSignInPalette.field.opacity(0.85),
                    in: RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous)
                .stroke(LioSignInPalette.line, lineWidth: LioTheme.outlineWidth).accessibilityHidden(true)
        }
    }
}

// MARK: - Welcome

/// The first screen: who Lio is, the three channels (placeholders), and the small internal-test entry.
struct LioSignInWelcome<Settings: View>: View {
    let language: LioLanguage
    let notice: String?
    let settings: Settings
    let onInvite: () -> Void
    @State private var comingSoon: LioSignInChannel?
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(spacing: 0) {
                    if !typeSize.isAccessibilitySize {
                        HStack {
                            Spacer(minLength: 0)
                            settings.fixedSize()
                                .padding(.horizontal, LioTheme.Spacing.sm)
                                .background(LioSignInPalette.field.opacity(0.7), in: Capsule())
                                .overlay { Capsule().stroke(LioSignInPalette.line, lineWidth: LioTheme.outlineWidth).accessibilityHidden(true) }
                        }
                        .padding(.top, LioTheme.Spacing.xs)
                    }
                    Spacer(minLength: LioTheme.Spacing.lg)
                    header
                    Spacer(minLength: LioTheme.Spacing.xl)
                    Spacer(minLength: 0)
                    actions
                }
                .frame(maxWidth: 440)
                .padding(.horizontal, LioTheme.Spacing.lg)
                .padding(.bottom, LioTheme.Spacing.md)
                .frame(maxWidth: .infinity, minHeight: proxy.size.height)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .background(LioSignInBackdrop())
        .toolbar(.hidden, for: .navigationBar)
        .alert(language.text("Coming soon", "即将开放"),
               isPresented: Binding(get: { comingSoon != nil }, set: { if !$0 { comingSoon = nil } }),
               presenting: comingSoon) { _ in
            Button(language.text("Use invitation code", "使用邀请码")) { onInvite() }
                .accessibilityIdentifier("lio.signin.soon.invite")
            Button(language.text("OK", "好"), role: .cancel) {}
        } message: { channel in
            Text(channel.comingSoon(language))
        }
    }

    private var header: some View {
        VStack(spacing: LioTheme.Spacing.md) {
            LioSignInEmblem()
            ViewThatFits(in: .horizontal) {
                HStack(spacing: LioTheme.Spacing.xs) { wordmark; betaTag }
                VStack(spacing: LioTheme.Spacing.xxs) { wordmark; betaTag }
            }
            Text(language.text("Your local helper in China", "你在中国的本地助手"))
                .font(.system(.largeTitle, design: .default, weight: .bold))
                .foregroundStyle(LioSignInPalette.ink)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("lio.signin.heading")
            LioSignInCenteredText(text: language.text("Plans, transport, translation and everyday errands — just ask Lio.",
                                                      "行程、交通、翻译和日常小事，随时问 Lio。"),
                                  color: LioSignInPalette.inkSecondary)
        }
    }

    // UIKit labels, as on the existing pages, so the wordmark follows every text size.
    private var wordmark: some View {
        RunReadableText(text: "Go2China", style: .subheadlineSemibold, color: LioSignInPalette.ink)
            .fixedSize()
    }

    private var betaTag: some View {
        RunReadableText(text: "BETA", style: .subheadlineSemibold, color: LioSignInPalette.inkSecondary)
            .fixedSize()
            .padding(.horizontal, 6).padding(.vertical, 2)
            .overlay { Capsule().stroke(LioSignInPalette.line, lineWidth: LioTheme.outlineWidth).accessibilityHidden(true) }
    }

    private var actions: some View {
        VStack(spacing: LioTheme.Spacing.sm) {
            if let notice {
                LioSignInMessage(text: notice, symbol: "info.circle", identifier: "lio.signin.status")
                    .padding(.bottom, LioTheme.Spacing.xxs)
            }
            ForEach(LioSignInChannel.allCases) { channel in
                LioSignInChannelButton(channel: channel, language: language) { comingSoon = channel }
            }
            HStack(spacing: LioTheme.Spacing.sm) {
                rule
                Text(language.text("or", "或")).font(.footnote).foregroundStyle(LioSignInPalette.inkSecondary)
                rule
            }
            .padding(.vertical, LioTheme.Spacing.xxs)
            .accessibilityHidden(true)
            Button(action: onInvite) {
                HStack(spacing: 6) {
                    Image(systemName: "ticket").accessibilityHidden(true)
                    Text(language.text("Use an internal test invitation code", "使用内部测试邀请码"))
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                    Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).accessibilityHidden(true)
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(LioSignInPalette.ink)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(LioSignInPressStyle())
            .accessibilityIdentifier("lio.signin.invite")
            // At accessibility sizes the language row moves to the end, full width, so it never runs off screen.
            if typeSize.isAccessibilitySize {
                settings
                    .padding(.horizontal, LioTheme.Spacing.md)
                    .background(LioSignInPalette.field.opacity(0.85),
                                in: RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous))
                    .padding(.top, LioTheme.Spacing.md)
            }
        }
    }

    private var rule: some View {
        Rectangle().fill(LioSignInPalette.line).frame(height: LioTheme.outlineWidth)
    }
}

// MARK: - Internal test page

/// The redesigned invitation page. It only lays out the existing controls: the code, its checks, the consent
/// step and the sign-in stay with `LioInvitationView`.
struct LioInternalTestPage<Settings: View>: View {
    let language: LioLanguage
    let isBusy: Bool
    let notice: String?
    let invalidFormat: Bool
    @Binding var code: String
    var enteringCode: FocusState<Bool>.Binding
    let settings: Settings
    let onContinue: () -> Void
    let onRestore: () -> Void
    @Environment(\.colorScheme) private var colorScheme
    @ScaledMetric(relativeTo: .body) private var fieldHeight: CGFloat = 56
    @ScaledMetric(relativeTo: .body) private var buttonHeight: CGFloat = 52
    private let focusWidth: CGFloat = 1.5

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                // The form sits about a third of the way down; the language row stays at the bottom.
                VStack(alignment: .leading, spacing: 0) {
                    Spacer(minLength: LioTheme.Spacing.md)
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                        header
                        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                            field
                            if invalidFormat {
                                LioSignInMessage(text: LioInvitationInput.formatMessage(language),
                                                 symbol: "exclamationmark.circle", identifier: "demo.invite.format")
                            }
                            if let notice {
                                LioSignInMessage(text: notice, symbol: "info.circle", identifier: "demo.invite.status")
                            }
                        }
                        VStack(spacing: LioTheme.Spacing.xs) {
                            primary
                            restore
                        }
                    }
                    Spacer(minLength: LioTheme.Spacing.xl)
                    Spacer(minLength: 0)
                    settingsRow
                }
                .frame(maxWidth: 480, alignment: .leading)
                .padding(.horizontal, LioTheme.Spacing.lg)
                .padding(.bottom, LioTheme.Spacing.md)
                .frame(maxWidth: .infinity, minHeight: proxy.size.height)
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .scrollBounceBehavior(.basedOnSize)
        .background(LioSignInBackdrop(quiet: true))
        .navigationTitle(language.text("Internal testing", "内部测试"))
        .navigationBarTitleDisplayMode(.inline)
        // A solid bar in the page colour, as on the existing page, so the title never sits on the glow.
        .toolbarBackground(LioSignInPalette.base, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .principal) {
                RunReadableText(text: language.text("Internal testing", "内部测试"), style: .headline,
                                color: LioSignInPalette.ink)
                    .fixedSize()
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("lio.invite.heading")
            }
            if enteringCode.wrappedValue {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(language.text("Done", "完成")) { enteringCode.wrappedValue = false }
                        .accessibilityIdentifier("lio.invite.keyboard-done")
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles").font(.caption.weight(.bold)).foregroundStyle(LioTheme.vermilion)
                    .accessibilityHidden(true)
                RunReadableText(text: language.text("Invite only", "仅限受邀测试者"), style: .subheadlineSemibold,
                                color: LioSignInPalette.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(LioSignInPalette.field, in: Capsule())
            .overlay { Capsule().stroke(LioSignInPalette.line, lineWidth: LioTheme.outlineWidth).accessibilityHidden(true) }
            Text(language.text("Enter your invitation code", "输入邀请码"))
                .font(.system(.title, design: .default, weight: .bold))
                .foregroundStyle(LioSignInPalette.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            RunReadableText(text: language.text("Use the code the Go2China team sent you to start chatting with Lio.",
                                                "输入 Go2China 团队发给你的邀请码，开始和 Lio 聊你的旅行。"),
                            color: LioSignInPalette.inkSecondary)
        }
    }

    private var field: some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            Image(systemName: "key.fill").foregroundStyle(LioSignInPalette.inkSecondary).accessibilityHidden(true)
            SecureField(language.text("Invitation code", "邀请码"), text: $code,
                        prompt: Text(language.text("Invitation code", "邀请码")).foregroundColor(LioSignInPalette.inkSecondary))
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.asciiCapable)
                .foregroundColor(LioSignInPalette.ink)
                .focused(enteringCode)
                .submitLabel(.continue)
                .onSubmit { if canContinue { onContinue() } }
                .frame(minHeight: fieldHeight)
                .accessibilityIdentifier("demo.invite.code")
                .background(LioInvitationInputTraits().accessibilityHidden(true))
        }
        .padding(.horizontal, LioTheme.Spacing.md)
        .background(LioSignInPalette.field,
                    in: RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous)
                .stroke(enteringCode.wrappedValue ? LioTheme.vermilion : LioSignInPalette.line,
                        lineWidth: enteringCode.wrappedValue ? focusWidth : LioTheme.outlineWidth)
                .accessibilityHidden(true)
        }
        .animation(LioTheme.Motion.change, value: enteringCode.wrappedValue)
    }

    private var canContinue: Bool { !code.isEmpty && !isBusy }

    private var primary: some View {
        Button(action: onContinue) {
            HStack(spacing: LioTheme.Spacing.xs) {
                if isBusy { ProgressView().tint(LioTheme.onVermilion).accessibilityHidden(true) }
                Text(language.text("Continue", "继续"))
                    .font(.body.weight(.semibold))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(canContinue || isBusy ? LioTheme.onVermilion : LioSignInPalette.inkSecondary)
            .padding(.vertical, LioTheme.Spacing.xs)
            .frame(maxWidth: .infinity, minHeight: buttonHeight)
            .background(canContinue || isBusy ? LioTheme.vermilion : LioSignInPalette.line, in: Capsule())
            .contentShape(Capsule())
        }
        .buttonStyle(LioSignInPressStyle())
        .disabled(!canContinue)
        .accessibilityIdentifier("demo.invite.continue")
    }

    private var restore: some View {
        Button(action: onRestore) {
            Text(language.text("Continue with your account", "继续使用账号"))
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(isBusy ? LioSignInPalette.inkSecondary : LioSignInPalette.ink)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(LioSignInPressStyle())
        .disabled(isBusy)
        .accessibilityIdentifier("demo.invite.restore")
    }

    private var settingsRow: some View {
        settings
            .padding(.horizontal, LioTheme.Spacing.md)
            .background(LioSignInPalette.field.opacity(0.85),
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous)
                    .stroke(LioSignInPalette.line, lineWidth: LioTheme.outlineWidth).accessibilityHidden(true)
            }
    }
}
#endif
