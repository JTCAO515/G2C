import Foundation

/// Strict codec for canonical required-null fields the pinned generator cannot
/// represent directly. A missing field or any non-null value is never absence.
public struct ExplicitJSONNull: Codable, Hashable, Sendable {
    public init() { }
    public init(from decoder: any Decoder) throws {
        let container=try decoder.singleValueContainer()
        guard container.decodeNil() else {
            throw DecodingError.dataCorruptedError(in:container,debugDescription:"Expected explicit JSON null")
        }
    }
    public func encode(to encoder: any Encoder) throws {
        var container=encoder.singleValueContainer();try container.encodeNil()
    }
}
