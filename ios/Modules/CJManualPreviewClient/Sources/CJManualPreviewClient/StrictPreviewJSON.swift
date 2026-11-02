import CJStrictJSON

enum PreviewJSONPolicy: StrictJSONPolicy {
    static var failure: PreviewFailure { .invalidResponse }
    static var allowsFragments: Bool { true }
}
typealias StrictPreviewJSON = StrictJSONReader<PreviewJSONPolicy>
