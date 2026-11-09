import SwiftUI
import CJShell

/// G2C App entry: the four-tab Muse shell (P2c). The state lives for the window lifetime;
/// no `.id(language)` or recreation on language change (CJShell README).
@main
struct CJProbeApp: App {
    @State private var shell: ShellState
    #if G2C_DEMO_BETA
    @State private var demo: DevelopmentAccountRoot?
    #endif
    #if DEBUG && (targetEnvironment(simulator) || (os(iOS) && G2C_M4_DEVICE_ACCEPTANCE))
    @State private var development: DevelopmentTripHost?
    @State private var developmentAccounts: DevelopmentAccountRoot?
    @State private var developmentFailed = false
    @Environment(\.scenePhase) private var scenePhase
    #endif

    init() {
        let shell = ShellState()
        _shell = State(initialValue: shell)
        #if G2C_DEMO_BETA
        _demo = State(initialValue: try? DevelopmentAccountRoot(demo: shell))
        #endif
        #if DEBUG && (targetEnvironment(simulator) || (os(iOS) && G2C_M4_DEVICE_ACCEPTANCE))
        do {
            let environment = ProcessInfo.processInfo.environment
            #if os(iOS) && !targetEnvironment(simulator) && G2C_M4_DEVICE_ACCEPTANCE
            if environment["G2C_M4_DISCARD_ACCOUNTS_FILE"] == "1" {
                try DevelopmentAccountInput.discardStaged()
            }
            #endif
            if environment["G2C_DEV_ACCOUNT_MODE"] != nil {
                _developmentAccounts = State(initialValue: try DevelopmentAccountRoot(environment: environment, shell: shell))
                _development = State(initialValue: nil)
            } else {
                let host = try DevelopmentSessionConfiguration.read(environment)
                    .map { try DevelopmentTripHost(configuration: $0, shell: shell) }
                _development = State(initialValue: host)
                _developmentAccounts = State(initialValue: nil)
            }
        } catch {
            _development = State(initialValue: nil)
            _developmentAccounts = State(initialValue: nil)
            _developmentFailed = State(initialValue: true)
        }
        #endif
    }

    var body: some Scene {
        WindowGroup {
            #if G2C_DEMO_BETA
            if let demo { DemoBetaRootView(shell: shell, root: demo) }
            else { Text(shell.language.text("Secure demo session is unavailable.", "安全演示会话暂不可用。")) }
            #elseif DEBUG && (targetEnvironment(simulator) || (os(iOS) && G2C_M4_DEVICE_ACCEPTANCE))
            #if targetEnvironment(simulator)
            if ProcessInfo.processInfo.arguments.contains("--demo-v2-preview"),
               !ProcessInfo.processInfo.environment.keys.contains(where: { $0.hasPrefix("G2C_DEV_") }),
               development == nil, developmentAccounts == nil, !developmentFailed {
                DemoV2Preview(shell: shell)
            } else if ProcessInfo.processInfo.arguments.contains("--demo-v2-live-fixture"),
                      !ProcessInfo.processInfo.environment.keys.contains(where: { $0.hasPrefix("G2C_DEV_") }),
                      development == nil, developmentAccounts == nil, !developmentFailed {
                DemoV2LiveFixture(shell: shell)
            } else {
                developmentShell
            }
            #else
            developmentShell
            #endif
            #else
            ShellView(state: shell)
            #endif
        }
    }

    #if DEBUG && (targetEnvironment(simulator) || (os(iOS) && G2C_M4_DEVICE_ACCEPTANCE))
    private var developmentShell: some View {
        ShellView(state: shell, messageHost: developmentAccounts?.trip?.messages.messages ?? development?.messages.messages,
                  serverHistoryHost: developmentAccounts?.trip?.messages.history ?? development?.messages.history,
                  memoryContainerHost: developmentAccounts?.trip?.memory?.host ?? development?.memory?.host,
                  typedMemoryContainerHost:developmentAccounts?.trip?.typedMemory?.host ?? development?.typedMemory?.host,
                  tripContainerHost: developmentAccounts?.trip?.trips ?? development?.trips,
                  structuredTripHost: developmentAccounts?.trip?.structuredTrips ?? development?.structuredTrips,
                  needsContainerHost: developmentAccounts?.trip?.needs?.host ?? development?.needs?.host,
                  answerFeedbackHost: developmentAccounts?.trip?.feedback?.answer ?? development?.feedback?.answer,
                  generalFeedbackHost: developmentAccounts?.trip?.feedback?.general ?? development?.feedback?.general,
                  runContainerHost: developmentAccounts?.trip?.messages.runs ?? development?.messages.runs,
                  developmentAccountHost: developmentAccounts?.accounts, offlineTripController: developmentAccounts?.offline,
                  memoryHistoryContainerHost: developmentAccounts?.trip?.memoryHistory?.host ?? development?.memoryHistory?.host)
            .environment(\.accountCleanupHost, developmentAccounts?.cleanup)
            .id(developmentAccounts?.trip?.id ?? development?.id) // host lifetime only; ShellState/language retained
            .safeAreaInset(edge: .top) {
                if developmentFailed {
                    Text(shell.language.text("Development trip connection unavailable", "开发行程连接不可用"))
                        .font(.caption).accessibilityIdentifier("g2c.dev.error")
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if let developmentAccounts {
                    if phase == .active { developmentAccounts.accounts.resume() }
                    else { developmentAccounts.accounts.suspend() }
                    return
                }
                if phase != .active { development?.invalidate() }
                else if let configuration = DevelopmentSessionConfiguration.read(ProcessInfo.processInfo.environment),
                        development?.trips.isConfigured != true {
                    do { development = try DevelopmentTripHost(configuration: configuration, shell: shell); developmentFailed = false }
                    catch { development = nil; developmentFailed = true }
                }
            }
    }
    #endif
}
