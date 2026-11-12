#if os(iOS)
import SwiftUI
import UIKit

extension View {
    /// Install once at the scene root. It protects that scene's windows, including sheets.
    public func lioScenePrivacy() -> some View { modifier(LioScenePrivacy()) }
}

struct LioScenePrivacy: ViewModifier {
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.colorScheme) private var colorScheme
    private let testPhase: ScenePhase?
    private let testResume: (@MainActor () -> Void)?
    init() { testPhase = nil; testResume = nil }
    #if DEBUG
    init(testPhase: ScenePhase, resume: @escaping @MainActor () -> Void) {
        self.testPhase = testPhase; testResume = resume
    }
    #endif

    func body(content: Content) -> some View {
        ZStack { content }.background(PrivacyAnchor(protected: (testPhase ?? scenePhase) != .active,
                                         style: colorScheme == .dark ? .dark : .light,
                                         testResume: testResume).allowsHitTesting(false))
    }
}

private struct PrivacyAnchor: UIViewRepresentable {
    let protected: Bool
    let style: UIUserInterfaceStyle
    let testResume: (@MainActor () -> Void)?
    func makeCoordinator() -> PrivacyWindows { PrivacyWindows() }
    func makeUIView(context: Context) -> PrivacyAnchorView {
        let view = PrivacyAnchorView()
        view.moved = { [weak coordinator = context.coordinator] window in coordinator?.attach(window?.windowScene) }
        return view
    }
    func updateUIView(_ view: PrivacyAnchorView, context: Context) {
        context.coordinator.update(protected: protected, style: style, testResume: testResume)
        context.coordinator.attach(view.window?.windowScene)
    }
    static func dismantleUIView(_ view: PrivacyAnchorView, coordinator: PrivacyWindows) { coordinator.detach() }
}

private final class PrivacyAnchorView: UIView {
    var moved: ((UIWindow?) -> Void)?
    override func didMoveToWindow() { super.didMoveToWindow(); moved?(window) }
}

/// No client or credential is retained here. The original window flags are restored exactly.
@MainActor
private final class PrivacyWindows: NSObject {
    private struct CoveredWindow {
        weak var window: UIWindow?
        let cover: UIView
        let accessibilityHidden: Bool
        let interactive: Bool
    }
    private weak var scene: UIWindowScene?
    private var covered: [ObjectIdentifier: CoveredWindow] = [:]
    private var shield: UIWindow?
    private var protecting = false
    private var style = UIUserInterfaceStyle.light
    private var testResume: (@MainActor () -> Void)?

    override init() {
        super.init()
        NotificationCenter.default.addObserver(self, selector: #selector(windowAppeared(_:)),
                                               name: UIWindow.didBecomeVisibleNotification, object: nil)
    }
    deinit { NotificationCenter.default.removeObserver(self) }

    func attach(_ next: UIWindowScene?) {
        guard scene !== next else { return }
        restore()
        scene = next
        if protecting { protect() }
    }
    func update(protected: Bool, style: UIUserInterfaceStyle, testResume: (@MainActor () -> Void)?) {
        protecting = protected; self.style = style; self.testResume = testResume
        if protected { protect() } else { restore() }
    }
    func detach() { protecting = false; restore(); scene = nil }

    private var paper: UIColor {
        UIColor(LioTheme.paper).resolvedColor(with: UITraitCollection(userInterfaceStyle: style))
    }
    private func cover(_ window: UIWindow) {
        guard window !== shield, window.windowScene === scene, covered[ObjectIdentifier(window)] == nil else { return }
        let cover = UIView(frame: window.bounds)
        cover.backgroundColor = paper
        cover.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        covered[ObjectIdentifier(window)] = CoveredWindow(window: window, cover: cover,
            accessibilityHidden: window.accessibilityElementsHidden, interactive: window.isUserInteractionEnabled)
        window.endEditing(true)
        window.accessibilityElementsHidden = true
        window.isUserInteractionEnabled = false
        window.addSubview(cover)
    }
    private func protect() {
        guard let scene else { return }
        scene.windows.forEach(cover)
        covered.values.forEach { $0.cover.backgroundColor = paper }
        if let shield {
            shield.overrideUserInterfaceStyle = style
            shield.rootViewController?.view.backgroundColor = paper
            return
        }
        let window = UIWindow(windowScene: scene)
        let controller = UIViewController()
        controller.view.backgroundColor = paper
        controller.view.accessibilityViewIsModal = true
        controller.view.isAccessibilityElement = true
        controller.view.accessibilityLabel = "Lio"
        window.windowLevel = UIWindow.Level(rawValue: UIWindow.Level.alert.rawValue + 1)
        window.overrideUserInterfaceStyle = style
        window.rootViewController = controller
        #if DEBUG
        if let testResume {
            controller.view.isAccessibilityElement = false
            let button = UIButton(type: .system)
            button.setTitle("Resume", for: .normal)
            button.titleLabel?.font = .preferredFont(forTextStyle: .body)
            button.titleLabel?.adjustsFontForContentSizeCategory = true
            button.setTitleColor(UIColor(LioTheme.ink).resolvedColor(with: UITraitCollection(userInterfaceStyle: style)), for: .normal)
            button.accessibilityIdentifier = "lio.privacy.test.resume"
            button.translatesAutoresizingMaskIntoConstraints = false
            button.addAction(UIAction { _ in testResume() }, for: .touchUpInside)
            controller.view.addSubview(button)
            NSLayoutConstraint.activate([
                button.centerXAnchor.constraint(equalTo: controller.view.centerXAnchor),
                button.bottomAnchor.constraint(equalTo: controller.view.safeAreaLayoutGuide.bottomAnchor, constant: -20),
                button.widthAnchor.constraint(greaterThanOrEqualToConstant: 120),
                button.heightAnchor.constraint(greaterThanOrEqualToConstant: 44)
            ])
        }
        #endif
        shield = window
        // The shield never becomes key; the user's responder and presentation ownership stay with the App.
        window.isHidden = false
    }
    @objc private func windowAppeared(_ note: Notification) {
        guard protecting, let window = note.object as? UIWindow else { return }
        cover(window)
    }
    private func restore() {
        for value in covered.values {
            value.cover.removeFromSuperview()
            value.window?.accessibilityElementsHidden = value.accessibilityHidden
            value.window?.isUserInteractionEnabled = value.interactive
        }
        covered.removeAll()
        shield?.isHidden = true
        shield = nil
    }
}
#endif
