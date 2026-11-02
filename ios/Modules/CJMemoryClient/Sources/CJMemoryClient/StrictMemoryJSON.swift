import CJStrictJSON

enum MemoryJSONPolicy: StrictJSONPolicy {
    static var failure: MemoryFailure { .invalidResponse }
}
typealias StrictMemoryJSON = StrictJSONReader<MemoryJSONPolicy>
