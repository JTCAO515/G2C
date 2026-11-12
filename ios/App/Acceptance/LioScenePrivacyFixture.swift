// Deterministic scene-interruption UI probe. No credentials or network.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import Observation

@MainActor @Observable
private final class LioPrivacyProbeState {
    var phase = ScenePhase.active
    var showingSheet = false
    var rootDraft = "Synthetic root draft"
    var sheetDraft = "Synthetic sheet draft"
    var actions = 0
}

private struct LioScenePrivacyFixture: View {
    let shell: ShellState
    @State private var state = LioPrivacyProbeState()

    var body: some View {
        LioPrivacyProbePanel(state: state, scope: "root")
            .sheet(isPresented: $state.showingSheet) {
                LioPrivacyProbePanel(state: state, scope: "sheet")
            }
            .modifier(LioScenePrivacy(testPhase: state.phase, resume: { state.phase = .active }))
    }
}

private struct LioPrivacyProbePanel: View {
    let state: LioPrivacyProbeState
    let scope: String

    var body: some View {
        VStack(spacing: 0) {
            NavigationStack {
                VStack(spacing: 20) {
                    Text("Synthetic private \(scope) text")
                        .accessibilityIdentifier("privacy.\(scope).text")
                    TextField("Synthetic draft", text: Binding(
                        get: { scope == "root" ? state.rootDraft : state.sheetDraft },
                        set: { if scope == "root" { state.rootDraft = $0 } else { state.sheetDraft = $0 } }))
                        .textFieldStyle(.roundedBorder)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("privacy.\(scope).draft")
                    Button { state.actions += 1 } label: {
                        Text("Private action").frame(minHeight: 44)
                    }
                    .accessibilityIdentifier("privacy.\(scope).action")
                    if scope == "root" {
                        Button { state.showingSheet = true } label: { Text("Open sheet").frame(minHeight: 44) }
                            .accessibilityIdentifier("privacy.open-sheet")
                    } else {
                        Button { state.showingSheet = false } label: { Text("Close sheet").frame(minHeight: 44) }
                            .accessibilityIdentifier("privacy.close-sheet")
                    }
                }
                .padding(24)
                .navigationTitle("Synthetic private \(scope) title")
            }
            HStack {
                Button { state.phase = .inactive } label: { Text("Interrupt").frame(minHeight: 44) }
                    .accessibilityIdentifier("privacy.\(scope).interrupt")
                Button { state.phase = .active } label: { Text("Resume").frame(minHeight: 44) }
                    .accessibilityIdentifier("privacy.\(scope).resume")
                Text(String(state.actions)).accessibilityIdentifier("privacy.\(scope).actions")
            }
            .padding(16)
            .background(LioTheme.paper)
        }
        .tint(LioTheme.vermilion)
    }
}
#endif
