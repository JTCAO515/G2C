#if os(iOS)
import SwiftUI
import UIKit

/// Configure only the native bar containing this Lio page. Platform backgrounds
/// and selected states remain owned by TabView and its existing tint.
struct LioTabBarAppearance: UIViewRepresentable {
    func makeUIView(context: Context) -> Anchor { Anchor(ink: ink(in: context.environment)) }
    func updateUIView(_ view: Anchor, context: Context) { view.update(ink: ink(in: context.environment)) }

    private func ink(in environment: EnvironmentValues) -> UIColor {
        UIColor(cgColor: LioTheme.inkSecondary.resolve(in: environment).cgColor)
    }

    final class Anchor: UIView {
        private var ink: UIColor

        init(ink: UIColor) {
            self.ink = ink
            super.init(frame: .zero)
            isAccessibilityElement = false
            isUserInteractionEnabled = false
        }
        @available(*, unavailable)
        required init?(coder: NSCoder) { fatalError() }

        override func didMoveToWindow() {
            super.didMoveToWindow()
            installWhenAttached()
        }

        func update(ink: UIColor) {
            self.ink = ink
            installWhenAttached()
        }

        private func installWhenAttached() {
            guard window != nil else { return }
            install()
            // SwiftUI can finish configuring the native page after attachment.
            // Reconcile that same instance on the next main-queue turn, without
            // a delay or a global UIAppearance setting.
            DispatchQueue.main.async { [weak self] in
                guard let self, self.window != nil else { return }
                self.install()
            }
        }

        private func install() {
            var responder: UIResponder? = self
            while let current = responder {
                if let controller = current as? UIViewController {
                    var parent: UIViewController? = controller
                    while let node = parent {
                        if let tabs = node as? UITabBarController {
                            apply(to: tabs.tabBar)
                            return
                        }
                        parent = node.parent
                    }
                }
                responder = current.next
            }
        }

        private func apply(to bar: UITabBar) {
            func matches(_ appearance: UITabBarAppearance) -> Bool {
                [appearance.stackedLayoutAppearance, appearance.inlineLayoutAppearance,
                 appearance.compactInlineLayoutAppearance].allSatisfy {
                    $0.normal.iconColor == ink && $0.normal.titleTextAttributes[.foregroundColor] as? UIColor == ink
                }
            }
            // This UIKit instance is also managed by SwiftUI. Avoid appearance
            // copies on ordinary body updates, but reapply if the platform has
            // replaced its normal-state configuration.
            if bar.unselectedItemTintColor == ink, matches(bar.standardAppearance),
               bar.scrollEdgeAppearance.map(matches) ?? true { return }
            func colored(_ appearance: UITabBarAppearance) -> UITabBarAppearance {
                let result = appearance.copy()
                for item in [result.stackedLayoutAppearance, result.inlineLayoutAppearance,
                             result.compactInlineLayoutAppearance] {
                    item.normal.iconColor = ink
                    item.normal.titleTextAttributes[.foregroundColor] = ink
                }
                return result
            }
            bar.unselectedItemTintColor = ink
            bar.standardAppearance = colored(bar.standardAppearance)
            if let edge = bar.scrollEdgeAppearance { bar.scrollEdgeAppearance = colored(edge) }
        }
    }
}
#endif
