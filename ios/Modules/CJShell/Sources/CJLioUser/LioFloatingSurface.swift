#if os(iOS)
import SwiftUI

/// Glass belongs to the controls floating over the conversation, not to its contents.
extension View {
    func lioFloatingSurface<S: Shape>(_ shape: S, interactive: Bool = false) -> some View {
        modifier(LioFloatingSurface(shape: shape, interactive: interactive))
    }

    @ViewBuilder
    func lioFloatingGroup() -> some View {
        if #available(iOS 26, *) {
            GlassEffectContainer(spacing: 16) { self }
        } else {
            self
        }
    }
}

private struct LioFloatingSurface<S: Shape>: ViewModifier {
    let shape: S
    let interactive: Bool
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    @ViewBuilder
    func body(content: Content) -> some View {
        if reduceTransparency {
            content.lioCard(shape)
        } else if #available(iOS 26, *) {
            content.glassEffect(.regular.interactive(interactive), in: shape)
        } else {
            content.background(.ultraThinMaterial, in: shape)
                .overlay { shape.stroke(LioTheme.hairline, lineWidth: 1).allowsHitTesting(false).accessibilityHidden(true) }
        }
    }
}
#endif
