import Foundation

/// Token-preserving JSON for strict consumer boundaries. Decimal data stays text;
/// JSON integers cannot silently become a rounded Double or accept 1.0/true.
public indirect enum StrictJSONValue: Sendable {
    case object([String: StrictJSONValue]), array([StrictJSONValue]), string(String)
    case number(String), boolean(Bool), null
}

/// What one boundary may differ on. Wire shapes stay exclusively in generated CJAPI.
public protocol StrictJSONPolicy {
    associatedtype Failure: Error
    static var failure: Failure { get }
    static var maximumDepth: Int { get }
    static var requiresObjectRoot: Bool { get }
    static var allowsFragments: Bool { get }
    /// New consumers may retain numeric lexemes outside Foundation's numeric range.
    /// Domain readers must still enforce their own integer/finite quantity constraints.
    static var preservesUnboundedNumberTokens: Bool { get }
}

public extension StrictJSONPolicy {
    static var maximumDepth: Int { 64 }
    static var requiresObjectRoot: Bool { false }
    static var allowsFragments: Bool { false }
    static var preservesUnboundedNumberTokens: Bool { false }
}

/// Generic JSON grammar with a duplicate-key check Foundation does not perform.
public struct StrictJSONReader<Policy: StrictJSONPolicy> {
    private let bytes: [UInt8]
    private var index = 0
    public private(set) var rootMemberRanges: [String: Range<Int>] = [:]
    private var root: StrictJSONValue?

    public init(bytes: [UInt8]) { self.bytes = bytes }

    public mutating func check() throws { _ = try document() }

    public mutating func document() throws -> StrictJSONValue {
        // Foundation may auto-detect UTF-16/32, while this token parser is UTF-8.
        // Raw NUL is never legal JSON UTF-8, including inside string literals.
        guard !bytes.contains(0), String(bytes: bytes, encoding: .utf8) != nil else { throw Policy.failure }
        whitespace()
        if Policy.requiresObjectRoot {
            guard index < bytes.count, bytes[index] == 123 else { throw Policy.failure }
        }
        let grammarInput = Policy.preservesUnboundedNumberTokens ? try foundationGrammarInput() : Data(bytes)
        _ = try JSONSerialization.jsonObject(with: grammarInput, options: Policy.allowsFragments ? [.fragmentsAllowed] : [])
        let result = try value(depth: 0)
        whitespace()
        guard index == bytes.count else { throw Policy.failure }
        root = result
        return result
    }

    /// Foundation checks all structural/string syntax as before. Only strictly valid
    /// numeric lexemes are replaced in this private grammar probe; `value` still
    /// traverses the actual original bytes, retaining every token and byte range.
    private func foundationGrammarInput() throws -> Data {
        let number = try NSRegularExpression(pattern: #"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"#)
        var probe: [UInt8] = []
        probe.reserveCapacity(bytes.count)
        var cursor = 0
        while cursor < bytes.count {
            let byte = bytes[cursor]
            if byte == 34 {
                probe.append(byte); cursor += 1
                while cursor < bytes.count {
                    let part = bytes[cursor]
                    probe.append(part); cursor += 1
                    if part == 34 { break }
                    if part == 92, cursor < bytes.count {
                        probe.append(bytes[cursor]); cursor += 1
                    }
                }
            } else if byte == 45 || (48...57).contains(byte) {
                let start = cursor
                while cursor < bytes.count, ![9, 10, 13, 32, 44, 93, 125].contains(bytes[cursor]) { cursor += 1 }
                let token = String(decoding: bytes[start..<cursor], as: UTF8.self)
                let range = NSRange(location: 0, length: token.utf16.count)
                guard number.firstMatch(in: token, range: range)?.range == range else { throw Policy.failure }
                probe.append(48)
            } else {
                probe.append(byte); cursor += 1
            }
        }
        return Data(probe)
    }

    private mutating func whitespace() { while index < bytes.count && [9, 10, 13, 32].contains(bytes[index]) { index += 1 } }

    private mutating func string() throws -> String {
        let start = index; index += 1
        while index < bytes.count {
            if bytes[index] == 92 { index += 2; continue }
            if bytes[index] == 34 {
                index += 1
                return try JSONDecoder().decode(String.self, from: Data(bytes[start..<index]))
            }
            index += 1
        }
        throw Policy.failure
    }

    private mutating func value(depth: Int) throws -> StrictJSONValue {
        guard depth < Policy.maximumDepth else { throw Policy.failure }
        whitespace()
        guard index < bytes.count else { throw Policy.failure }
        switch bytes[index] {
        case 123:
            index += 1; whitespace(); var fields: [String: StrictJSONValue] = [:]
            if bytes[index] == 125 { index += 1; return .object(fields) }
            while true {
                whitespace(); let key = try string()
                guard fields[key] == nil else { throw Policy.failure }
                whitespace(); index += 1 // colon: grammar already validated
                whitespace(); let start = index
                fields[key] = try value(depth: depth + 1)
                if depth == 0 { rootMemberRanges[key] = start..<index }
                whitespace()
                if bytes[index] == 125 { index += 1; break }
                index += 1
            }
            return .object(fields)
        case 91:
            index += 1; whitespace(); var elements: [StrictJSONValue] = []
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
            while index < bytes.count && ![9, 10, 13, 32, 44, 93, 125].contains(bytes[index]) { index += 1 }
            let token = String(decoding: bytes[start..<index], as: UTF8.self)
            // Foundation accepts trailing array commas. They cannot produce an
            // empty numeric value in the explicitly strict new numeric policy.
            if Policy.preservesUnboundedNumberTokens, token.isEmpty { throw Policy.failure }
            switch token {
            case "true": return .boolean(true)
            case "false": return .boolean(false)
            case "null": return .null
            default: return .number(token)
            }
        }
    }
}

/// Lexical unsigned integers keyed by JSON path, never rounded Foundation numbers.
/// Array positions appear in a path as decimal text.
public extension StrictJSONReader {
    /// Every integer token, including direct array elements.
    var unsignedIntegers: [[String]: Int64] { integers(includingArrayElements: true) }
    /// Integer tokens held by an object member.
    var memberUnsignedIntegers: [[String]: Int64] { integers(includingArrayElements: false) }
    /// Integer tokens that are direct members of the root object.
    var topLevelUnsignedIntegers: [String: Int64] {
        var result: [String: Int64] = [:]
        for (path, integer) in memberUnsignedIntegers where path.count == 1 { result[path[0]] = integer }
        return result
    }

    private func integers(includingArrayElements: Bool) -> [[String]: Int64] {
        var result: [[String]: Int64] = [:]
        func visit(_ value: StrictJSONValue, _ path: [String], recorded: Bool) {
            switch value {
            case .number(let token):
                if recorded, !token.isEmpty, token.utf8.allSatisfy({ (48...57).contains($0) }), let integer = Int64(token) {
                    result[path] = integer
                }
            case .object(let fields):
                for (key, member) in fields { visit(member, path + [key], recorded: true) }
            case .array(let elements):
                for (position, element) in elements.enumerated() {
                    visit(element, path + [String(position)], recorded: includingArrayElements)
                }
            case .string, .boolean, .null: break
            }
        }
        if let root { visit(root, [], recorded: includingArrayElements) }
        return result
    }
}
