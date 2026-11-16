// Local synthetic account/persistence only; the generated Root expression comes from App source.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJSession
import Observation

@MainActor private final class LioActivationFailurePersistence: SessionPersistence {
    let value: SessionMaterial
    init() throws { value = try SessionMaterial(trustedSDKBytes: Data("synthetic-only".utf8)) }
    var clears = 0
    func load() throws -> SessionMaterial? { value }
    func save(_ material: SessionMaterial) throws {}
    func clearAndBlock() throws { clears += 1 }
}
@MainActor @Observable private final class LioActivationFailureRoot {
    let shell: ShellState
    var attempts = 0
    var lioSessionProblem: LioRequestProblem?
    let store: LioActivationFailurePersistence
    @ObservationIgnored lazy var accounts = DevelopmentAccountHost(shell: shell, choices: [], persistence: store,
        demoMode: true, material: { _ in throw SessionFailure.invalidConfiguration },
        verify: { _ in .accepted(account: "synthetic-owner") },
        activate: { [weak self] _,_,_ in
            self?.attempts += 1
            self?.lioSessionProblem = LioRequestProblem(RecoveryError.inactive, stage: .localRecord)
            throw RecoveryError.inactive
        }, invalidate: {})
    init(shell: ShellState) throws { self.shell = shell; store = try LioActivationFailurePersistence() }
}
@MainActor private struct LioRootActivationFailureFixture: View {
    let shell: ShellState
    @State private var root: LioActivationFailureRoot?
    @State private var setupFailed = false
    var body: some View {
        VStack {
            if let root {
                LioRootFailureView(shell: root.shell, root: root)
                Text(String(root.attempts)).accessibilityIdentifier("fixture.activation.attempts")
                Text(String(root.store.clears)).accessibilityIdentifier("fixture.activation.clears")
            } else if setupFailed {
                Text("Synthetic setup failed").accessibilityIdentifier("fixture.activation.setup-failure")
            } else { ProgressView() }
        }
        .task {
            guard root == nil && !setupFailed else { return }
            do {
                let ready = try LioActivationFailureRoot(shell: shell)
                root = ready
                ready.accounts.restore()
            } catch { setupFailed = true }
        }
    }
}
#endif
