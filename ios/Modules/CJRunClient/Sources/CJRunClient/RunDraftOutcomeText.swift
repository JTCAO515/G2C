import SwiftUI

public enum RunReadableTextStyle: Sendable { case body, caption }

#if os(iOS)
import UIKit

/// Multiline UIKit measurement avoids the reproducible SwiftUI Text clipping
/// at the largest accessibility size. The font follows the SwiftUI environment;
/// there is no size cap, alternate accessibility text or filtered audit result.
public struct RunReadableText: UIViewRepresentable {
    let text: String
    let style: RunReadableTextStyle
    public init(text: String, style: RunReadableTextStyle = .body) { self.text = text; self.style = style }
    @Environment(\.dynamicTypeSize) private var size
    public func makeUIView(context: Context) -> UILabel {
        let label = UILabel()
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        label.textColor = .label
        label.adjustsFontForContentSizeCategory = true
        label.setContentCompressionResistancePriority(.required, for: .vertical)
        return label
    }
    public func updateUIView(_ label: UILabel, context: Context) {
        label.text = text
        label.font = UIFont.preferredFont(forTextStyle: style == .body ? .body : .caption1,
            compatibleWith: UITraitCollection(preferredContentSizeCategory: category))
    }
    public func sizeThatFits(_ proposal: ProposedViewSize, uiView: UILabel, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
    private var category: UIContentSizeCategory {
        switch size {
        case .xSmall: .extraSmall
        case .small: .small
        case .medium: .medium
        case .large: .large
        case .xLarge: .extraLarge
        case .xxLarge: .extraExtraLarge
        case .xxxLarge: .extraExtraExtraLarge
        case .accessibility1: .accessibilityMedium
        case .accessibility2: .accessibilityLarge
        case .accessibility3: .accessibilityExtraLarge
        case .accessibility4: .accessibilityExtraExtraLarge
        case .accessibility5: .accessibilityExtraExtraExtraLarge
        @unknown default: .large
        }
    }
}
#else
public struct RunReadableText: View {
    let text: String
    let style: RunReadableTextStyle
    public init(text: String, style: RunReadableTextStyle = .body) { self.text = text; self.style = style }
    public var body: some View { Text(text).font(style == .body ? .body : .caption).fixedSize(horizontal: false, vertical: true) }
}
#endif
