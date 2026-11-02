import CJStrictJSON
import Foundation

/// Reuse the existing duplicate-key/token boundary for non-HTTP original RUN
/// consumers. Returned paths identify lexical JSON unsigned integers, not
/// rounded Foundation numbers. This grants no source or write authority.
@discardableResult public func validateUnambiguousJSON(_ data: Data) throws -> [[String]: Int64] {
    var checker = StrictJSON(bytes: Array(data))
    try checker.check()
    return checker.memberUnsignedIntegers
}

enum MessageJSONPolicy: StrictJSONPolicy {
    static var failure: MessageHTTPFailure { .invalidResponse }
}
typealias StrictJSON = StrictJSONReader<MessageJSONPolicy>
