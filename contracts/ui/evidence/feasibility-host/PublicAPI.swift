import CJShell
import CJFeasibilityClient
import CJSession

@MainActor func ordinaryHost(_ host: NeedsContainerHost, session: SessionLifecycle) {
    _ = host.openFeasibility(context: host.captureAction())
    if let entry = host.feasibilityPresentation {
        _ = entry.binding.acceptedRevision
        _ = entry.binding.acceptedContentSHA256
        _ = entry.model.state
        host.dismissFeasibility(id: entry.id)
    }
    _ = FeasibilityModel(session: session, currentBinding: { nil })
}
