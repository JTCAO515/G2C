import Foundation

/// UI state supplied by the authenticated composition. It grants no service
/// authority; each supplied client still enforces its original owner and lease.
public struct LioSessionAvailability: Equatable, Sendable {
    public let revision: UUID
    public let available: Bool
    public let showsRetry: Bool
    public let problem: LioRequestProblem?

    public init(revision: UUID, available: Bool, showsRetry: Bool = false, problem: LioRequestProblem? = nil) {
        self.revision = revision
        self.available = available
        self.showsRetry = showsRetry
        self.problem = problem
    }
}
