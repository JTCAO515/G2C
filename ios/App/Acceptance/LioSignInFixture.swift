#if DEBUG && G2C_DEMO_BETA && targetEnvironment(simulator)
import SwiftUI
import Foundation
import CJSession
import CJMessageHTTP
import CJLioUser

@main struct LioSignInFixture: App {
    @AppStorage(LioAppearance.preferenceKey) private var appearance = LioAppearance.system
    @State private var shell = ShellState()
    @State private var root: DevelopmentAccountRoot?
    @State private var setupFailed = false

    var body: some Scene {
        WindowGroup {
            VStack(spacing: 0) {
                if let root {
                    DemoBetaRootView(shell: shell, root: root)
                    Text(state(root.accounts.state)).accessibilityIdentifier("fixture.signin.state")
                    if let note = LioDiagnosticLog.shared.entries.first {
                        Text(note.stage.rawValue + "|" + String(note.httpStatus ?? 0) + "|" + (note.reference ?? "-"))
                            .accessibilityIdentifier("fixture.signin.diagnostic")
                    }
                } else {
                    Text(setupFailed ? "Fixture setup failed" : "Fixture starting")
                }
            }
            .preferredColorScheme(appearance.colorScheme)
            .task {
                guard root == nil && !setupFailed else { return }
                do {
                    try NoRedirectTransport.installB691LocalFixture(LioSignInFixtureHTTP.self)
                    let ready = try DevelopmentAccountRoot(demo: shell)
                    root = ready
                    if try !ready.fixtureHasNoSavedMaterial() {
                        ready.accounts.restore()
                    }
                } catch { setupFailed = true }
            }
        }
    }

    private func state(_ state: DevelopmentAccountState) -> String {
        switch state {
        case .signedIn: "signed-in"
        case .responseUnavailable: "response-unavailable"
        case .networkUnknown: "network-unknown"
        case .checking: "checking"
        default: "not-signed-in"
        }
    }
}
#endif
