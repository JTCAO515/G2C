import Foundation

/// The silent check for a memory choice still waiting to be saved, run when the chat comes back to the
/// foreground (#1450). Backgrounding retires the account's journal lease, so the check waits until the
/// session is ready again; a failure is recorded for diagnosis and never shown to the traveller.
enum LioMemoryResumeCheck {
    /// `nil` when nothing should change on screen.
    @MainActor
    static func pendingChoice(sessionReady: Bool, check: () throws -> Bool, failed: (Error) -> Void) -> Bool? {
        guard sessionReady else { return nil }
        do {
            return try check()
        } catch {
            failed(error)
            return nil
        }
    }
}
