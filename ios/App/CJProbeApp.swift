import SwiftUI
import CJShell

/// G2C App entry: the four-tab Muse shell (P2c). The state lives for the window lifetime;
/// no `.id(language)` or recreation on language change (CJShell README).
@main
struct CJProbeApp: App {
    @State private var shell = ShellState()

    var body: some Scene {
        WindowGroup { ShellView(state: shell) }
    }
}
