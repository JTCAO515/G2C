#if os(iOS)
import SwiftUI
import CJRunClient
import UIKit

struct ShellActionLabel: View {
    let title: String
    let symbol: String
    var detail: String? = nil
    var accessory: String? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: symbol)
                .frame(minWidth: 22)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                RunReadableText(text: title)
                if let detail { RunReadableText(text: detail, style: .caption) }
            }
            if let accessory {
                Spacer(minLength: 0)
                Image(systemName: accessory)
                    .font(.caption.weight(.semibold))
                    .accessibilityHidden(true)
            }
        }
    }
}

struct ShellActionButtonStyle: ButtonStyle {
    var emphasized = false
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let prominent = emphasized && isEnabled
        let shape = RoundedRectangle(cornerRadius: 12)
        configuration.label
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 4)
            .foregroundStyle(isEnabled ? Color.primary : Color.secondary)
            .background(prominent ? Color.primary.opacity(0.12)
                        : Color(uiColor: isEnabled ? .systemBackground : .tertiarySystemFill), in: shape)
            .overlay {
                shape.strokeBorder(Color.primary.opacity(prominent ? 0.9 : 0.25), lineWidth: prominent ? 2 : 1)
                    .allowsHitTesting(false)
            }
            .contentShape(shape)
            .opacity(configuration.isPressed ? 0.75 : 1)
    }
}

struct ShellCardHeading: View {
    let title: String
    let symbol: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: symbol).font(.headline).accessibilityHidden(true)
            RunReadableText(text: title, style: .headline).accessibilityAddTraits(.isHeader)
        }
    }
}

extension View {
    func shellCard(fill: Color = Color(uiColor: .secondarySystemBackground)) -> some View {
        frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background(fill, in: RoundedRectangle(cornerRadius: 18))
    }
}
#endif
