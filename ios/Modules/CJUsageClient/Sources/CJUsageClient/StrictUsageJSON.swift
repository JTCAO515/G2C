import CJStrictJSON

enum UsageJSONPolicy: StrictJSONPolicy {
    static var failure: UsageFailure { .invalidResponse }
}
typealias StrictUsageJSON = StrictJSONReader<UsageJSONPolicy>
