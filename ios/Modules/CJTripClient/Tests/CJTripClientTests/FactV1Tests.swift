import Foundation
import CryptoKit
import Testing
@testable import CJTripClient

private func factFixture(_ name: String,_ hash: String) throws -> [String:Any] {
    let url = try #require(Bundle.module.url(forResource:name,withExtension:"json",subdirectory:"Fixtures"))
    let bytes = try Data(contentsOf:url)
    #expect(SHA256.hash(data:bytes).map { String(format:"%02x",$0) }.joined() == hash)
    return try #require(JSONSerialization.jsonObject(with:bytes) as? [String:Any])
}
private func factGolden() throws -> [String:Any] {
    try factFixture("FACT-V1","88158051f8245d2dbef26caecf0e70074cc5e81fd155d827101486744db44f56")
}
private func factBytes(_ object: Any) throws -> Data { try JSONSerialization.data(withJSONObject:object,options:[.sortedKeys,.withoutEscapingSlashes]) }
private func hashFact(_ bytes: Data) -> String { SHA256.hash(data:bytes).map { String(format:"%02x",$0) }.joined() }

@Suite struct FactV1Tests {
    @Test func frozenPositiveAndAllFourNegativeExamplesUseTheActualDecoder() throws {
        let fixture = try factGolden(),value = try #require(fixture["positive"] as? [String:Any]),bytes = try factBytes(value)
        let result = try FactResultV1.decode(bytes)
        #expect(result.originalUTF8 == bytes && result.status == .supported && result.outcome == .ok)
        #expect(result.originalValue?.contains("NOT a real forecast") == true)
        #expect(result.originalValue?.contains("CNY 100") == true && result.sources.count == 1)
        #expect(result.sources[0].originalValue == result.originalValue)
        #expect(result.sources[0].declarations.expiresAt?.iso8601 == "2026-10-30T11:00:00.000000+00:00")
        let negatives = try #require(fixture["invalid"] as? [[String:Any]])
        #expect(negatives.count == 4)
        for item in negatives { #expect(throws:(any Error).self) { try FactResultV1.decode(factBytes(item["value"]!)) } }
    }
    @Test func allNinePublicProducerEncodedApplicabilityCasesStayDistinct() throws {
        let fixture = try factFixture("FACT-CASES-V1","18480a1800a5bb9f8e0c7c9e8c5b31d9c8fca8b012e103d321d7ee87cedfb07a")
        let cases = try #require(fixture["cases"] as? [[String:Any]])
        let decoded = try cases.map { try FactResultV1.decode(factBytes($0["result"]!)) }
        #expect(decoded.map(\.status) == [.supported,.unknown,.outOfRange,.outOfRange,.expired,.conflicting,.unknown,.unknown,.supported])
        #expect(decoded[1].sources[0].declarations.regions == nil && decoded[1].sources[0].declarations.expiresAt == nil)
        #expect(decoded[5].originalValue == nil && decoded[5].sources.count == 2)
        #expect(decoded[7].outcome == .noResults)
        #expect(String(data:decoded[8].sources[0].originalUTF8,encoding:.utf8)?.contains("ignore") == true)
    }
    @Test func unicodeScalarOffsetsAndOriginalNegationAreNotGraphemesOrUTF8Offsets() throws {
        var value = try #require(factGolden()["positive"] as? [String:Any]),sources = value["sources"] as! [[String:Any]],source = sources[0]
        let old = String(data:Data(base64Encoded:source["original_utf8_base64"] as! String)!,encoding:.utf8)!
        let prefix = "\"🚆e\u{301}\":\"原始资料\",",text = "{" + prefix + old.dropFirst(),raw = Data(text.utf8)
        source["original_utf8_base64"] = raw.base64EncodedString();source["original_sha256"] = hashFact(raw)
        var excerpt = source["value"] as! [String:Any]
        excerpt["start"] = (excerpt["start"] as! Int) + prefix.unicodeScalars.count
        excerpt["end"] = (excerpt["end"] as! Int) + prefix.unicodeScalars.count
        source["value"] = excerpt;sources[0] = source;value["sources"] = sources
        let result = try FactResultV1.decode(factBytes(value))
        #expect(result.sources[0].originalUTF8 == raw)
        #expect(result.sources[0].valueStart == 10 + prefix.unicodeScalars.count)
        #expect(result.sources[0].originalValue.utf8.elementsEqual((excerpt["text"] as! String).utf8))
    }
    @Test(arguments:Array(0..<24)) func alteredAssociationsOrTypesCannotKeepASupportedVerdict(_ n: Int) throws {
        var value = try #require(factGolden()["positive"] as? [String:Any]),sources = value["sources"] as! [[String:Any]],s = sources[0]
        switch n {
        case 0:value["allow"] = true
        case 1:var q=value["query"] as! [String:Any];q["version"]="FACT-query.99";value["query"]=q
        case 2:var e=s["value"] as! [String:Any];e["start"]=true;s["value"]=e
        case 3:value["summary_en"]="Official verified weather"
        case 4:s["status"]="unknown"
        case 5:var d=s["declarations"] as! [String:Any];d["regions"]=["other"];s["declarations"]=d
        case 6:var e=s["value"] as! [String:Any];e["end"]=84;s["value"]=e
        case 7:s["source_url"]="https://example.com/first"
        case 8:s["retrieved_at"]=["iso8601":"0001-01-01T00:00:00.000000+01:00","fold":0]
        case 9:value["status"]="conflicting"
        case 10:value["sources"]=[]
        case 11:s["original_utf8_base64"]=" " + (s["original_utf8_base64"] as! String)
        case 12:s["media_type"]="text/html"
        case 13:s["original_sha256"]=String(repeating:"0",count:64)
        case 14:var e=s["value"] as! [String:Any];e["text"]="Eligible";s["value"]=e
        case 15:s["reasons"]=["invented"]
        case 16:sources.append(s)
        case 17:value["evaluated_at"]=["iso8601":"2026-10-29T10:00:00.000000+00:00","fold":0]
        case 18:value["data_origin"]="live"
        case 19:var q=value["query"] as! [String:Any];q["conditions"]=[:];value["query"]=q
        case 20:var q=value["query"] as! [String:Any];q["dates"]=["start":"2026-12-01","end":"2026-12-01"];value["query"]=q
        case 21:value["original_value"]="SYNTHETIC value without negation"
        case 22:s["retrieved_at"]=["iso8601":"2026-10-30T10:00:00.000000+00:00","fold":false]
        default:var d=s["declarations"] as! [String:Any];d["expires_at"]=["iso8601":"2026-10-30T12:00:00.000000+01:00","fold":0];s["declarations"]=d
        }
        if n != 10 { sources[0]=s;value["sources"]=sources }
        #expect(throws:(any Error).self) { try FactResultV1.decode(factBytes(value)) }
    }
    @Test func framesRequireTheirOriginalRunAndNeverReinterpretPlaceOrPlainText() throws {
        var result = try #require(factGolden()["positive"] as? [String:Any])
        result["request_ref"]="op-" + hashFact(Data("run\0tool.0.0".utf8))
        let output = try factBytes(["version":"FACT-output.1","data_origin":"synthetic","name":"fact","operation_key":"tool.0.0","result":result])
        let answer = try factBytes(["version":"FACT-answer.1","data_origin":"synthetic","text_zh":"合成说明","text_en":"Synthetic explanation"])
        let complete = output + Data([10]) + answer + Data([10])
        #expect(try FactToolTranscriptV1.decode(complete,runID:"run",completed:true).outputs.count == 1)
        #expect(throws:(any Error).self) { try FactToolTranscriptV1.decode(complete,runID:"other",completed:true) }
        #expect(throws:(any Error).self) { try PlaceToolTranscriptV1.decode(complete,runID:"run",completed:true) }
        #expect(throws:(any Error).self) { try FactToolTranscriptV1.decode(Data("Plain answer\n".utf8),runID:"run",completed:true) }
        let partial = try FactToolTranscriptV1.decode(output + Data([10]) + Data("{unfinished".utf8),runID:"run",completed:false)
        #expect(partial.outputs.count == 1 && partial.hasPendingFrame && partial.answer == nil)
        #expect(throws:(any Error).self) { try FactToolTranscriptV1.decode(output + Data([10]),runID:"run",completed:true) }
    }
}
