import CJStrictJSON

enum RunJSONPolicy: StrictJSONPolicy {
    static var failure: RunDisplayFailure { .invalidResponse }
}
typealias StrictRunJSON = StrictJSONReader<RunJSONPolicy>
