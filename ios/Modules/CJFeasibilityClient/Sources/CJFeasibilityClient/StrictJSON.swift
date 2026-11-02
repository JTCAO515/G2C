import CJStrictJSON

enum FeasibilityJSONPolicy: StrictJSONPolicy {
    static var failure: FeasibilityFailure { .invalidResponse }
    static var maximumDepth: Int { 32 }
}
typealias StrictFeasibilityJSON = StrictJSONReader<FeasibilityJSONPolicy>
