// Adapted from fixed base CJMessageHTTP duplicate-key validator. No wire schema.
import Foundation

/// Token-preserving JSON for strict consumer boundaries. Decimal data stays text;
/// JSON integers cannot silently become a rounded Double or accept 1.0/true.
indirect enum TripJSONValue {
    case object([String: TripJSONValue]), array([TripJSONValue]), string(String)
    case number(String), boolean(Bool), null
}

struct StrictTripJSON {
    var bytes: [UInt8]
    var index = 0
    private(set) var rootMemberRanges: [String:Range<Int>] = [:]
    mutating func check() throws {
        _ = try document()
    }
    mutating func document() throws -> TripJSONValue {
        // Foundation may auto-detect UTF-16/32, while this token parser is UTF-8.
        // Raw NUL is never legal JSON UTF-8, including inside string literals.
        guard !bytes.contains(0),String(bytes:bytes,encoding:.utf8) != nil else { throw TripFailure.invalidResponse }
        _ = try JSONSerialization.jsonObject(with: Data(bytes))
        let result = try value(depth: 0)
        whitespace()
        guard index == bytes.count else { throw TripFailure.invalidResponse }
        return result
    }
    mutating func whitespace() { while index < bytes.count && [9,10,13,32].contains(bytes[index]) { index += 1 } }
    mutating func string() throws -> String {
        let start = index; index += 1
        while index < bytes.count {
            if bytes[index] == 92 { index += 2; continue }
            if bytes[index] == 34 {
                index += 1
                return try JSONDecoder().decode(String.self, from: Data(bytes[start..<index]))
            }
            index += 1
        }
        throw TripFailure.invalidResponse
    }
    mutating func value(depth: Int) throws -> TripJSONValue {
        guard depth < 64 else { throw TripFailure.invalidResponse }
        whitespace()
        guard index < bytes.count else { throw TripFailure.invalidResponse }
        switch bytes[index] {
        case 123:
            index += 1; whitespace(); var fields: [String: TripJSONValue] = [:]
            if bytes[index] == 125 { index += 1; return .object(fields) }
            while true {
                whitespace(); let key = try string()
                guard fields[key] == nil else { throw TripFailure.invalidResponse }
                whitespace(); index += 1 // colon: grammar already validated
                whitespace();let start = index
                fields[key] = try value(depth: depth + 1)
                if depth == 0 { rootMemberRanges[key] = start..<index }
                whitespace()
                if bytes[index] == 125 { index += 1; break }
                index += 1
            }
            return .object(fields)
        case 91:
            index += 1; whitespace(); var elements: [TripJSONValue] = []
            if bytes[index] == 93 { index += 1; return .array(elements) }
            while true {
                elements.append(try value(depth: depth + 1)); whitespace()
                if bytes[index] == 93 { index += 1; break }
                index += 1
            }
            return .array(elements)
        case 34: return .string(try string())
        default:
            let start = index
            while index < bytes.count && ![9,10,13,32,44,93,125].contains(bytes[index]) { index += 1 }
            let token = String(decoding: bytes[start..<index], as: UTF8.self)
            switch token {
            case "true": return .boolean(true)
            case "false": return .boolean(false)
            case "null": return .null
            default: return .number(token)
            }
        }
    }
}
