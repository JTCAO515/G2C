import SwiftUI
import CJShell
#if G2C_LIO_APP
import CJLioUser
import CJRunClient
#endif
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJTripClient
#endif

/// The native product uses Lio. Development profiles keep their existing shell.
///
/// The scene's content factory is called by SwiftUI's `LazyView`, which on iOS 27 may run it on the
/// `com.apple.SwiftUI.AsyncRenderer` thread. A closure written inside this `@MainActor` `App.body` is
/// inferred `@MainActor`, and Swift 6 traps at its entry when that happens off the main thread.
/// So the factory is a `@Sendable` function reference with no isolation, which only builds an empty
/// entry view. The state and the whole view tree live in `CJProbeRoot`, created from the entry view's
/// `body`, which SwiftUI always evaluates on the main thread.
@main
struct CJProbeApp: App {
    private static let makeEntry: @Sendable () -> CJProbeRootEntry = CJProbeRootEntry.init

    var body: some Scene { WindowGroup(content: Self.makeEntry) }
}

struct CJProbeRootEntry: View {
    nonisolated init() {}

    var body: some View { CJProbeRoot() }
}

struct CJProbeRoot: View {
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

    #if DEBUG && targetEnvironment(simulator) && G2C_LIO_APP
    private let localMedicalCardPreview = Self.makeMedicalCardPreview()
    private let travelProfilePreview = LioTravelProfilePreview.make()
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

    // The nesting below keeps the layout the acceptance scripts patch by exact text.
    var body: some View {
        Group {
            Group {
                #if G2C_DEMO_BETA
                if let demo { DemoBetaRootView(shell: shell, root: demo) }
                else {
                    Text(shell.language.text("Lio is temporarily unavailable.", "暂时打不开 Lio。"))
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .lioEmergencySupportFallback(language: shell.language.lio, enabled: true)
                }
                #elseif DEBUG && (targetEnvironment(simulator) || (os(iOS) && G2C_M4_DEVICE_ACCEPTANCE))
                #if targetEnvironment(simulator)
                #if G2C_LIO_APP
                if canPreviewLio, ProcessInfo.processInfo.arguments.contains("--lio-onboarding-preview") {
                    LioOnboardingPreview(shell: shell)
                        .lioEmergencySupportFallback(
                            language: shell.language.lio,
                            enabled: ProcessInfo.processInfo.arguments.contains("--lio-support-sos")
                        )
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
            #if !G2C_DEMO_BETA
            .modifier(LioInformationHost(shell: shell))
            #endif
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
            let home = LioHome(language: shell.language.lio, service: .demo, isDemo: true,
                               showsTools: ProcessInfo.processInfo.arguments.contains("--lio-tools-preview"),
                               toolsRelay: translationRelayPreview,
                               savedPlans: travelProfilePreview?.savedPlans,
                               roadbookDirectory: travelProfilePreview.map { LioAccountFolders.roadbooks(inMessageDirectory: $0.messageDirectory) },
                               tripHomeStore: travelProfilePreview?.tripHome,
                               messageDirectory: travelProfilePreview?.messageDirectory,
                               toolsDraftStorage: localSupportDraftPreview,
                               answerFeedback: LioAnswerFeedbackPreview.launch) {
                LioMenuSettings(shell: shell)
            }
            .lioMedicalCardStorage(localMedicalCardPreview)
            .lioToolServices(LioToolServices().with(travelProfilePreview.map {
                LioTravelProfileSource.device(messageDirectory: $0.messageDirectory, savedPlans: $0.savedPlans,
                                              tripHome: $0.tripHome, isCurrent: { true })
            }))
            if ProcessInfo.processInfo.arguments.contains("--lio-support-dial-preview"),
               let number = ProcessInfo.processInfo.environment["G2C_LOCAL_SUPPORT_TEST_PHONE"] {
                LioSupportDialPreview(number: number, content: home)
            } else {
                home
            }
        }
    }

    /// `--lio-home-plan-acceptance` only: one throwaway account folder per launch (never the signed-in account's),
    /// so the trip home, Back to Hotel and show-card details typed in the preview prefill the tools as on Beta.
    private struct LioTravelProfilePreview {
        let messageDirectory: URL
        let savedPlans: LioSavedPlans
        let tripHome: LioTripHomeStore

        @MainActor static func make() -> Self? {
            guard ProcessInfo.processInfo.arguments.contains("--lio-home-plan-acceptance") else { return nil }
            let root = FileManager.default.temporaryDirectory
                .appendingPathComponent("LioTravelProfilePreview-\(ProcessInfo.processInfo.processIdentifier)", isDirectory: true)
            return Self(messageDirectory: root,
                        savedPlans: LioSavedPlans(directory: LioSavedPlans.storageDirectory(inMessageDirectory: root),
                                                  isCurrent: { true }),
                        tripHome: LioTripHomeStore(directory: LioTripHomeStore.storageDirectory(inMessageDirectory: root),
                                                   isCurrent: { true }))
        }
    }

    private static func makeMedicalCardPreview() -> LocalMedicalCardStorage? {
        guard let value = ProcessInfo.processInfo.environment["G2C_LIO_MEDICAL_CARD_FIXTURE"],
              let identity = UUID(uuidString: value),
              let applicationID = try? DevelopmentKeychainIdentity.read() else { return nil }
        return try? LocalMedicalCardVault(applicationIdentifier: applicationID)
            .storage(for: .init(environment: identity, account: identity), isCurrent: { true })
    }

    private var localSupportDraftPreview: LocalSupportDraftStorage? {
        guard let value = ProcessInfo.processInfo.environment["G2C_LIO_SUPPORT_DRAFT_FIXTURE"],
              let identity = UUID(uuidString: value),
              let applicationID = try? DevelopmentKeychainIdentity.read() else { return nil }
        return LocalSupportKeychainDraft(applicationIdentifier: applicationID)
            .storage(for: .account(environment: identity, account: identity), isCurrent: { true })
    }

    private var translationRelayPreview: LioRelayTranslationClient? {
        guard ProcessInfo.processInfo.arguments.contains("--lio-translation-relay-preview") else { return nil }
        let photoQuotaFixture = ProcessInfo.processInfo.arguments.contains("--lio-translation-photo-quota-preview")
        let photoEmptyFixture = ProcessInfo.processInfo.arguments.contains("--lio-translation-photo-empty-preview")
        let photoTimeoutFixture = ProcessInfo.processInfo.arguments.contains("--lio-translation-photo-timeout-preview")
        let photoLoginFixture = ProcessInfo.processInfo.arguments.contains("--lio-translation-photo-login-preview")
        let layoutFixture = ProcessInfo.processInfo.arguments.contains("--lio-translation-photo-layout-preview")
        var timedOutOriginal: Data?
        var timedOutPhoto: Data?
        var reauthPhoto: Data?
        return LioRelayTranslationClient(supportsImageLayout: layoutFixture) { route, data in
            guard let fields = try JSONSerialization.jsonObject(with: data) as? [String: String],
                  fields["source_lang"] == "en", fields["target_lang"] == "zh" else {
                return (400, Data())
            }
            if layoutFixture && route == "/v1/tools/translate/image-layout" &&
                fields["version"] == "IMAGE-LAYOUT.1" && fields["kind"] == "image",
               let media = fields["media"], let bytes = Data(base64Encoded: media),
               let bitmap = UIImage(data: bytes)?.cgImage {
                let width = bitmap.width, height = bitmap.height
                let left = width * 8 / 100, right = width * 45 / 100
                let firstTop = height * 8 / 100, firstBottom = height * 42 / 100
                let secondTop = height * 50 / 100, secondBottom = height * 86 / 100
                let items: [[String: Any]] = [
                    ["source_text": "Tea", "translated_text": "茶",
                     "location": [left, firstTop, right, firstTop, right, firstBottom, left, firstBottom]],
                    ["source_text": "Coffee", "translated_text": "咖啡",
                     "location": [left, secondTop, right, secondTop, right, secondBottom, left, secondBottom]]
                ]
                return (200, try JSONSerialization.data(withJSONObject: [
                    "version": "IMAGE-LAYOUT.1", "image_width": width, "image_height": height, "items": items
                ]))
            }
            guard route == "/v1/tools/translate", fields["version"] == "TRANSLATION.1" else { return (400, Data()) }
            if fields["kind"] == "text", fields["text"] == "Timed out" {
                if let timedOutOriginal {
                    return timedOutOriginal == data ? (409, Data()) : (422, Data())
                }
                timedOutOriginal = data
                throw URLError(.timedOut)
            }
            if fields["kind"] == "text", fields["text"] == "Already sent" {
                return (409, Data(#"{"version":"TRANSLATION.1","error":"request_already_used"}"#.utf8))
            }
            if fields["kind"] == "text" {
                switch fields["text"] {
                case "Offline input": throw URLError(.notConnectedToInternet)
                case "Expired input": return (401, Data())
                case "Unavailable input": return (503, Data())
                default: break
                }
            }
            if fields["kind"] == "text", fields["text"] == "Hello" {
                return (200, Data(#"{"version":"TRANSLATION.1","kind":"text","items":[{"source_text":"Hello","translated_text":"你好"}]}"#.utf8))
            }
            if fields["kind"] == "image", let media = fields["media"], let image = Data(base64Encoded: media),
               image.starts(with: [0xff, 0xd8, 0xff]), fields["media_type"] == nil {
                if photoLoginFixture {
                    if let reauthPhoto {
                        guard reauthPhoto == data else { return (422, Data()) }
                    } else {
                        reauthPhoto = data
                        return (401, Data())
                    }
                }
                if photoQuotaFixture {
                    return (429, Data(#"{"version":"TRANSLATION.1","error":"quota_exceeded"}"#.utf8))
                }
                if photoEmptyFixture {
                    return (200, Data(#"{"version":"TRANSLATION.1","kind":"image","items":[]}"#.utf8))
                }
                if photoTimeoutFixture {
                    if let timedOutPhoto {
                        guard timedOutPhoto == data else { return (422, Data()) }
                    } else {
                        timedOutPhoto = data
                        throw URLError(.timedOut)
                    }
                }
                return (200, Data(#"{"version":"TRANSLATION.1","kind":"image","items":[{"source_text":"Tea","translated_text":"茶"},{"source_text":"Coffee","translated_text":"咖啡"}]}"#.utf8))
            }
            return (400, Data())
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
        Menu {
            Picker(shell.language.text("Language", "语言"),
                   selection: Binding(get: { shell.language }, set: { shell.selectLanguage($0) })) {
                Text("English").tag(ShellLanguage.english)
                Text("简体中文").tag(ShellLanguage.chinese)
            }
        } label: {
            HStack {
                RunReadableText(text: shell.language.text("Language", "语言"), color: LioTheme.ink)
                Spacer(minLength: 8)
                RunReadableText(text: shell.language.text("English", "简体中文"), color: LioTheme.inkSecondary)
                    .fixedSize(horizontal: true, vertical: true)
                Image(systemName: "chevron.up.chevron.down").font(.caption).accessibilityHidden(true)
            }
            .frame(minHeight: 44)
            .contentShape(Rectangle())
        }
        .accessibilityLabel(shell.language.text("Language", "语言"))
        .accessibilityValue(shell.language.text("English", "简体中文"))
        .accessibilityIdentifier("lio.language")
    }
}

struct LioMenuSettings: View {
    let shell: ShellState
    @Environment(LioInformationPresentation.self) private var information

    var body: some View {
        LioLanguagePicker(shell: shell)
        LioAppearancePicker(language: shell.language.lio)
        Button(shell.language.text("Internal demo information", "内部演示说明")) { information.isPresented = true }
            .frame(minHeight: 44, alignment: .leading)
            .accessibilityIdentifier("lio.information")
        // #1880: the privacy summary (policy 1.0), reachable from Me in every Lio build.
        NavigationLink(PrivacySummary.title(shell.language)) {
            PrivacyNoticeView(language: shell.language, showsSupportLink: false)
        }
        .frame(minHeight: 44, alignment: .leading)
        .accessibilityIdentifier("lio.privacy-summary")
    }
}

@Observable private final class LioInformationPresentation {
    var isPresented = false
}

// The settings row leaves the lazy list when text size changes. Keep its presentation
// on the signed-in home, so the sheet survives a reflow and closes with that session.
struct LioInformationHost: ViewModifier {
    let shell: ShellState
    @State private var information = LioInformationPresentation()

    func body(content: Content) -> some View {
        content
            .environment(information)
            .sheet(isPresented: $information.isPresented) {
                NavigationStack {
                    LioDemoNoticePage(language: shell.language.lio) { EmptyView() }
                        .safeAreaInset(edge: .top, spacing: 0) {
                            HStack {
                                Spacer()
                                Button { information.isPresented = false } label: {
                                    Text(shell.language.text("Done", "完成"))
                                        .font(.body)
                                        .foregroundStyle(LioTheme.ink)
                                        .fixedSize()
                                        .frame(minWidth: 44, minHeight: 44)
                                        .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier("lio.information.done")
                            }
                            .padding(.horizontal, 24)
                            .padding(.vertical, 8)
                            .background(LioTheme.paper)
                        }
                }
                .tint(LioTheme.vermilion)
            }
    }
}
#endif


#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private struct LioSupportDialPreview<Content: View>: View {
    let number: String
    let content: Content
    @State private var matched = false

    var body: some View {
        content
            .environment(\.openURL, OpenURLAction { url in
                matched = url.absoluteString == "tel:" + number
                return matched ? .handled : .discarded
            })
            .overlay(alignment: .topLeading) {
                Text(matched ? "Test dial request matched" : "Dial fixture ready")
                    .font(.footnote)
                    .accessibilityIdentifier(matched ? "fixture.support.dial-matched" : "fixture.support.dial-intercept-ready")
                    .allowsHitTesting(false)
            }
    }
}

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
