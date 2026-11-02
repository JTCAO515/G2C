import CJStrictJSON

enum CleanupJSONPolicy: StrictJSONPolicy {
    static var failure: CleanupFailure { .invalidResponse }
    static var requiresObjectRoot: Bool { true }
}
typealias StrictCleanupJSON = StrictJSONReader<CleanupJSONPolicy>
