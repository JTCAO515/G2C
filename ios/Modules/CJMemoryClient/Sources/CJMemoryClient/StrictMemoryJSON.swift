// Adapted from the accepted CJMessageHTTP private duplicate-key validator.
import Foundation

/// Duplicate-key and integer-token boundary check. Generated CJAPI supplies wire
/// types; typed domains also enforce frozen conditional constraints it cannot express.
struct StrictMemoryJSON {
    var bytes: [UInt8]
    var index = 0
    private(set) var unsignedIntegers: [[String]: Int64] = [:]
    mutating func check() throws {
        _ = try JSONSerialization.jsonObject(with: Data(bytes))
        try value(depth: 0)
        whitespace()
        guard index == bytes.count else { throw MemoryFailure.invalidResponse }
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
        throw MemoryFailure.invalidResponse
    }
    mutating func value(depth: Int, path: [String] = []) throws {
        guard depth < 64 else { throw MemoryFailure.invalidResponse }
        whitespace()
        guard index < bytes.count else { throw MemoryFailure.invalidResponse }
        switch bytes[index] {
        case 123:
            index += 1; whitespace(); var keys = Set<String>()
            if bytes[index] == 125 { index += 1; return }
            while true {
                whitespace(); let key = try string()
                guard keys.insert(key).inserted else { throw MemoryFailure.invalidResponse }
                whitespace(); index += 1 // colon: grammar already validated
                try value(depth: depth + 1, path: path + [key]); whitespace()
                if bytes[index] == 125 { index += 1; break }
                index += 1
            }
        case 91:
            index += 1; whitespace()
            if bytes[index] == 93 { index += 1; return }
            var element = 0
            while true {
                try value(depth: depth + 1, path: path + [String(element)]); element += 1; whitespace()
                if bytes[index] == 93 { index += 1; break }
                index += 1
            }
        case 34: _ = try string()
        default:
            let start = index
            while index < bytes.count && ![9,10,13,32,44,93,125].contains(bytes[index]) { index += 1 }
            let token = bytes[start..<index]
            if !token.isEmpty, token.allSatisfy({ (48...57).contains($0) }),
               let integer = Int64(String(decoding: token, as: UTF8.self)) {
                unsignedIntegers[path] = integer
            }
        }
    }
}
