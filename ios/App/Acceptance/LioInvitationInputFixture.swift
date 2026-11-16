import SwiftUI
import UIKit

/// Acceptance-only observation of UIKit traits; never reads input text.
@MainActor struct LioInvitationInputFixture<Content: View>: View {
    let content: Content
    @State private var traits = "checking"
    init(@ViewBuilder content: () -> Content) { self.content = content() }
    var body: some View {
        content.overlay(alignment: .bottom) {
            if ProcessInfo.processInfo.arguments.contains("--lio-invitation-traits-acceptance") {
                Text(traits).font(.caption).accessibilityIdentifier("fixture.invitation.traits")
            }
        }
        .task {
            guard ProcessInfo.processInfo.arguments.contains("--lio-invitation-traits-acceptance") else { return }
            for _ in 0..<100 {
                let windows = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows)
                if let field = windows.compactMap({ secureField(in: $0) }).first,
                   field.isSecureTextEntry, field.autocapitalizationType == .none, field.autocorrectionType == .no,
                   field.smartQuotesType == .no, field.smartDashesType == .no, field.smartInsertDeleteType == .no {
                    traits = "literal-secure"; return
                }
                do { try await Task.sleep(for: .milliseconds(20)) } catch { return }
            }
            traits = "not-configured"
        }
    }
    private func secureField(in view: UIView) -> UITextField? {
        if let field = view as? UITextField, field.isSecureTextEntry { return field }
        for child in view.subviews { if let field = secureField(in: child) { return field } }
        return nil
    }
}
