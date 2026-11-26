import Foundation
import Testing
@testable import CJLioUser

/// One fake notification centre that both the scheduler (setting reminders) and account deletion (reading and
/// removing them) work on, as the system centre is on a real phone.
final class SharedFakeNotificationCenter: LioAttractionReminderCenter, LioReminderNotifications, @unchecked Sendable {
    private let lock = NSLock()
    private var _pending: Set<String>
    private var _delivered: Set<String>
    private let failsToAdd: Bool
    private let granted: Bool
    init(pending: Set<String> = [], delivered: Set<String> = [], granted: Bool = true, failsToAdd: Bool = false) {
        (_pending, _delivered, self.granted, self.failsToAdd) = (pending, delivered, granted, failsToAdd)
    }
    var pending: Set<String> { lock.withLock { _pending } }
    var delivered: Set<String> { lock.withLock { _delivered } }
    /// A reminder going off: it moves from waiting to shown.
    func fire(_ id: String) { lock.withLock { if _pending.remove(id) != nil { _delivered.insert(id) } } }

    struct AddFailed: Error {}
    func requestAuthorization() async -> Bool { granted }
    func add(_ request: LioAttractionReminder.Request) async throws {
        if failsToAdd { throw AddFailed() }
        lock.withLock { _ = _pending.insert(request.id) }
    }
    func pendingIDs() async -> Set<String> { pending }
    func deliveredIDs() async -> Set<String> { delivered }
    func remove(_ id: String) async { lock.withLock { _ = _pending.remove(id) } }
    func removePending(_ ids: [String]) { lock.withLock { _pending.subtract(ids) } }
    func removeDelivered(_ ids: [String]) { lock.withLock { _delivered.subtract(ids) } }
}

/// #1922: sight booking reminders belong to the account that set them; account deletion removes only its own.
struct LioAttractionReminderAccountTests {
    private let accountA = "6F1B0C52-4F2E-4C58-9E57-0C1B8E6A7D01"
    private let accountB = "0B8E4D77-91A3-4E0C-8D62-3A5F7C19E2B4"
    private var scopeA: LioAttractionReminderScope { .init(account: accountA) }
    private var scopeB: LioAttractionReminderScope { .init(account: accountB) }
    private let calendar = LioAttractionBookingRule.calendar

    private func beijing(_ y: Int, _ m: Int, _ d: Int) -> Date {
        calendar.date(from: DateComponents(year: y, month: m, day: d))!
    }
    private let now = LioAttractionBookingRule.day("2026-11-25")!
    private var palace: LioAttractionBookingRule { LioAttractionBookingRule.all.first { $0.id == "beijing.palace-museum" }! }
    private var museum: LioAttractionBookingRule { LioAttractionBookingRule.all.first { $0.id == "beijing.national-museum" }! }

    private func scheduler(_ center: SharedFakeNotificationCenter, _ scope: LioAttractionReminderScope) -> LioAttractionReminderScheduler {
        LioAttractionReminderScheduler(center: center, scope: scope)
    }

    @discardableResult
    private func set(_ rule: LioAttractionBookingRule, on visit: Date, with scheduler: LioAttractionReminderScheduler) async throws
        -> LioAttractionReminder.Request {
        let request = try #require(scheduler.request(for: rule, visit: visit, now: now.addingTimeInterval(9 * 3600), language: .english))
        #expect(try await scheduler.schedule(request) == .scheduled)
        return request
    }

    // MARK: - The identifier

    /// L0: the account part is 16 lowercase hex characters, stable for an account, different between accounts, and
    /// holds nothing from the account id.
    @Test func theAccountSegmentIsAShortOneWayHash() throws {
        let segment = scopeA.segment
        #expect(segment.count == 16)
        #expect(segment.allSatisfy { "0123456789abcdef".contains($0) })
        #expect(LioAttractionReminderScope(account: accountA).segment == segment, "stable")
        #expect(LioAttractionReminderScope(account: accountA.lowercased()).segment == segment, "case of the id does not matter")
        #expect(scopeB.segment != segment)
        #expect(scopeA.prefix == "g2c.attraction.\(segment).")
        // Nothing of the account id, whole or in part, is in the identifier.
        let request = try #require(LioAttractionReminder.request(for: palace, visit: beijing(2026, 12, 5), now: now, language: .english,
                                                                 scope: scopeA))
        let id = request.id.lowercased()
        for piece in [accountA, accountA.replacingOccurrences(of: "-", with: "")] + accountA.split(separator: "-").map(String.init) {
            #expect(!id.contains(piece.lowercased()), "\(piece)")
        }
        #expect(request.id == "g2c.attraction.\(segment).beijing.palace-museum.2026-12-05")
        // The title and body (what the notification shows) carry no account either.
        #expect(!(request.title + request.body).lowercased().contains(segment))
    }

    @Test func noAccountGivesTheSharedSegmentThatNoDeletionTargets() {
        #expect(LioAttractionReminderScope(account: nil) == LioAttractionReminderScope(account: ""))
        #expect(LioAttractionReminderScope(account: nil).segment != scopeA.segment)
        #expect(LioAttractionReminderScope(account: nil).segment.count == 16)
    }

    /// The reader tells an account segment from a pre-#1922 rule id by its shape, so no rule id may look like one.
    @Test func noRuleIDStartsLikeAnAccountSegment() {
        for rule in LioAttractionBookingRule.all {
            let first = rule.id.split(separator: ".", maxSplits: 1).first ?? ""
            #expect(!LioAttractionReminderScope.isSegment(first), "\(rule.id)")
        }
    }

    @Test func itemsReadBackTheirAccountAndOldOnesHaveNone() throws {
        let current = try #require(LioAttractionReminderItem(id: scopeA.prefix + "beijing.palace-museum.2026-12-05"))
        #expect(current.account == scopeA.segment && current.ruleID == "beijing.palace-museum")
        #expect(current.legacyID == "g2c.attraction.beijing.palace-museum.2026-12-05")
        let old = try #require(LioAttractionReminderItem(id: "g2c.attraction.beijing.palace-museum.2026-12-05"))
        #expect(old.account == nil && old.ruleID == "beijing.palace-museum")
        #expect(LioAttractionReminderItem(id: scopeA.prefix + "2026-12-05") == nil, "an account but no sight")
    }

    // MARK: - Two accounts on one phone

    /// L0 (acceptance 1): both accounts set reminders; A deletes; B's, waiting and shown, are still there.
    @Test func deletingOneAccountKeepsTheOthersReminders() async throws {
        let center = SharedFakeNotificationCenter(pending: ["medication.9am"], delivered: ["medication.8am"])
        let a = scheduler(center, scopeA), b = scheduler(center, scopeB)
        let aPalace = try await set(palace, on: beijing(2026, 12, 5), with: a)
        let aMuseum = try await set(museum, on: beijing(2026, 12, 6), with: a)
        let bPalace = try await set(palace, on: beijing(2026, 12, 5), with: b)   // the same sight and day
        let bMuseum = try await set(museum, on: beijing(2026, 12, 7), with: b)
        #expect(Set([aPalace.id, aMuseum.id, bPalace.id, bMuseum.id]).count == 4, "one identifier per account, sight and day")
        center.fire(aMuseum.id)
        center.fire(bMuseum.id)    // one of each account's has already been shown

        try await LioAttractionReminderPurge.purge(of: scopeA, in: center)

        #expect(center.pending == ["medication.9am", bPalace.id])
        #expect(center.delivered == ["medication.8am", bMuseum.id])
        #expect(await b.scheduled().map(\.id) == [bPalace.id], "the shown one is no longer waiting")
        #expect(await a.scheduled().isEmpty)
        #expect(await b.isScheduled(bPalace.id))
        // Re-entrant: running the deletion again removes nothing of B's and still verifies.
        try await LioAttractionReminderPurge.purge(of: scopeA, in: center)
        #expect(center.pending == ["medication.9am", bPalace.id])
        #expect(center.delivered == ["medication.8am", bMuseum.id])
    }

    @Test func eachAccountOnlySeesItsOwnReminders() async throws {
        let center = SharedFakeNotificationCenter()
        let a = scheduler(center, scopeA), b = scheduler(center, scopeB)
        let aRequest = try await set(palace, on: beijing(2026, 12, 5), with: a)
        let bRequest = try await set(museum, on: beijing(2026, 12, 6), with: b)
        #expect(await a.scheduled().map(\.id) == [aRequest.id])
        #expect(await b.scheduled().map(\.id) == [bRequest.id])
        // Setting B's reminder for A's sight and day does not touch A's.
        let again = try await set(palace, on: beijing(2026, 12, 5), with: b)
        #expect(again.id != aRequest.id)
        #expect(center.pending.contains(aRequest.id))
    }

    /// The snapshot steps the deletion runs from see only the deleted account's reminders as residue.
    @Test func theSnapshotTreatsOnlyTheDeletedAccountsRemindersAsResidue() {
        let aID = scopeA.prefix + "beijing.palace-museum.2026-12-05", bID = scopeB.prefix + "beijing.palace-museum.2026-12-05"
        let snapshot = LioReminderSnapshot(pending: [aID, bID], delivered: [bID])
        #expect(snapshot.residue(of: scopeA) == [aID])
        #expect(snapshot.withoutSightReminders(of: scopeA) == LioReminderSnapshot(pending: [bID], delivered: [bID]))
        #expect(throws: Never.self) { try LioAttractionReminderPurge.requireAbsent(snapshot.withoutSightReminders(of: scopeA), of: scopeA) }
        #expect(throws: LioAttractionReminderPurge.Failure.stillPresent) { try LioAttractionReminderPurge.requireAbsent(snapshot, of: scopeA) }
    }

    // MARK: - Only account deletion

    /// L0: switching accounts or a session found invalid removes nothing (the host runs the purge only when
    /// `applies(to:)` says so); neither account's reminders change.
    @Test func switchingAccountsOrAnInvalidSessionKeepsEveryReminder() async throws {
        let center = SharedFakeNotificationCenter()
        let a = scheduler(center, scopeA), b = scheduler(center, scopeB)
        try await set(palace, on: beijing(2026, 12, 5), with: a)
        try await set(museum, on: beijing(2026, 12, 6), with: b)
        let before = (center.pending, center.delivered)
        for reason in ["session_invalid", "offline_expired", "account_switch", ""] {
            #expect(!LioAttractionReminderPurge.applies(to: reason), "\(reason)")
            if LioAttractionReminderPurge.applies(to: reason) { try await LioAttractionReminderPurge.purge(of: scopeA, in: center) }
        }
        #expect(center.pending == before.0 && center.delivered == before.1)
        #expect(LioAttractionReminderPurge.applies(to: "account_cleanup"))
    }

    // MARK: - Look-alike prefixes

    /// L0: only `g2c.attraction.<this account>.` is removed; look-alikes stay.
    @Test func lookAlikePrefixesAreNotRemoved() async throws {
        let mine = scopeA.prefix + "beijing.palace-museum.2026-12-05"
        let lookAlikes: Set<String> = [
            "g2c.attractionx." + scopeA.segment + ".beijing.palace-museum.2026-12-05",   // another feature's prefix
            "g2c.attractionx.1",
            "g2c.attraction." + scopeA.segment + "x.beijing.palace-museum.2026-12-05",   // segment run on
            "g2c.attraction." + scopeA.segment,                                          // no dot after the segment
            "g2c.attraction" + scopeA.segment + ".beijing.palace-museum.2026-12-05",     // no dot before it
            "xg2c.attraction." + scopeA.segment + ".beijing.palace-museum.2026-12-05",
            "G2C.ATTRACTION." + scopeA.segment + ".beijing.palace-museum.2026-12-05",
            "g2c.attraction." + String(scopeA.segment.dropLast()) + ".beijing.palace-museum.2026-12-05",   // 15 characters
        ]
        let center = SharedFakeNotificationCenter(pending: lookAlikes.union([mine]), delivered: lookAlikes.union([mine]))
        try await LioAttractionReminderPurge.purge(of: scopeA, in: center)
        #expect(center.pending == lookAlikes)
        #expect(center.delivered == lookAlikes)
    }

    // MARK: - Reminders set before #1922

    private let legacyPalace = "g2c.attraction.beijing.palace-museum.2026-12-05"
    private let legacyMuseum = "g2c.attraction.beijing.national-museum.2026-12-06"

    /// L0: a reminder in the old shape (no account segment) cannot be told to be anybody's, so account deletion
    /// leaves it, waiting or shown; the account's own reminders are removed as usual.
    @Test func accountDeletionLeavesRemindersInTheOldShape() async throws {
        let center = SharedFakeNotificationCenter(pending: [legacyPalace], delivered: [legacyMuseum])
        let a = scheduler(center, scopeA)
        let own = try await set(palace, on: beijing(2026, 12, 7), with: a)
        try await LioAttractionReminderPurge.purge(of: scopeA, in: center)
        #expect(!center.pending.contains(own.id))
        #expect(center.pending == [legacyPalace])
        #expect(center.delivered == [legacyMuseum])
        // Not an account's residue: the deletion still verifies.
        try LioAttractionReminderPurge.requireAbsent(await LioAttractionReminderPurge.read(center), of: scopeA)
    }

    /// L0: an old-shape reminder is not listed for any account (the trip home does not count it as set) ...
    @Test func anOldShapeReminderIsNotListedAsSetForAnAccount() async throws {
        let center = SharedFakeNotificationCenter(pending: [legacyPalace])
        #expect(await scheduler(center, scopeA).scheduled().isEmpty)
        #expect(await scheduler(center, scopeB).scheduled().isEmpty)
        let request = try #require(scheduler(center, scopeA).request(for: palace, visit: beijing(2026, 12, 5), now: now, language: .english))
        #expect(await !scheduler(center, scopeA).isScheduled(request.id))
    }

    /// L0: ... and setting the same sight and day again rebuilds it in the account's shape: the new one is added and
    /// the old one removed, so it does not fire twice. Other old-shape reminders stay.
    @Test func settingTheSameReminderAgainRebuildsAnOldShapeOne() async throws {
        let center = SharedFakeNotificationCenter(pending: [legacyPalace, legacyMuseum])
        let a = scheduler(center, scopeA)
        let rebuilt = try await set(palace, on: beijing(2026, 12, 5), with: a)
        #expect(rebuilt.id == scopeA.prefix + "beijing.palace-museum.2026-12-05")
        #expect(center.pending == [rebuilt.id, legacyMuseum], "the old one for this sight and day is gone, the other stays")
        #expect(await a.scheduled().map(\.id) == [rebuilt.id])
        // From then on it is the account's: deletion removes it, and the remaining old-shape one stays.
        try await LioAttractionReminderPurge.purge(of: scopeA, in: center)
        #expect(center.pending == [legacyMuseum])
    }

    /// Nothing is removed when the reminder cannot be set: no permission, or the system refuses the add.
    @Test func anOldShapeReminderStaysWhenTheNewOneCannotBeSet() async throws {
        let denied = SharedFakeNotificationCenter(pending: [legacyPalace], granted: false)
        let request = try #require(scheduler(denied, scopeA).request(for: palace, visit: beijing(2026, 12, 5), now: now, language: .english))
        #expect(try await scheduler(denied, scopeA).schedule(request) == .notAllowed)
        #expect(denied.pending == [legacyPalace])

        let failing = SharedFakeNotificationCenter(pending: [legacyPalace], failsToAdd: true)
        await #expect(throws: SharedFakeNotificationCenter.AddFailed.self) { try await scheduler(failing, scopeA).schedule(request) }
        #expect(failing.pending == [legacyPalace])
    }
}
