// Reuses the accepted RunDraftOutcomeText measurement pattern within this module.
import SwiftUI

#if os(iOS)
import UIKit

/// Multiline UIKit measurement avoids the reproducible SwiftUI Text clipping
/// at the largest accessibility size. The font follows the SwiftUI environment;
/// there is no size cap, alternate accessibility text or filtered audit result.
struct FeedbackReadableText: UIViewRepresentable {
    let text: String
    let footnote: Bool
    init(text: String, footnote: Bool = false) { self.text = text; self.footnote = footnote }
    @Environment(\.dynamicTypeSize) private var size
    func makeUIView(context: Context) -> UILabel {
        let label = UILabel()
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        label.textColor = .label
        label.adjustsFontForContentSizeCategory = true
        label.setContentCompressionResistancePriority(.required, for: .vertical)
        return label
    }
    func updateUIView(_ label: UILabel, context: Context) {
        label.text = text
        let textStyle: UIFont.TextStyle = footnote ? .footnote : .body
        label.font = UIFont.preferredFont(forTextStyle:textStyle,
            compatibleWith: UITraitCollection(preferredContentSizeCategory: feedbackTextCategory(size)))
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UILabel, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
    static func dismantleUIView(_ uiView: UILabel, coordinator: ()) { uiView.text = nil }
}


private func feedbackTextCategory(_ size: DynamicTypeSize) -> UIContentSizeCategory {
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
#else
struct FeedbackReadableText: View {
    let text: String
    var footnote = false
    var body: some View { Text(text).font(footnote ? .footnote : .body).fixedSize(horizontal: false, vertical: true) }
}
#endif
