import Foundation
import CryptoKit

/// FACT@1.0 synthetic declarations. This codec confers no AUTH, source truth,
/// freshness renewal, tool dispatch or Trip/Memory write permission.
public enum FactStatusV1: String, Sendable {
    case supported, outOfRange = "unsupported_or_out_of_range", expired, conflicting, unknown
    var summaries: (String,String) {
        switch self {
        case .supported:("所给证据声明覆盖查询范围；请核对原文和条件。","The supplied declarations cover this query; check the original text and conditions.")
        case .outOfRange:("查询超出所给证据声明的适用范围。","The query is outside the declared evidence scope.")
        case .expired:("所给证据已过声明的有效期，需重新核实。","The supplied evidence has expired; verification is needed.")
        case .conflicting:("适用证据的原始值不一致，需核实，不能选定答案。","Applicable original values differ; verification is needed before choosing an answer.")
        case .unknown:("证据或适用信息不完整，待核实。","Evidence or applicability information is incomplete; verification is needed.")
        }
    }
}
public enum FactOutcomeV1: String, Sendable {
    case ok, noResults = "no_results", rateLimited = "rate_limited", invalidResponse = "invalid_response", sourceFailure = "source_failure"
    var failureSummaries: (String,String)? {
        switch self {
        case .ok,.noResults:nil
        case .rateLimited:("合成来源限流，待核实。","Synthetic source rate limited; verification is needed.")
        case .invalidResponse:("合成来源内容无效，待核实。","Synthetic source content is invalid; verification is needed.")
        case .sourceFailure:("合成来源失败，待核实。","Synthetic source failed; verification is needed.")
        }
    }
}
public struct FactDatesV1: Sendable, Equatable {
    public let start: String
    public let end: String
    static func read(_ value: TripJSONValue) throws -> Self {
        let f = try value.fields("start end"),start = try f.required("start").text(),end = try f.required("end").text()
        for date in [start,end] {
            guard date.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}") else { throw TripFailure.invalidResponse }
            _ = try factStamp(.object(["iso8601":.string(date + "T00:00:00.000000+00:00"),"fold":.number("0")]))
        }
        guard start <= end else { throw TripFailure.invalidResponse }
        return .init(start:start,end:end)
    }
}
public struct FactQueryV1: Sendable {
    public let factKey: String
    public let region: String
    public let dates: FactDatesV1
    public let conditions: [String:String]
    static func read(_ value: TripJSONValue) throws -> Self {
        let f = try value.fields("version fact_key region dates conditions")
        guard try f.required("version").text() == "FACT-query.1" else { throw TripFailure.invalidResponse }
        let conditions = try factConditions(f.required("conditions"),bounded:true)
        return .init(factKey:try factText(f.required("fact_key")),region:try factText(f.required("region")),
                     dates:try FactDatesV1.read(f.required("dates")),conditions:conditions)
    }
}
public struct FactDeclarationsV1: Sendable {
    public let regions: [String]?
    public let dates: FactDatesV1?
    public let conditions: [String:String]?
    public let publishedAt: PlaceTimestampV1?
    public let expiresAt: PlaceTimestampV1?
}
public struct FactSourceV1: Sendable {
    public let evidenceID: String
    public let factKey: String
    public let sourceURL: String
    public let retrievedAt: PlaceTimestampV1
    public let originalUTF8: Data
    public let originalSHA256: String
    /// Exact JSON scalar literal, including quotes/escapes/negation/currency.
    public let originalValue: String
    /// Unicode scalar offsets in the original decoded document, end exclusive.
    public let valueStart: Int
    public let valueEnd: Int
    public let declarations: FactDeclarationsV1
    public let status: FactStatusV1
    public let reasons: [String]
}
public struct FactResultV1: Sendable {
    public static let contractVersion = "FACT@1.0"
    public let originalUTF8: Data
    public let requestReference: String
    public let query: FactQueryV1
    public let evaluatedAt: PlaceTimestampV1
    public let outcome: FactOutcomeV1
    public let status: FactStatusV1
    public let originalValue: String?
    public let chinese: String
    public let english: String
    public let sources: [FactSourceV1]

    public static func decode(_ bytes: Data) throws -> Self {
        guard !bytes.isEmpty,bytes.count <= 131072 else { throw TripFailure.invalidResponse }
        var parser = StrictTripJSON(bytes:Array(bytes));let node = try parser.document()
        try factBounds(node,maxDepth:24,maxNodes:16384)
        let f = try node.fields("version data_origin request_ref query evaluated_at outcome status original_value summary_zh summary_en sources")
        guard try f.required("version").text() == "FACT-result.1",try f.required("data_origin").text() == "synthetic",
              let outcome = FactOutcomeV1(rawValue:try f.required("outcome").text()),
              let status = FactStatusV1(rawValue:try f.required("status").text()) else { throw TripFailure.invalidResponse }
        let query = try FactQueryV1.read(f.required("query")),at = try factStamp(f.required("evaluated_at"))
        let original = try f.required("original_value").nullable { try $0.text() }
        let zh = try f.required("summary_zh").text(),en = try f.required("summary_en").text()
        let values = try f.required("sources").elements()
        guard values.count <= 16 else { throw TripFailure.invalidResponse }
        let sources = try values.map { try FactSourceV1.read($0,query:query,at:at) }
        guard Set(sources.map { Data($0.evidenceID.utf8) }).count == sources.count else { throw TripFailure.invalidResponse }
        let summaries: (String,String)
        if let failure = outcome.failureSummaries {
            guard sources.isEmpty,status == .unknown,original == nil else { throw TripFailure.invalidResponse }
            summaries = failure
        } else {
            guard outcome == (sources.isEmpty ? .noResults : .ok) else { throw TripFailure.invalidResponse }
            let eligible = sources.filter { $0.status == .supported }
            let literals = Set(eligible.map { Data($0.originalValue.utf8) })
            let computed: FactStatusV1
            if literals.count > 1 { computed = .conflicting }
            else if sources.contains(where:{ $0.status == .unknown }) { computed = .unknown }
            else if !eligible.isEmpty { computed = .supported }
            else if !sources.isEmpty && sources.allSatisfy({ $0.status == .expired }) { computed = .expired }
            else if !sources.isEmpty && sources.allSatisfy({ $0.status == .outOfRange }) { computed = .outOfRange }
            else { computed = .unknown }
            guard status == computed else { throw TripFailure.invalidResponse }
            if computed == .supported {
                guard let original,let first = eligible.first,factSame(original,first.originalValue) else { throw TripFailure.invalidResponse }
            } else { guard original == nil else { throw TripFailure.invalidResponse } }
            summaries = computed.summaries
        }
        guard factSame(zh,summaries.0),factSame(en,summaries.1) else { throw TripFailure.invalidResponse }
        return .init(originalUTF8:bytes,requestReference:try factText(f.required("request_ref")),query:query,evaluatedAt:at,
                     outcome:outcome,status:status,originalValue:original,chinese:zh,english:en,sources:sources)
    }
}

func factSame(_ a: String,_ b: String) -> Bool { a.utf8.elementsEqual(b.utf8) }
func factText(_ value: TripJSONValue) throws -> String {
    let text = try value.text()
    guard !text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,text.unicodeScalars.count <= 256 else { throw TripFailure.invalidResponse }
    return text
}
func factConditions(_ value: TripJSONValue,bounded: Bool) throws -> [String:String] {
    let values = try value.object()
    guard !bounded || values.count <= 32 else { throw TripFailure.invalidResponse }
    return try values.reduce(into:[:]) { result,pair in
        let key = pair.key,text = try pair.value.text()
        if bounded { _ = try factText(.string(key));_ = try factText(.string(text)) }
        else { guard !key.isEmpty,!text.isEmpty else { throw TripFailure.invalidResponse } }
        result[key] = text
    }
}
func factStamp(_ value: TripJSONValue) throws -> PlaceTimestampV1 {
    let stamp = try PlaceTimestampV1.read(value)
    guard (0...315537897599999999).contains(stamp.utcMicroseconds) else { throw TripFailure.invalidResponse }
    return stamp
}
func factBounds(_ value: TripJSONValue,maxDepth: Int,maxNodes: Int) throws {
    var nodes = 0
    func visit(_ value: TripJSONValue,_ depth: Int) throws {
        nodes += 1;guard nodes <= maxNodes else { throw TripFailure.invalidResponse }
        switch value {
        case .object(let fields):
            guard depth < maxDepth else { throw TripFailure.invalidResponse }
            nodes += fields.count;guard nodes <= maxNodes else { throw TripFailure.invalidResponse }
            for value in fields.values { try visit(value,depth+1) }
        case .array(let values):
            guard depth < maxDepth else { throw TripFailure.invalidResponse }
            for value in values { try visit(value,depth+1) }
        case .number(let token):
            if token.contains(".") || token.lowercased().contains("e") {
                guard let number = Double(token),number.isFinite else { throw TripFailure.invalidResponse }
            }
        default:break
        }
    }
    try visit(value,0)
}
