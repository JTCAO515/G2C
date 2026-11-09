#if os(iOS)
import SwiftUI
import CJRunClient
import UIKit

struct AssistantOptionLabel: View {
    let title: String
    let symbol: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: symbol).accessibilityHidden(true)
            RunReadableText(text: title)
        }
    }
}

struct AssistantOptionButtonStyle: ButtonStyle {
    var emphasized = false
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 4)
            .foregroundStyle(.primary)
            .background(emphasized ? Color.accentColor.opacity(0.14) : Color(uiColor: .systemBackground),
                        in: RoundedRectangle(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(emphasized ? Color.accentColor : Color(uiColor: .separator), lineWidth: 1)
                    .allowsHitTesting(false)
            }
            .contentShape(RoundedRectangle(cornerRadius: 12))
            .opacity(isEnabled && !configuration.isPressed ? 1 : 0.7)
    }
}

extension View {
    func assistantCard() -> some View {
        frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 18))
    }
}
#endif
