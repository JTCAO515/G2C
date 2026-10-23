import CJShell
import CJSession
import CJFeasibilityClient

// Public-import compile probe only; not executed or added as a product wrapper.
// The public model has no endpoint, credentials, transport or issuer argument.
@MainActor func composeClosedFeasibility(
    session: SessionLifecycle,
    current: @escaping @MainActor () -> FeasibilityBinding?
) -> FeasibilityModel {
    FeasibilityModel(session: session, currentBinding: current)
}

@MainActor func composeShell(_ state: ShellState) -> ShellView {
    ShellView(state: state)
}
