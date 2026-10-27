import SwiftUI
import CJShell

/// G2C App entry: the four-tab Muse shell (P2c). The state lives for the window lifetime;
/// no `.id(language)` or recreation on language change (CJShell README).
@main
struct CJProbeApp: App {
    @State private var shell: ShellState
    #if DEBUG && targetEnvironment(simulator)
    @State private var development: DevelopmentTripHost?
    @State private var developmentFailed = false
    @Environment(\.scenePhase) private var scenePhase
    #endif

    init() {
        let shell = ShellState()
        _shell = State(initialValue: shell)
        #if DEBUG && targetEnvironment(simulator)
        do {
            let host = try DevelopmentSessionConfiguration.read(ProcessInfo.processInfo.environment)
                .map { try DevelopmentTripHost(configuration: $0, shell: shell) }
            _development = State(initialValue: host)
        } catch {
            _development = State(initialValue: nil)
            _developmentFailed = State(initialValue: true)
        }
        #endif
    }

    var body: some Scene {
        WindowGroup {
            #if DEBUG && targetEnvironment(simulator)
            ShellView(state: shell, tripContainerHost: development?.trips)
                .id(development?.id) // host lifetime only; ShellState/language are retained
                .safeAreaInset(edge: .top) {
                    if developmentFailed {
                        Text(shell.language.text("Development trip connection unavailable", "开发行程连接不可用"))
                            .font(.caption).accessibilityIdentifier("g2c.dev.error")
                    }
                }
                .onChange(of: scenePhase) { _, phase in
                    if phase != .active { development?.invalidate() }
                    else if let configuration = DevelopmentSessionConfiguration.read(ProcessInfo.processInfo.environment),
                            development?.trips.isConfigured != true {
                        do { development = try DevelopmentTripHost(configuration: configuration, shell: shell); developmentFailed = false }
                        catch { development = nil; developmentFailed = true }
                    }
                }
            #else
            ShellView(state: shell)
            #endif
        }
    }
}
