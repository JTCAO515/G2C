#if os(iOS)
import SwiftUI
import UIKit

/// Apply the existing palette to this Lio TabView, retaining the platform background.
struct LioTabBarAppearance: UIViewRepresentable {
    func makeUIView(context: Context) -> Anchor { Anchor() }
    func updateUIView(_ view: Anchor, context: Context) { view.installWhenAttached() }

    final class Anchor: UIView {
        private weak var installedBar: UITabBar?

        override init(frame: CGRect) {
            super.init(frame: frame)
            isAccessibilityElement = false
            isUserInteractionEnabled = false
        }
        required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

        override func didMoveToWindow() {
            super.didMoveToWindow()
            installWhenAttached()
        }

        func installWhenAttached() {
            guard window != nil else { return }
            DispatchQueue.main.async { [weak self] in self?.install() }
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
            guard installedBar !== bar else { return }
            installedBar = bar
            let ink = UIColor(LioTheme.inkSecondary)
            bar.unselectedItemTintColor = ink
            func colored(_ source: UITabBarAppearance) -> UITabBarAppearance {
                let result = source.copy()
                for item in [result.stackedLayoutAppearance, result.inlineLayoutAppearance,
                             result.compactInlineLayoutAppearance] {
                    item.normal.iconColor = ink
                    item.normal.titleTextAttributes[.foregroundColor] = ink
                }
                return result
            }
            bar.standardAppearance = colored(bar.standardAppearance)
            if let edge = bar.scrollEdgeAppearance { bar.scrollEdgeAppearance = colored(edge) }
        }
    }
}
#endif
