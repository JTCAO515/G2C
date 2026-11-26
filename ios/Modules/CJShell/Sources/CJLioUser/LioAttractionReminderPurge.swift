import Foundation

/// The local notifications account deletion looks at: those waiting to fire and those already shown.
/// Reading is async (the system answers on its own queue); removing is a request the system applies itself.
public protocol LioReminderNotifications: Sendable {
    func pendingIDs() async -> Set<String>
    func deliveredIDs() async -> Set<String>
    func removePending(_ ids: [String])
    func removeDelivered(_ ids: [String])
}

/// What the notification centre held when it was last read, before the synchronous cleanup steps run.
public struct LioReminderSnapshot: Equatable, Sendable {
    public let pending: Set<String>
    public let delivered: Set<String>

    public init(pending: Set<String>, delivered: Set<String>) { self.pending = pending; self.delivered = delivered }

    /// This account's sight booking reminders still in either list.
    public func residue(of scope: LioAttractionReminderScope) -> Set<String> {
        pending.union(delivered).filter(scope.owns)
    }

    /// The same lists once this account's sight booking reminders are removed; every other notification as it was,
    /// including another account's sight booking reminders.
    public func withoutSightReminders(of scope: LioAttractionReminderScope) -> Self {
        Self(pending: pending.filter { !scope.owns($0) }, delivered: delivered.filter { !scope.owns($0) })
    }
}

/// Account deletion removes the sight booking reminders this account set (#1689, per account since #1922), waiting
/// and already shown. Only identifiers that start with the account's own prefix (`g2c.attraction.<account>.`) are
/// touched: another account's sight booking reminders, other notifications, and reminders set before #1922 (their
/// identifier carries no account, so none can be told to be this one's) stay. Only `account_cleanup` runs it:
/// switching accounts or a session found invalid keeps the reminders.
///
/// The device cleanup steps are synchronous and run on the main actor, so the lists are read asynchronously
/// beforehand (`read`) and the steps work from that snapshot; nothing waits on the main thread. A missing snapshot
/// fails the step, which the cleanup records as unknown and retries.
public enum LioAttractionReminderPurge {
    public static func applies(to cleanupReason: String) -> Bool { cleanupReason == "account_cleanup" }

    public static func read(_ center: any LioReminderNotifications) async -> LioReminderSnapshot {
        async let pending = center.pendingIDs()
        async let delivered = center.deliveredIDs()
        return await LioReminderSnapshot(pending: pending, delivered: delivered)
    }

    /// Removes this account's sight booking reminders the snapshot found, from both lists. Running it again on a
    /// fresh snapshot finds nothing and removes nothing.
    public static func erase(_ snapshot: LioReminderSnapshot?, of scope: LioAttractionReminderScope,
                             in center: any LioReminderNotifications) throws {
        guard let snapshot else { throw Failure.unavailable }
        let pending = snapshot.pending.filter(scope.owns).sorted()
        let delivered = snapshot.delivered.filter(scope.owns).sorted()
        if !pending.isEmpty { center.removePending(pending) }
        if !delivered.isEmpty { center.removeDelivered(delivered) }
    }

    /// Passes only when a snapshot was read and neither list holds one of this account's sight booking reminders.
    public static func requireAbsent(_ snapshot: LioReminderSnapshot?, of scope: LioAttractionReminderScope) throws {
        guard let snapshot else { throw Failure.unavailable }
        guard snapshot.residue(of: scope).isEmpty else { throw Failure.stillPresent }
    }

    /// The whole step for an async caller: read, remove, read again and check both lists.
    public static func purge(of scope: LioAttractionReminderScope, in center: any LioReminderNotifications) async throws {
        try erase(await read(center), of: scope, in: center)
        try requireAbsent(await read(center), of: scope)
    }

    public enum Failure: Error, Equatable { case stillPresent, unavailable }
}

#if canImport(UserNotifications)
import UserNotifications

/// The system notification centre's async lists; no waiting on the caller's thread.
public struct LioSystemReminderNotifications: LioReminderNotifications {
    public init() {}

    public func pendingIDs() async -> Set<String> {
        Set(await UNUserNotificationCenter.current().pendingNotificationRequests().map(\.identifier))
    }

    public func deliveredIDs() async -> Set<String> {
        Set(await UNUserNotificationCenter.current().deliveredNotifications().map(\.request.identifier))
    }

    public func removePending(_ ids: [String]) {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ids)
    }

    public func removeDelivered(_ ids: [String]) {
        UNUserNotificationCenter.current().removeDeliveredNotifications(withIdentifiers: ids)
    }
}
#endif
