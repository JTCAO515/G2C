import CJStrictJSON

enum FeedbackJSONPolicy: StrictJSONPolicy {
    static var failure: FeedbackFailure { .invalidResponse }
}
typealias StrictFeedbackJSON = StrictJSONReader<FeedbackJSONPolicy>
