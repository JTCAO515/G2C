import CJMessageClient

enum NeedsJournalPolicy: LocalJournalCleanupPolicy {
    static var unavailable: NeedsFailure { .storageUnavailable }
    static var outcomeUnknown: NeedsFailure { .exchangeUnknown }
    static var recordExtension: String { "needs" }
}
typealias NeedsLocalJournalCleanup = LocalJournalCleanup<NeedsJournalPolicy>
