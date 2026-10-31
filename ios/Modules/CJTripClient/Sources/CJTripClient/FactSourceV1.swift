import Foundation
import CryptoKit

extension FactSourceV1 {
    static func read(_ value: TripJSONValue,query: FactQueryV1,at: PlaceTimestampV1) throws -> Self {
        let f = try value.fields("evidence_id fact_key source_url retrieved_at media_type original_utf8_base64 original_sha256 value declarations status reasons")
        let encoded = try f.required("original_utf8_base64").text()
        guard let bytes = Data(base64Encoded:encoded),bytes.base64EncodedString() == encoded,
              !bytes.isEmpty,bytes.count <= 16384,let text = String(data:bytes,encoding:.utf8),
              try f.required("media_type").text() == "application/json" else { throw TripFailure.invalidResponse }
        let digest = SHA256.hash(data:bytes).map { String(format:"%02x",$0) }.joined()
        guard try factSame(f.required("original_sha256").text(),digest) else { throw TripFailure.invalidResponse }
        let url = try f.required("source_url").text()
        guard url.utf8.count <= 4096,url.utf8.allSatisfy({ $0 > 32 && $0 < 127 && $0 != 92 }),
              let target = URLComponents(string:url),target.scheme == "https",target.host == "synthetic-fact.g2c.invalid",
              target.user == nil,target.password == nil,target.fragment == nil,target.port == nil || target.port == 443,
              let authority = url.split(separator:"/",omittingEmptySubsequences:false).dropFirst(2).first,
              authority == "synthetic-fact.g2c.invalid" || authority == "synthetic-fact.g2c.invalid:443" else { throw TripFailure.invalidResponse }
        var parser = StrictTripJSON(bytes:Array(bytes));let sourceNode = try parser.document()
        try factBounds(sourceNode,maxDepth:16,maxNodes:4096)
        let source = try sourceNode.object()
        let scalar = try source.required("value")
        switch scalar { case .null,.object,.array:throw TripFailure.invalidResponse;default:break }
        guard let range = parser.rootMemberRanges["value"],let literal = String(data:Data(bytes[range]),encoding:.utf8),
              let prefix = String(data:Data(bytes[..<range.lowerBound]),encoding:.utf8) else { throw TripFailure.invalidResponse }
        let start = prefix.unicodeScalars.count,end = start + literal.unicodeScalars.count
        let excerpt = try f.required("value").fields("text start end")
        guard try factSame(excerpt.required("text").text(),literal),
              try excerpt.required("start").integer(0...Int64(text.unicodeScalars.count)) == start,
              try excerpt.required("end").integer(1...Int64(text.unicodeScalars.count)) == end else { throw TripFailure.invalidResponse }
        let declarations = try FactDeclarationsV1.read(source:source,wire:f.required("declarations"))
        let retrieved = try factStamp(f.required("retrieved_at"))
        let key = try factText(f.required("fact_key"))
        let (status,reasons) = assess(query:query,key:key,retrieved:retrieved,declarations:declarations,at:at)
        guard try f.required("status").text() == status.rawValue else { throw TripFailure.invalidResponse }
        let suppliedReasons = try f.required("reasons").elements().map { try $0.text() }
        guard suppliedReasons.count == reasons.count,zip(suppliedReasons,reasons).allSatisfy({ factSame($0,$1) }) else { throw TripFailure.invalidResponse }
        return .init(evidenceID:try factText(f.required("evidence_id")),factKey:key,sourceURL:url,retrievedAt:retrieved,
                     originalUTF8:bytes,originalSHA256:digest,originalValue:literal,valueStart:start,valueEnd:end,
                     declarations:declarations,status:status,reasons:reasons)
    }
    private static func assess(query: FactQueryV1,key: String,retrieved: PlaceTimestampV1,declarations d: FactDeclarationsV1,
                               at: PlaceTimestampV1) -> (FactStatusV1,[String]) {
        if !factSame(key,query.factKey) { return (.outOfRange,["fact_key_mismatch"]) }
        if retrieved.utcMicroseconds > at.utcMicroseconds || d.publishedAt.map({ $0.utcMicroseconds > retrieved.utcMicroseconds }) == true {
            return (.unknown,["future_observation_or_publication"])
        }
        if d.expiresAt.map({ at.utcMicroseconds >= $0.utcMicroseconds }) == true { return (.expired,["expiry_reached"]) }
        var reasons: [String] = []
        if let regions = d.regions {
            if !regions.contains(where:{ factSame($0,query.region) }) { return (.outOfRange,["region_mismatch"]) }
        } else { reasons.append("region_not_declared") }
        if let dates = d.dates {
            if dates.start > query.dates.start || query.dates.end > dates.end { return (.outOfRange,["outside_declared_dates"]) }
        } else { reasons.append("dates_not_declared") }
        if let conditions = d.conditions {
            var missing = false
            for (key,value) in conditions {
                if let pair = query.conditions.first(where:{ factSame($0.key,key) }) {
                    if !factSame(pair.value,value) { return (.outOfRange,["condition_mismatch"]) }
                } else { missing = true }
            }
            if missing { reasons.append("condition_not_supplied") }
        } else { reasons.append("conditions_not_declared") }
        if d.expiresAt == nil { reasons.append("expiry_not_declared") }
        return (reasons.isEmpty ? .supported : .unknown,reasons)
    }
}

extension FactDeclarationsV1 {
    static func read(source: [String:TripJSONValue],wire: TripJSONValue) throws -> Self {
        func optional<T>(_ key: String,_ convert: (TripJSONValue)throws->T) throws -> T? {
            guard let value = source[key] else { return nil }
            return try value.nullable(convert)
        }
        func regions(_ value: TripJSONValue) throws -> [String] {
            let strings = try value.elements().map { try $0.text() }
            guard !strings.isEmpty,strings.allSatisfy({ !$0.isEmpty }) else { throw TripFailure.invalidResponse };return strings
        }
        let declaredRegions = try optional("regions",regions)
        let dates = try optional("dates",FactDatesV1.read)
        let conditions = try optional("conditions") { try factConditions($0,bounded:false) }
        let published = try optional("published_at",sourceStamp),expires = try optional("expires_at",sourceStamp)
        if let published,let expires { guard expires.utcMicroseconds > published.utcMicroseconds else { throw TripFailure.invalidResponse } }
        let f = try wire.fields("regions dates conditions published_at expires_at")
        let projectedRegions = try f.required("regions").nullable(regions)
        if let a = declaredRegions,let b = projectedRegions {
            guard a.count == b.count,zip(a,b).allSatisfy({ factSame($0,$1) }) else { throw TripFailure.invalidResponse }
        } else { guard (declaredRegions == nil) == (projectedRegions == nil) else { throw TripFailure.invalidResponse } }
        guard try f.required("dates").nullable(FactDatesV1.read) == dates,
              try f.required("published_at").nullable(factStamp) == published,
              try f.required("expires_at").nullable(factStamp) == expires else { throw TripFailure.invalidResponse }
        let projected = try f.required("conditions").nullable { try factConditions($0,bounded:false) }
        if let a = conditions,let b = projected {
            guard a.count == b.count,a.allSatisfy({ key,value in b.contains(where:{ factSame($0.key,key) && factSame($0.value,value) }) }) else { throw TripFailure.invalidResponse }
        } else { guard (conditions == nil) == (projected == nil) else { throw TripFailure.invalidResponse } }
        return .init(regions:declaredRegions,dates:dates,conditions:conditions,publishedAt:published,expiresAt:expires)
    }
    /// Parse the source's explicit ISO offset, retaining it in the canonical
    /// FACT stamp. Never consult the device timezone or fill a missing offset.
    private static func sourceStamp(_ value: TripJSONValue) throws -> PlaceTimestampV1 {
        let raw = try value.text()
        let regex = try NSRegularExpression(pattern:#"^([0-9]{4}-[0-9]{2}-[0-9]{2})[T ]([0-9]{2}:[0-9]{2}:[0-9]{2})(?:[.,]([0-9]+))?(Z|[+-][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:[.,][0-9]+)?)?)$"#)
        guard let match = regex.firstMatch(in:raw,range:NSRange(raw.startIndex...,in:raw)) else { throw TripFailure.invalidResponse }
        func part(_ n: Int) -> String? { Range(match.range(at:n),in:raw).map { String(raw[$0]) } }
        guard let date = part(1),let time = part(2),var offset = part(4) else { throw TripFailure.invalidResponse }
        let fraction = part(3).map { String($0.prefix(6)).padding(toLength:6,withPad:"0",startingAt:0) } ?? "000000"
        if offset == "Z" || offset == "-00:00" { offset = "+00:00" }
        if offset.count > 6 {
            let base = String(offset.prefix(6)),tail = String(offset.dropFirst(7)).replacingOccurrences(of:",",with:".")
            let pieces = tail.split(separator:".",omittingEmptySubsequences:false)
            guard pieces.count <= 2,let seconds = Int(pieces[0]),seconds < 60 else { throw TripFailure.invalidResponse }
            let micro = pieces.count == 2 ? String(pieces[1].prefix(6)).padding(toLength:6,withPad:"0",startingAt:0) : "000000"
            if seconds == 0 && micro == "000000" { offset = base == "-00:00" ? "+00:00" : base }
            else { offset = base + ":" + String(format:"%02d",seconds) + (micro == "000000" ? "" : "." + micro) }
        }
        return try factStamp(.object(["iso8601":.string(date + "T" + time + "." + fraction + offset),"fold":.number("0")]))
    }
}
