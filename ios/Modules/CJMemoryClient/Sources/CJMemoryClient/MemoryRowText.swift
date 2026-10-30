import SwiftUI

// Local rendering adapter: CJMemoryClient has no dependency on CJRunClient.
// Keep module boundaries; use native multiline measurement for audited rows.
enum MemoryRowTextStyle { case body, caption }
#if os(iOS)
import UIKit

struct MemoryRowText: UIViewRepresentable {
    let text: String
    let style: MemoryRowTextStyle
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
        label.font = UIFont.preferredFont(forTextStyle: style == .body ? .body : .caption1,
                                          compatibleWith: label.traitCollection)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UILabel, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
    static func dismantleUIView(_ uiView: UILabel, coordinator: ()) { uiView.text = nil }
}
#else
struct MemoryRowText: View {
    let text: String
    let style: MemoryRowTextStyle
    var body: some View {
        Text(text).font(style == .body ? .body : .caption)
            .foregroundStyle(Color.primary).fixedSize(horizontal: false, vertical: true)
    }
}
#endif
