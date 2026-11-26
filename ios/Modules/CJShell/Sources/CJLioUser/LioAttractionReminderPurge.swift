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

    /// Sight booking reminders still in either list.
    public var residue: Set<String> {
        pending.union(delivered).filter { $0.hasPrefix(LioAttractionReminderPurge.prefix) }
    }

    /// The same lists once the sight booking reminders are removed; other notifications as they were.
    public var withoutSightReminders: Self {
        Self(pending: pending.filter { !$0.hasPrefix(LioAttractionReminderPurge.prefix) },
             delivered: delivered.filter { !$0.hasPrefix(LioAttractionReminderPurge.prefix) })
    }
}

/// Account deletion removes the sight booking reminders this app set (#1689), waiting and already shown. Only
/// identifiers with the sight booking prefix are touched; other notifications stay. Only `account_cleanup` runs it:
/// switching accounts or a session found invalid keeps the reminders.
///
/// The device cleanup steps are synchronous and run on the main actor, so the lists are read asynchronously
/// beforehand (`read`) and the steps work from that snapshot; nothing waits on the main thread. A missing snapshot
/// fails the step, which the cleanup records as unknown and retries.
public enum LioAttractionReminderPurge {
    /// Every sight booking reminder identifier starts with this (`g2c.attraction.<rule id>.<yyyy-MM-dd>`).
    public static var prefix: String { LioAttractionReminderItem.prefix }

    public static func applies(to cleanupReason: String) -> Bool { cleanupReason == "account_cleanup" }

    public static func read(_ center: any LioReminderNotifications) async -> LioReminderSnapshot {
        async let pending = center.pendingIDs()
        async let delivered = center.deliveredIDs()
        return await LioReminderSnapshot(pending: pending, delivered: delivered)
    }

    /// Removes the sight booking reminders the snapshot found, from both lists. Running it again on a fresh
    /// snapshot finds nothing and removes nothing.
    public static func erase(_ snapshot: LioReminderSnapshot?, in center: any LioReminderNotifications) throws {
        guard let snapshot else { throw Failure.unavailable }
        let pending = snapshot.pending.filter { $0.hasPrefix(prefix) }.sorted()
        let delivered = snapshot.delivered.filter { $0.hasPrefix(prefix) }.sorted()
        if !pending.isEmpty { center.removePending(pending) }
        if !delivered.isEmpty { center.removeDelivered(delivered) }
    }

    /// Passes only when a snapshot was read and neither list holds a sight booking reminder.
    public static func requireAbsent(_ snapshot: LioReminderSnapshot?) throws {
        guard let snapshot else { throw Failure.unavailable }
        guard snapshot.residue.isEmpty else { throw Failure.stillPresent }
    }

    /// The whole step for an async caller: read, remove, read again and check both lists.
    public static func purge(in center: any LioReminderNotifications) async throws {
        try erase(await read(center), in: center)
        try requireAbsent(await read(center))
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
