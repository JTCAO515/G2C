import Foundation

/// Explicit synthetic/product policy input. This evaluator does not grant offline authorization.
public struct OfflinePolicy: Sendable {
    public let maximumAge: Int64
    public init(maximumAge: Int64) { self.maximumAge = maximumAge }
}
public struct OfflineClock: Sendable {
    public let trustedWallSeconds: Int64?
    public let boot: UUID
    public let uptime: Double
    public init(trustedWallSeconds: Int64?, boot: UUID, uptime: Double) {
        self.trustedWallSeconds = trustedWallSeconds; self.boot = boot; self.uptime = uptime
    }
}
public enum OfflineValidity: Equatable, Sendable {
    case readable(version: Int64, syncedAt: Int64, deadline: Int64)
    case stale
    case unavailable
}
public enum OfflineValidityEvaluator {
    /// Trusted clock/last-observed time must come from host authority, not from editable cache.
    public static func evaluate(_ snapshot: OfflineSnapshot, active: OfflineNamespace?, policy: OfflinePolicy?,
                                clock: OfflineClock, lastTrustedWall: Int64?, minimumVersion: Int64,
                                sessionAllowsOffline: Bool) -> OfflineValidity {
        let m = snapshot.metadata
        guard sessionAllowsOffline, active == m.namespace, let policy, policy.maximumAge > 0,
              let now = clock.trustedWallSeconds, let last = lastTrustedWall,
              now >= last, now >= m.syncedAt, minimumVersion > 0, m.version >= minimumVersion,
              clock.uptime.isFinite, clock.uptime >= 0 else { return .unavailable }
        let (limit, overflow) = m.syncedAt.addingReportingOverflow(policy.maximumAge)
        guard !overflow else { return .unavailable }
        let deadline = min(m.deadline, limit)
        if clock.boot == m.boot {
            guard clock.uptime >= m.uptimeAtSync else { return .unavailable }
            let elapsed = clock.uptime - m.uptimeAtSync
            guard elapsed < Double(deadline - m.syncedAt) else { return .stale }
        }
        // A reboot has no comparable monotonic clock. A fresh trusted wall input is mandatory.
        guard now < deadline else { return .stale }
        return .readable(version: m.version, syncedAt: m.syncedAt, deadline: deadline)
    }
}
