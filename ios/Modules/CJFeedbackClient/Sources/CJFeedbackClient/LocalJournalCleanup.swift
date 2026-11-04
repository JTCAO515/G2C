import CJMessageClient

enum FeedbackJournalPolicy: LocalJournalCleanupPolicy {
    static var unavailable: FeedbackFailure { .storageUnavailable }
    static var outcomeUnknown: FeedbackFailure { .exchangeUnknown }
    static var recordExtension: String { "feedback" }
}
typealias FeedbackLocalJournalCleanup = LocalJournalCleanup<FeedbackJournalPolicy>
