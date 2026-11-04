import CJMessageClient

enum MemoryJournalPolicy: LocalJournalCleanupPolicy {
    static var unavailable: MemoryFailure { .storageUnavailable }
    static var outcomeUnknown: MemoryFailure { .exchangeUnknown }
    static var recordExtension: String { "memory" }
    static var acceptsUUIDStem: Bool { true }
}
typealias MemoryLocalJournalCleanup = LocalJournalCleanup<MemoryJournalPolicy>
