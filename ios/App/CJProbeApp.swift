import SwiftUI
import CJShell
#if G2C_LIO_APP
import CJLioUser
#endif
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJTripClient
#endif

/// The native product uses Lio. Development profiles keep their existing shell.
@main
struct CJProbeApp: App {
    @State private var shell: ShellState
    #if G2C_LIO_APP
    @AppStorage(LioAppearance.preferenceKey) private var appearance = LioAppearance.system
    #endif
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
            Group {
                #if G2C_DEMO_BETA
                if let demo { DemoBetaRootView(shell: shell, root: demo) }
                else { Text(shell.language.text("Lio is temporarily unavailable.", "暂时打不开 Lio。")) }
                #elseif DEBUG && (targetEnvironment(simulator) || (os(iOS) && G2C_M4_DEVICE_ACCEPTANCE))
                #if targetEnvironment(simulator)
                #if G2C_LIO_APP
                if canPreviewLio, ProcessInfo.processInfo.arguments.contains("--lio-onboarding-preview") {
                    LioOnboardingPreview(shell: shell)
                } else if canPreviewLio, ProcessInfo.processInfo.arguments.contains("--lio-preview") {
                    lioPreview
                } else {
                    debugPreviewOrShell
                }
                #else
                debugPreviewOrShell
                #endif
                #else
                developmentShell
                #endif
                #elseif DEBUG || !G2C_LIO_APP
                // The generated acceptance projects keep the disconnected shell
                // to exercise their existing Release negative cases.
                ShellView(state: shell)
                #else
                LioHome(language: shell.language.lio, service: .unavailable, isDemo: false) { LioMenuSettings(shell: shell) }
                #endif
            }
            #if G2C_LIO_APP
            .preferredColorScheme(appearance.colorScheme)
            #endif
        }
    }

    #if DEBUG && targetEnvironment(simulator) && G2C_LIO_APP
    private var canPreviewLio: Bool {
        !ProcessInfo.processInfo.environment.keys.contains(where: { $0.hasPrefix("G2C_DEV_") })
            && development == nil && developmentAccounts == nil && !developmentFailed
    }

    @ViewBuilder private var lioPreview: some View {
        if let encoded = ProcessInfo.processInfo.environment["G2C_LIO_PREVIEW_TRIP"] {
            switch Result(catching: { try LioPreviewTripFixture.library(encoded) }) {
            case .success(let library):
                LioHome(language: shell.language.lio, service: .demo, isDemo: true, tripLibrary: library,
                        recordedMap: { document in
                    AnyView(LioRecordedTripMap(document: document, language: shell.language))
                }) { LioMenuSettings(shell: shell) }
            case .failure:
                Text(shell.language.text("Sample trip unavailable.", "示例行程暂不可用。"))
            }
        } else {
            LioHome(language: shell.language.lio, service: .demo, isDemo: true) { LioMenuSettings(shell: shell) }
        }
    }
    #endif

    #if DEBUG && targetEnvironment(simulator)
    @ViewBuilder private var debugPreviewOrShell: some View {
        if ProcessInfo.processInfo.arguments.contains("--demo-v2-preview"),
           !ProcessInfo.processInfo.environment.keys.contains(where: { $0.hasPrefix("G2C_DEV_") }),
           development == nil, developmentAccounts == nil, !developmentFailed {
            DemoV2Preview(shell: shell)
        } else {
            developmentShell
        }
    }
    #endif

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

#if G2C_LIO_APP
extension ShellLanguage {
    var lio: LioLanguage { self == .chinese ? .chinese : .english }
}

struct LioLanguagePicker: View {
    let shell: ShellState

    var body: some View {
        Picker(shell.language.text("Language", "语言"),
               selection: Binding(get: { shell.language }, set: { shell.selectLanguage($0) })) {
            Text("English").tag(ShellLanguage.english)
            Text("简体中文").tag(ShellLanguage.chinese)
        }
        .accessibilityIdentifier("lio.language")
    }
}

struct LioMenuSettings: View {
    let shell: ShellState

    var body: some View {
        LioLanguagePicker(shell: shell)
        LioAppearancePicker(language: shell.language.lio)
    }
}
#endif


#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private struct LioPreviewTripFixture: Decodable {
    let trace: String
    let list: Data
    let detail: Data

    static func library(_ encoded: String) throws -> LioTripLibrary {
        guard let data = Data(base64Encoded: encoded) else { throw TripFailure.invalidResponse }
        let fixture = try JSONDecoder().decode(Self.self, from: data)
        let page = try StructuredTripReadV1.page(fixture.list, requestID: fixture.trace)
        guard let record = try StructuredTripReadV1.detail(fixture.detail, requestID: fixture.trace),
              page.trips.contains(where: { $0.tripID == record.tripID }) else {
            throw TripFailure.invalidResponse
        }
        return LioTripLibrary(list: { page.trips }, detail: { id in
            id == record.tripID ? record : nil
        })
    }
}

private struct LioOnboardingPreview: View {
    let shell: ShellState
    @State private var admitted = false

    var body: some View {
        if admitted {
            LioHome(language: shell.language.lio, service: .demo, isDemo: true) { LioMenuSettings(shell: shell) }
        } else {
            LioInvitationView(language: shell.language.lio, isBusy: false, notice: nil,
                              onInvite: { _ in admitted = true }, onRestore: { admitted = true }) {
                LioLanguagePicker(shell: shell)
            }
        }
    }
}
#endif
