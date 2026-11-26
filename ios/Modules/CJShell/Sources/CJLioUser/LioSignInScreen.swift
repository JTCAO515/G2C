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

/// Two looks for JT to choose from (design draft). `aurora` is the default; Debug can show `paper`.
enum LioSignInStyle: Sendable {
    case aurora, paper

    static var current: LioSignInStyle {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--lio-signin-paper") { return .paper }
        #endif
        return .aurora
    }
}

/// Debug-only launch arguments that open a given state for screenshots.
enum LioSignInDebug {
    static var opensInvite: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--lio-signin-open-invite")
        #else
        return false
        #endif
    }

    static var comingSoon: LioSignInChannel? {
        #if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        if let index = arguments.firstIndex(of: "--lio-signin-soon"), arguments.indices.contains(index + 1) {
            return LioSignInChannel(rawValue: arguments[index + 1])
        }
        #endif
        return nil
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

#if os(iOS)
import SwiftUI
import UIKit

// MARK: - Palette

/// Colours of the sign-in screen only. Apple's and Google's button colours come from their brand guidelines and
/// must not follow the Lio theme.
enum LioSignInPalette {
    static func dynamic(light: UInt32, dark: UInt32) -> Color {
        Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? uiColor(dark) : uiColor(light) })
    }

    static func uiColor(_ hex: UInt32) -> UIColor {
        UIColor(red: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }

    static func base(_ style: LioSignInStyle) -> Color {
        style == .paper ? LioTheme.paper : dynamic(light: 0xF7F6F4, dark: 0x09090B)
    }
    static func ink(_ style: LioSignInStyle) -> Color {
        style == .paper ? LioTheme.ink : dynamic(light: 0x0E0E11, dark: 0xF4F4F6)
    }
    static func inkSecondary(_ style: LioSignInStyle) -> Color {
        style == .paper ? LioTheme.inkSecondary : dynamic(light: 0x55555F, dark: 0xA3A3AD)
    }
    static func line(_ style: LioSignInStyle) -> Color {
        style == .paper ? LioTheme.hairline : dynamic(light: 0xDEDCD8, dark: 0x2A2A30)
    }
    /// The email button and the code field.
    static func field(_ style: LioSignInStyle) -> Color {
        style == .paper ? LioTheme.surface : dynamic(light: 0xFFFFFF, dark: 0x17171B)
    }

    static let ember = dynamic(light: 0xFF5B3A, dark: 0xFF5B3A)
    static let amber = dynamic(light: 0xFFB34D, dark: 0xF2A23A)
    static let iris = dynamic(light: 0x8A6CFF, dark: 0x6E52FF)

    // Apple: black on light backgrounds, white on dark (Sign in with Apple, Human Interface Guidelines).
    static let appleFill = dynamic(light: 0x000000, dark: 0xFFFFFF)
    static let appleText = dynamic(light: 0xFFFFFF, dark: 0x000000)
    // Google: the light and dark themes of the Sign in with Google branding guidelines.
    static let googleFill = dynamic(light: 0xFFFFFF, dark: 0x131314)
    static let googleStroke = dynamic(light: 0x747775, dark: 0x8E918F)
    static let googleText = dynamic(light: 0x1F1F1F, dark: 0xE3E3E3)
}

// MARK: - Backdrop

/// Soft drifting glows behind the content, with a faint dot grid in the aurora look. Decorative only; still when
/// Reduce Motion is on.
struct LioSignInBackdrop: View {
    let style: LioSignInStyle
    var quiet = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme
    @State private var drift = false
    private let glowBlur: CGFloat = 70
    private let dotStep: CGFloat = 22
    private let dotSize: CGFloat = 1.3

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            let height = proxy.size.height
            ZStack {
                LioSignInPalette.base(style)
                if style == .aurora {
                    glow(LioSignInPalette.ember, size: width * 0.95)
                        .offset(x: drift ? -width * 0.30 : -width * 0.12, y: -height * (drift ? 0.30 : 0.36))
                    glow(LioSignInPalette.amber, size: width * 0.70)
                        .offset(x: drift ? width * 0.32 : width * 0.18, y: -height * (drift ? 0.38 : 0.30))
                    glow(LioSignInPalette.iris, size: width * 0.80)
                        .offset(x: drift ? width * 0.05 : width * 0.25, y: -height * (drift ? 0.16 : 0.22))
                    dots
                } else {
                    glow(LioTheme.vermilion, size: width * 1.1)
                        .offset(x: -width * 0.15, y: -height * 0.36)
                    glow(LioTheme.gold, size: width * 0.8)
                        .offset(x: width * 0.30, y: -height * 0.30)
                }
            }
            .frame(width: width, height: height)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .allowsHitTesting(false)
        .onAppear {
            guard !reduceMotion, style == .aurora else { return }
            withAnimation(.easeInOut(duration: 9).repeatForever(autoreverses: true)) { drift = true }
        }
    }

    private var glowOpacity: Double {
        let dark = colorScheme == .dark
        let base: Double = style == .paper ? (dark ? 0.16 : 0.10) : (dark ? 0.42 : 0.30)
        return quiet ? base * 0.55 : base
    }

    private func glow(_ color: Color, size: CGFloat) -> some View {
        Circle().fill(color).frame(width: size, height: size).blur(radius: glowBlur).opacity(glowOpacity)
    }

    private var dots: some View {
        Canvas { context, size in
            var path = Path()
            var y: CGFloat = dotStep / 2
            while y < size.height {
                var x: CGFloat = dotStep / 2
                while x < size.width {
                    path.addEllipse(in: CGRect(x: x, y: y, width: dotSize, height: dotSize))
                    x += dotStep
                }
                y += dotStep
            }
            context.fill(path, with: .color(LioSignInPalette.ink(style).opacity(colorScheme == .dark ? 0.16 : 0.10)))
        }
        .mask(LinearGradient(colors: [.white, .white.opacity(0)], startPoint: .top, endPoint: UnitPoint(x: 0.5, y: 0.55)))
    }
}

// MARK: - Emblem

/// Lio's portrait in a slowly turning gradient ring.
struct LioSignInEmblem: View {
    let style: LioSignInStyle
    @ScaledMetric(relativeTo: .largeTitle) private var size: CGFloat = 76
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var turn = false
    private let ringWidth: CGFloat = 2.5
    private let haloBlur: CGFloat = 18

    var body: some View {
        let portrait = min(size, 120)
        ZStack {
            Circle().fill(ringColors.first ?? LioTheme.vermilion).opacity(0.35)
                .frame(width: portrait, height: portrait).blur(radius: haloBlur)
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
            withAnimation(.linear(duration: 14).repeatForever(autoreverses: false)) { turn = true }
        }
    }

    private var ringColors: [Color] {
        style == .aurora
            ? [LioSignInPalette.ember, LioSignInPalette.amber, LioSignInPalette.iris, LioSignInPalette.ember]
            : [LioTheme.vermilion, LioTheme.gold, LioTheme.vermilion]
    }
}

// MARK: - Buttons

struct LioSignInPressStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(isEnabled ? (configuration.isPressed ? 0.82 : 1) : 0.55)
            .scaleEffect(configuration.isPressed && isEnabled ? 0.985 : 1)
            .animation(LioTheme.Motion.micro, value: configuration.isPressed)
    }
}

/// One channel button. Apple and Google use their own colours, logo and wording; email follows the screen's look.
struct LioSignInChannelButton: View {
    let channel: LioSignInChannel
    let language: LioLanguage
    let style: LioSignInStyle
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
        case .email: LioSignInPalette.field(style)
        }
    }
    private var stroke: Color {
        switch channel {
        case .apple: .clear
        case .google: LioSignInPalette.googleStroke
        case .email: LioSignInPalette.line(style)
        }
    }
    private var text: Color {
        switch channel {
        case .apple: LioSignInPalette.appleText
        case .google: LioSignInPalette.googleText
        case .email: LioSignInPalette.ink(style)
        }
    }
}

/// A status line in a soft card, for the format hint and the sign-in notice.
struct LioSignInMessage: View {
    let text: String
    let style: LioSignInStyle
    let symbol: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.xs) {
            Image(systemName: symbol).foregroundStyle(LioTheme.vermilion).accessibilityHidden(true)
            Text(text).font(.subheadline).foregroundStyle(LioSignInPalette.ink(style))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(LioTheme.Spacing.sm)
        .background(LioSignInPalette.field(style).opacity(0.85),
                    in: RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous)
                .stroke(LioSignInPalette.line(style), lineWidth: LioTheme.outlineWidth).accessibilityHidden(true)
        }
        .accessibilityElement(children: .combine)
    }
}

private extension LioSignInStyle {
    func headline() -> Font {
        self == .paper ? LioTheme.display(.largeTitle).weight(.semibold) : .system(.largeTitle, design: .default, weight: .bold)
    }
    func title() -> Font {
        self == .paper ? LioTheme.display(.title).weight(.semibold) : .system(.title, design: .default, weight: .bold)
    }
}

// MARK: - Welcome

/// The first screen: who Lio is, the three channels (placeholders), and the small internal-test entry.
struct LioSignInWelcome<Settings: View>: View {
    let language: LioLanguage
    let style: LioSignInStyle
    let notice: String?
    let settings: Settings
    let onInvite: () -> Void
    @State private var comingSoon: LioSignInChannel? = LioSignInDebug.comingSoon
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
                                .background(LioSignInPalette.field(style).opacity(0.7), in: Capsule())
                                .overlay { Capsule().stroke(LioSignInPalette.line(style), lineWidth: LioTheme.outlineWidth).accessibilityHidden(true) }
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
        .background(LioSignInBackdrop(style: style))
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
            LioSignInEmblem(style: style)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: LioTheme.Spacing.xs) { wordmark; betaTag }
                VStack(spacing: LioTheme.Spacing.xxs) { wordmark; betaTag }
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Go2China Beta")
            Text(language.text("Your local helper in China", "你在中国的本地助手"))
                .font(style.headline())
                .foregroundStyle(LioSignInPalette.ink(style))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("lio.signin.heading")
            Text(language.text("Plans, transport, translation and everyday errands — just ask Lio.",
                               "行程、交通、翻译和日常小事，随时问 Lio。"))
                .font(.body)
                .foregroundStyle(LioSignInPalette.inkSecondary(style))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var wordmark: some View {
        Text("Go2China").font(.subheadline.weight(.semibold)).tracking(0.6)
            .foregroundStyle(LioSignInPalette.ink(style))
    }

    private var betaTag: some View {
        Text("BETA").font(.caption2.weight(.bold)).tracking(0.8)
            .foregroundStyle(LioSignInPalette.inkSecondary(style))
            .padding(.horizontal, 6).padding(.vertical, 2)
            .overlay { Capsule().stroke(LioSignInPalette.line(style), lineWidth: LioTheme.outlineWidth) }
    }

    private var actions: some View {
        VStack(spacing: LioTheme.Spacing.sm) {
            if let notice {
                LioSignInMessage(text: notice, style: style, symbol: "info.circle")
                    .accessibilityIdentifier("lio.signin.status")
                    .padding(.bottom, LioTheme.Spacing.xxs)
            }
            ForEach(LioSignInChannel.allCases) { channel in
                LioSignInChannelButton(channel: channel, language: language, style: style) { comingSoon = channel }
            }
            HStack(spacing: LioTheme.Spacing.sm) {
                rule
                Text(language.text("or", "或")).font(.footnote).foregroundStyle(LioSignInPalette.inkSecondary(style))
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
                .foregroundStyle(style == .paper ? LioTheme.vermilion : LioSignInPalette.ink(style))
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(LioSignInPressStyle())
            .accessibilityIdentifier("lio.signin.invite")
            // At accessibility sizes the language row moves to the end, full width, so it never runs off screen.
            if typeSize.isAccessibilitySize {
                settings
                    .padding(.horizontal, LioTheme.Spacing.md)
                    .background(LioSignInPalette.field(style).opacity(0.85),
                                in: RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous))
                    .padding(.top, LioTheme.Spacing.md)
            }
        }
    }

    private var rule: some View {
        Rectangle().fill(LioSignInPalette.line(style)).frame(height: LioTheme.outlineWidth)
    }
}

// MARK: - Internal test page

/// The redesigned invitation page. It only lays out the existing controls: the code, its checks, the consent
/// step and the sign-in stay with `LioInvitationView`.
struct LioInternalTestPage<Settings: View>: View {
    let language: LioLanguage
    let style: LioSignInStyle
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
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                header
                VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                    field
                    if invalidFormat {
                        LioSignInMessage(text: LioInvitationInput.formatMessage(language), style: style,
                                         symbol: "exclamationmark.circle")
                            .accessibilityIdentifier("demo.invite.format")
                    }
                    if let notice {
                        LioSignInMessage(text: notice, style: style, symbol: "info.circle")
                            .accessibilityIdentifier("demo.invite.status")
                    }
                }
                VStack(spacing: LioTheme.Spacing.xs) {
                    primary
                    restore
                }
                settingsRow
            }
            .frame(maxWidth: 480, alignment: .leading)
            .padding(.horizontal, LioTheme.Spacing.lg)
            .padding(.top, LioTheme.Spacing.md)
            .padding(.bottom, LioTheme.Spacing.xl)
            .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .scrollBounceBehavior(.basedOnSize)
        .background(LioSignInBackdrop(style: style, quiet: true))
        .navigationTitle(language.text("Internal testing", "内部测试"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.hidden, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .principal) {
                Text(language.text("Internal testing", "内部测试"))
                    .font(.headline)
                    .foregroundStyle(LioSignInPalette.ink(style))
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
                Image(systemName: "sparkles").accessibilityHidden(true)
                Text(language.text("INVITE ONLY", "仅限受邀测试者")).tracking(language == .english ? 0.8 : 0)
            }
            .font(.caption.weight(.bold))
            .foregroundStyle(LioTheme.vermilion)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(LioTheme.vermilion.opacity(0.12), in: Capsule())
            .accessibilityElement(children: .combine)
            Text(language.text("Enter your invitation code", "输入邀请码"))
                .font(style.title())
                .foregroundStyle(LioSignInPalette.ink(style))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(language.text("Use the code the Go2China team sent you to start chatting with Lio.",
                               "输入 Go2China 团队发给你的邀请码，开始和 Lio 聊你的旅行。"))
                .font(.body)
                .foregroundStyle(LioSignInPalette.inkSecondary(style))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var field: some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            Image(systemName: "key.fill").foregroundStyle(LioSignInPalette.inkSecondary(style)).accessibilityHidden(true)
            SecureField(language.text("Invitation code", "邀请码"), text: $code,
                        prompt: Text(language.text("Invitation code", "邀请码")).font(.body).foregroundColor(LioSignInPalette.inkSecondary(style)))
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.asciiCapable)
                .font(.body.monospaced())
                .foregroundColor(LioSignInPalette.ink(style))
                .focused(enteringCode)
                .submitLabel(.continue)
                .onSubmit { if canContinue { onContinue() } }
                .accessibilityIdentifier("demo.invite.code")
                .background(LioInvitationInputTraits().accessibilityHidden(true))
        }
        .padding(.horizontal, LioTheme.Spacing.md)
        .frame(minHeight: fieldHeight)
        .background(LioSignInPalette.field(style),
                    in: RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous)
                .stroke(enteringCode.wrappedValue ? LioTheme.vermilion : LioSignInPalette.line(style),
                        lineWidth: enteringCode.wrappedValue ? focusWidth : LioTheme.outlineWidth)
                .accessibilityHidden(true)
        }
        .animation(LioTheme.Motion.change, value: enteringCode.wrappedValue)
        .contentShape(Rectangle())
        .onTapGesture { enteringCode.wrappedValue = true }
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
            .foregroundStyle(canContinue || isBusy ? LioTheme.onVermilion : LioSignInPalette.inkSecondary(style))
            .padding(.vertical, LioTheme.Spacing.xs)
            .frame(maxWidth: .infinity, minHeight: buttonHeight)
            .background(canContinue || isBusy ? LioTheme.vermilion : LioSignInPalette.line(style), in: Capsule())
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
                .foregroundStyle(isBusy ? LioSignInPalette.inkSecondary(style) : LioSignInPalette.ink(style))
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
            .background(LioSignInPalette.field(style).opacity(0.85),
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: LioTheme.Radius.small, style: .continuous)
                    .stroke(LioSignInPalette.line(style), lineWidth: LioTheme.outlineWidth).accessibilityHidden(true)
            }
    }
}
#endif
