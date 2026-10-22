// Derived from canonical CJMessageHTTP StrictResponse.swift at e450e38; generic JSON grammar only.
import Foundation

/// Generic JSON duplicate-key check; wire shapes remain exclusively in generated CJAPI.
struct StrictUsageJSON {
    var bytes: [UInt8]
    var index = 0
    mutating func check() throws {
        _ = try JSONSerialization.jsonObject(with: Data(bytes))
        try value(depth: 0)
        whitespace()
        guard index == bytes.count else { throw UsageFailure.invalidResponse }
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
        throw UsageFailure.invalidResponse
    }
    mutating func value(depth: Int) throws {
        guard depth < 64 else { throw UsageFailure.invalidResponse }
        whitespace()
        guard index < bytes.count else { throw UsageFailure.invalidResponse }
        switch bytes[index] {
        case 123:
            index += 1; whitespace(); var keys = Set<String>()
            if bytes[index] == 125 { index += 1; return }
            while true {
                whitespace(); let key = try string()
                guard keys.insert(key).inserted else { throw UsageFailure.invalidResponse }
                whitespace(); index += 1 // colon: grammar already validated
                try value(depth: depth + 1); whitespace()
                if bytes[index] == 125 { index += 1; break }
                index += 1
            }
        case 91:
            index += 1; whitespace()
            if bytes[index] == 93 { index += 1; return }
            while true {
                try value(depth: depth + 1); whitespace()
                if bytes[index] == 93 { index += 1; break }
                index += 1
            }
        case 34: _ = try string()
        default:
            while index < bytes.count && ![9,10,13,32,44,93,125].contains(bytes[index]) { index += 1 }
        }
    }
}
