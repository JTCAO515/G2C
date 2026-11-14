import SwiftUI

/// Lio user design tokens (docs/ui.md, D5: warm paper with vermilion).
/// Views reference only these semantic names; colour values live in `LioAssets.xcassets`
/// and are mirrored in `swatches` so a unit test can keep both in step and check contrast.
public enum LioTheme {
    struct Swatch: Sendable {
        let name: String
        let asset: String
        let light: UInt32
        let dark: UInt32
    }

    static let swatches: [Swatch] = [
        Swatch(name: "paper", asset: "LioPaper", light: 0xFAF6EF, dark: 0x16130F),
        Swatch(name: "surface", asset: "LioSurface", light: 0xFFFFFF, dark: 0x211D18),
        Swatch(name: "surfaceSunken", asset: "LioSurfaceSunken", light: 0xF1EADF, dark: 0x2B2620),
        Swatch(name: "ink", asset: "LioInk", light: 0x1F1A15, dark: 0xF3EDE4),
        Swatch(name: "inkSecondary", asset: "LioInkSecondary", light: 0x6B6157, dark: 0xA89E92),
        Swatch(name: "hairline", asset: "LioHairline", light: 0xE4DACB, dark: 0x3A332B),
        Swatch(name: "vermilion", asset: "LioVermilion", light: 0xC0352B, dark: 0xE86655),
        Swatch(name: "onVermilion", asset: "LioOnVermilion", light: 0xFFFFFF, dark: 0x16130F),
        Swatch(name: "jade", asset: "LioJade", light: 0x1D7556, dark: 0x4FB893),
        Swatch(name: "gold", asset: "LioGold", light: 0x866116, dark: 0xD4AE5C)
    ]

    /// Page background for chat, trips and memory.
    public static let paper = Color("LioPaper", bundle: .module)
    /// Cards and the message field.
    public static let surface = Color("LioSurface", bundle: .module)
    /// The traveller's messages and secondary fills.
    public static let surfaceSunken = Color("LioSurfaceSunken", bundle: .module)
    /// Body text.
    public static let ink = Color("LioInk", bundle: .module)
    /// Secondary text and times.
    public static let inkSecondary = Color("LioInkSecondary", bundle: .module)
    /// Decorative separators and card outlines only; never used for text.
    public static let hairline = Color("LioHairline", bundle: .module)
    /// The single primary action colour: send, primary buttons, links.
    public static let vermilion = Color("LioVermilion", bundle: .module)
    /// Text and symbols placed on a vermilion fill.
    public static let onVermilion = Color("LioOnVermilion", bundle: .module)
    /// Saved and remembered states.
    public static let jade = Color("LioJade", bundle: .module)
    /// Memory icons and emphasis.
    public static let gold = Color("LioGold", bundle: .module)
    /// Messages that couldn't be sent.
    public static let danger = Color.red

    /// Headline-level display text. New York for Latin text; Chinese falls back to the system font.
    /// Follows Dynamic Type through the text style.
    public static func display(_ style: Font.TextStyle) -> Font {
        .system(style, design: .serif)
    }

    public enum Spacing {
        public static let xxs: CGFloat = 4
        public static let xs: CGFloat = 8
        public static let sm: CGFloat = 12
        public static let md: CGFloat = 16
        public static let lg: CGFloat = 24
        public static let xl: CGFloat = 32
    }

    /// Corner radii. Pills and the message field use `Capsule()`.
    public enum Radius {
        /// Small cards and chips.
        public static let small: CGFloat = 12
        /// Cards and message bubbles.
        public static let card: CGFloat = 20
        /// The corner of a message bubble nearest its sender.
        public static let tail: CGFloat = 6
    }

    /// `hairline` outline width for cards and the message field.
    public static let outlineWidth: CGFloat = 1

    public enum Motion {
        /// Something appearing.
        public static let appear = Animation.spring(duration: 0.3)
        /// A change of state.
        public static let change = Animation.easeOut(duration: 0.2)
        /// Small feedback such as a pressed control.
        public static let micro = Animation.easeOut(duration: 0.12)
        /// A message or card entering the conversation.
        public static let enter = Animation.spring(response: 0.35, dampingFraction: 0.85)
        /// A moment worth noticing, such as a saved trip.
        public static let emphasis = Animation.spring(response: 0.45, dampingFraction: 0.75)
        /// Seconds for one full breath (in and out) of a waiting avatar.
        public static let breathingCycle: Double = 1.6
        /// Half a breath, repeated with autoreverse for a `breathingCycle` loop.
        public static let breathing = Animation.easeInOut(duration: breathingCycle / 2).repeatForever(autoreverses: true)
        /// The first frame's avatar, played once per launch.
        public static let launch = Animation.spring(duration: 0.4, bounce: 0.2)
        /// Seconds the old conversation takes to fade out when a new chat starts.
        public static let chatFadeOut: Double = 0.15

        /// No animation when Reduce Motion is on.
        public static func animation(_ animation: Animation, reduceMotion: Bool) -> Animation? {
            reduceMotion ? nil : animation
        }
    }
}

extension View {
    /// A `surface` card with a `hairline` outline and no shadow. The outline doesn't change layout.
    func lioCard<S: Shape>(_ shape: S) -> some View {
        background(LioTheme.surface, in: shape)
            .overlay {
                shape.stroke(LioTheme.hairline, lineWidth: LioTheme.outlineWidth)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
    }

    /// Lists and forms on the `paper` page colour; pair with `lioRow()` on their rows.
    public func lioPage() -> some View {
        scrollContentBackground(.hidden).background(LioTheme.paper)
    }

    /// A list or form row on `surface`.
    public func lioRow() -> some View {
        listRowBackground(LioTheme.surface)
    }
}
