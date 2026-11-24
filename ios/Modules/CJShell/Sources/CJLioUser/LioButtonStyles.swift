#if os(iOS)
import SwiftUI

/// Build 54 UI proposal (#1429, JT confirmed): one primary style (vermilion fill) and one secondary
/// style (surface with a hairline) for actions on tool pages, replacing system grey buttons.
struct LioPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(isEnabled ? LioTheme.onVermilion : LioTheme.inkSecondary)
            .frame(maxWidth: .infinity, minHeight: 52)
            .padding(.horizontal, LioTheme.Spacing.md)
            .background(isEnabled ? LioTheme.vermilion : LioTheme.surfaceSunken,
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

struct LioSecondaryButtonStyle: ButtonStyle {
    var fullWidth = true
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(isEnabled ? LioTheme.ink : LioTheme.inkSecondary)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: 48)
            .padding(.horizontal, LioTheme.Spacing.md)
            .background(configuration.isPressed ? LioTheme.surfaceSunken : LioTheme.surface,
                        in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .overlay {
                RoundedRectangle(cornerRadius: LioTheme.Radius.card)
                    .stroke(LioTheme.hairline, lineWidth: LioTheme.outlineWidth)
                    .allowsHitTesting(false)
            }
            .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

/// A numbered step card used by guides (taxi first-run guide, metro steps).
struct LioStepCard: View {
    let step: Int
    let symbol: String
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: LioTheme.Spacing.sm) {
            Text("\(step)")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(LioTheme.onVermilion)
                .frame(width: 26, height: 26)
                .background(LioTheme.vermilion, in: Circle())
                .accessibilityHidden(true)
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(LioTheme.vermilion)
                .frame(width: 28)
                .accessibilityHidden(true)
            Text(text)
                .foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .accessibilityElement(children: .combine)
    }
}
#endif
