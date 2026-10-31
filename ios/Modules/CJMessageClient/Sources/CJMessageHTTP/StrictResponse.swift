import Foundation

/// Reuse the existing duplicate-key/token boundary for non-HTTP original RUN
/// consumers. Returned paths identify lexical JSON unsigned integers, not
/// rounded Foundation numbers. This grants no source or write authority.
@discardableResult public func validateUnambiguousJSON(_ data: Data) throws -> [[String]: Int64] {
    guard !data.contains(0), String(data: data, encoding: .utf8) != nil else {
        throw MessageHTTPFailure.invalidResponse
    }
    var checker = StrictJSON(bytes: Array(data))
    try checker.check()
    return checker.memberUnsignedIntegers
}

/// Generic JSON duplicate-key check; wire shapes remain exclusively in generated CJAPI.
struct StrictJSON {
    var bytes: [UInt8]
    var index = 0
    var topLevelUnsignedIntegers: [String: Int64] = [:]
    var memberUnsignedIntegers: [[String]: Int64] = [:]
    mutating func check() throws {
        _ = try JSONSerialization.jsonObject(with: Data(bytes))
        try value(depth: 0)
        whitespace()
        guard index == bytes.count else { throw MessageHTTPFailure.invalidResponse }
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
        throw MessageHTTPFailure.invalidResponse
    }
    mutating func value(depth: Int, path: [String] = []) throws {
        guard depth < 64 else { throw MessageHTTPFailure.invalidResponse }
        whitespace()
        guard index < bytes.count else { throw MessageHTTPFailure.invalidResponse }
        switch bytes[index] {
        case 123:
            index += 1; whitespace(); var keys = Set<String>()
            if bytes[index] == 125 { index += 1; return }
            while true {
                whitespace(); let key = try string()
                guard keys.insert(key).inserted else { throw MessageHTTPFailure.invalidResponse }
                whitespace(); index += 1 // colon: grammar already validated
                whitespace(); let start = index
                let memberPath = path + [key]
                try value(depth: depth + 1, path: memberPath)
                if bytes[start..<index].allSatisfy({ (48...57).contains($0) }),
                   let integer = Int64(String(decoding: bytes[start..<index], as: UTF8.self)) {
                    memberUnsignedIntegers[memberPath] = integer
                    if depth == 0 { topLevelUnsignedIntegers[key] = integer }
                }
                whitespace()
                if bytes[index] == 125 { index += 1; break }
                index += 1
            }
        case 91:
            index += 1; whitespace()
            if bytes[index] == 93 { index += 1; return }
            var element = 0
            while true {
                try value(depth: depth + 1, path: path + [String(element)]); whitespace()
                element += 1
                if bytes[index] == 93 { index += 1; break }
                index += 1
            }
        case 34: _ = try string()
        default:
            while index < bytes.count && ![9,10,13,32,44,93,125].contains(bytes[index]) { index += 1 }
        }
    }
}
