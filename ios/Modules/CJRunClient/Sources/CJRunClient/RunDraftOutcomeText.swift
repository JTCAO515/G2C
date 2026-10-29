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
            compatibleWith: UITraitCollection(preferredContentSizeCategory: runTextCategory(size)))
    }
    public func sizeThatFits(_ proposal: ProposedViewSize, uiView: UILabel, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
    public static func dismantleUIView(_ uiView: UILabel, coordinator: ()) { uiView.text = nil }
}

public struct RunSelectableText: UIViewRepresentable {
    let text: String
    public init(text: String) { self.text = text }
    @Environment(\.dynamicTypeSize) private var size
    public func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false; view.isSelectable = true; view.isScrollEnabled = false
        view.dataDetectorTypes = []; view.backgroundColor = .clear; view.textColor = .label
        view.textContainerInset = .zero; view.textContainer.lineFragmentPadding = 0
        view.adjustsFontForContentSizeCategory = true
        view.setContentCompressionResistancePriority(.required, for: .vertical)
        return view
    }
    public func updateUIView(_ view: UITextView, context: Context) {
        if view.text?.utf8.elementsEqual(text.utf8) != true { view.text = text }
        view.font = UIFont.preferredFont(forTextStyle: .body,
            compatibleWith: UITraitCollection(preferredContentSizeCategory: runTextCategory(size)))
    }
    public func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
    public static func dismantleUIView(_ uiView: UITextView, coordinator: ()) { uiView.text = nil }
}

private func runTextCategory(_ size: DynamicTypeSize) -> UIContentSizeCategory {
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
public struct RunReadableText: View {
    let text: String
    let style: RunReadableTextStyle
    public init(text: String, style: RunReadableTextStyle = .body) { self.text = text; self.style = style }
    public var body: some View { Text(text).font(style == .body ? .body : .caption).fixedSize(horizontal: false, vertical: true) }
}
public struct RunSelectableText: View {
    let text: String
    public init(text: String) { self.text = text }
    public var body: some View { Text(text).textSelection(.enabled).fixedSize(horizontal: false, vertical: true) }
}
#endif
