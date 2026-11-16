import Foundation

/// Presentation validation only. The service still decides access and expiry.
enum LioInvitationInput {
    static func accepts(_ value: String) -> Bool {
        value.range(of: #"\A(?:(?:G2C|CJ_Tester)@(?:0[1-9]|[1-9][0-9])|D1-[a-z0-9]{12}\.[A-Za-z0-9_-]{22})\z"#,
                    options: .regularExpression) != nil
    }

    static func formatMessage(_ language: LioLanguage) -> String {
        language.text(
            "Use G2C@ or CJ_Tester@ followed by two digits (01–99). Match the capitals and use no spaces.",
            "请使用 G2C@两位数字 或 CJ_Tester@两位数字（01–99），保持大小写，不加空格。")
    }
}

#if os(iOS)
import SwiftUI
import UIKit

/// SwiftUI exposes capitalization/correction, but not smart punctuation traits.
/// Keep the native SecureField and configure only its UIKit input traits.
struct LioInvitationInputTraits: UIViewRepresentable {
    func makeUIView(context: Context) -> Anchor {
        let view = Anchor()
        view.isUserInteractionEnabled = false
        view.isAccessibilityElement = false
        return view
    }
    func updateUIView(_ view: Anchor, context: Context) { view.apply() }

    @MainActor final class Anchor: UIView {
        override func didMoveToWindow() { super.didMoveToWindow(); apply() }
        override func layoutSubviews() { super.layoutSubviews(); apply() }

        func apply() {
            guard window != nil else { return }
            var ancestor = superview
            while let current = ancestor {
                if let field = invitationField(in: current) {
                    field.autocapitalizationType = .none
                    field.autocorrectionType = .no
                    field.smartQuotesType = .no
                    field.smartDashesType = .no
                    field.smartInsertDeleteType = .no
                    return
                }
                ancestor = current.superview
            }
        }

        private func invitationField(in view: UIView) -> UITextField? {
            if let field = view as? UITextField, field.isSecureTextEntry,
               field.accessibilityIdentifier == "demo.invite.code" { return field }
            for child in view.subviews {
                if let field = invitationField(in: child) { return field }
            }
            return nil
        }
    }
}
#endif
