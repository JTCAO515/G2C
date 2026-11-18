import XCTest
import SwiftUI
import UIKit
import CJLioUser

@MainActor final class LioTabBarColorUnitTests: XCTestCase {
    func testNormalPaletteIsLocalToLioInBothLanguagesAndAppearances() throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        for chinese in [false, true] {
            for dark in [false, true] {
                let style: UIUserInterfaceStyle = dark ? .dark : .light
                let before = unrelatedAppearance(scene: scene, style: style)
                let appeared = expectation(description: "Actual Lio Home appeared")
                let window = UIWindow(windowScene: scene)
                window.overrideUserInterfaceStyle = style
                let content = LioHome(language: chinese ? .chinese : .english, service: .unavailable, isDemo: true) { EmptyView() }
                    .background(TabTestAppearanceNotice { appeared.fulfill() }.frame(width: 0, height: 0))
                let host = UIHostingController(rootView: content)
                window.rootViewController = host
                window.makeKeyAndVisible()
                defer { window.isHidden = true }
                XCTAssertEqual(XCTWaiter.wait(for: [appeared], timeout: 5), .completed)
                host.view.layoutIfNeeded()
                let bar = try XCTUnwrap(tabController(in: host)?.tabBar)
                XCTAssertEqual(bar.items?.map(\.title), chinese ? ["聊天", "行程"] : ["Chat", "Trips"])
                let traits = UITraitCollection(userInterfaceStyle: style)
                let expected: UInt32 = dark ? 0xA89E92 : 0x6B6157 // Accepted D5 inkSecondary swatches.
                try assertColor(bar.unselectedItemTintColor, expected, traits: traits)
                for item in [bar.standardAppearance.stackedLayoutAppearance,
                             bar.standardAppearance.inlineLayoutAppearance,
                             bar.standardAppearance.compactInlineLayoutAppearance] {
                    try assertColor(item.normal.iconColor, expected, traits: traits)
                    try assertColor(item.normal.titleTextAttributes[.foregroundColor] as? UIColor, expected, traits: traits)
                }
                if let edge = bar.scrollEdgeAppearance {
                    for item in [edge.stackedLayoutAppearance, edge.inlineLayoutAppearance, edge.compactInlineLayoutAppearance] {
                        try assertColor(item.normal.iconColor, expected, traits: traits)
                        try assertColor(item.normal.titleTextAttributes[.foregroundColor] as? UIColor, expected, traits: traits)
                    }
                }
                window.isHidden = true
                XCTAssertEqual(unrelatedAppearance(scene: scene, style: style), before,
                               "Installing Lio must not change another native TabView's appearance")
            }
        }
    }

    func testPaletteUpdatesOnTheSameBarWhenAppearanceChanges() throws {
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let appeared = expectation(description: "Lio Home appeared before changing its appearance")
        let window = UIWindow(windowScene: scene)
        let host = UIHostingController(rootView: TabTestChangingAppearanceHome(dark: false) { appeared.fulfill() })
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer { window.isHidden = true }
        XCTAssertEqual(XCTWaiter.wait(for: [appeared], timeout: 5), .completed)
        let bar = try XCTUnwrap(tabController(in: host)?.tabBar)
        try assertColor(bar.unselectedItemTintColor, 0x6B6157, traits: UITraitCollection(userInterfaceStyle: .light))
        for dark in [true, false] {
            let oldColor = try XCTUnwrap(bar.unselectedItemTintColor)
            host.rootView = TabTestChangingAppearanceHome(dark: dark) {}
            let changed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "unselectedItemTintColor != %@", oldColor), object: bar)
            XCTAssertEqual(XCTWaiter.wait(for: [changed], timeout: 5), .completed)
            XCTAssertTrue(tabController(in: host)?.tabBar === bar)
            let traits = UITraitCollection(userInterfaceStyle: dark ? .dark : .light)
            let expected: UInt32 = dark ? 0xA89E92 : 0x6B6157
            try assertColor(bar.unselectedItemTintColor, expected, traits: traits)
            try assertColor(bar.standardAppearance.stackedLayoutAppearance.normal.iconColor, expected, traits: traits)
            try assertColor(bar.standardAppearance.stackedLayoutAppearance.normal.titleTextAttributes[.foregroundColor] as? UIColor, expected, traits: traits)
        }
    }

    private func tabController(in parent: UIViewController) -> UITabBarController? {
        if let tabs = parent as? UITabBarController { return tabs }
        return parent.children.lazy.compactMap { self.tabController(in: $0) }.first
    }

    private func assertColor(_ color: UIColor?, _ hex: UInt32, traits: UITraitCollection,
                             file: StaticString = #filePath, line: UInt = #line) throws {
        let actual = try XCTUnwrap(color, "An explicit D5 normal-state color is missing", file: file, line: line)
            .resolvedColor(with: traits)
        var red: CGFloat = 0, green: CGFloat = 0, blue: CGFloat = 0, alpha: CGFloat = 0
        XCTAssertTrue(actual.getRed(&red, green: &green, blue: &blue, alpha: &alpha), file: file, line: line)
        XCTAssertEqual(red, CGFloat((hex >> 16) & 255) / 255, accuracy: 0.002, file: file, line: line)
        XCTAssertEqual(green, CGFloat((hex >> 8) & 255) / 255, accuracy: 0.002, file: file, line: line)
        XCTAssertEqual(blue, CGFloat(hex & 255) / 255, accuracy: 0.002, file: file, line: line)
        XCTAssertEqual(alpha, 1, accuracy: 0.002, file: file, line: line)
    }

    private func unrelatedAppearance(scene: UIWindowScene, style: UIUserInterfaceStyle) -> [String] {
        let window = UIWindow(windowScene: scene)
        window.overrideUserInterfaceStyle = style
        let tabs = UITabBarController()
        tabs.viewControllers = [UIViewController(), UIViewController()]
        window.rootViewController = tabs
        window.makeKeyAndVisible()
        tabs.view.layoutIfNeeded()
        let traits = UITraitCollection(userInterfaceStyle: style)
        func value(_ color: UIColor?) -> String {
            guard let color else { return "unset" }
            return color.resolvedColor(with: traits).description
        }
        let bar = tabs.tabBar
        var result = [value(bar.unselectedItemTintColor)]
        for item in [bar.standardAppearance.stackedLayoutAppearance, bar.standardAppearance.inlineLayoutAppearance,
                     bar.standardAppearance.compactInlineLayoutAppearance] {
            result += [value(item.normal.iconColor), value(item.normal.titleTextAttributes[.foregroundColor] as? UIColor)]
        }
        window.isHidden = true
        return result
    }
}

private struct TabTestAppearanceNotice: UIViewControllerRepresentable {
    let appeared: @MainActor () -> Void
    func makeUIViewController(context: Context) -> NoticeController { NoticeController(appeared: appeared) }
    func updateUIViewController(_ controller: NoticeController, context: Context) {}
    final class NoticeController: UIViewController {
        private var appeared: (@MainActor () -> Void)?
        init(appeared: @escaping @MainActor () -> Void) { self.appeared = appeared; super.init(nibName: nil, bundle: nil) }
        @available(*, unavailable) required init?(coder: NSCoder) { fatalError() }
        override func viewDidAppear(_ animated: Bool) {
            super.viewDidAppear(animated)
            let callback = appeared; appeared = nil; callback?()
        }
    }
}

private struct TabTestChangingAppearanceHome: View {
    let dark: Bool
    let appeared: @MainActor () -> Void
    var body: some View {
        LioHome(language: .english, service: .unavailable, isDemo: true) { EmptyView() }
            .background(TabTestAppearanceNotice(appeared: appeared).frame(width: 0, height: 0))
            .preferredColorScheme(dark ? .dark : .light)
    }
}
