import Foundation
import CryptoKit

public struct FactToolOutputV1: Sendable {
    public let operationKey: String
    public let result: FactResultV1
}
public struct FactToolAnswerV1: Sendable {
    public let chinese: String
    public let english: String
}
/// Only FACT-TOOL-HOST@1 frames from the protected original RUN. Association
/// hashes are checked as data; they never grant AUTH or another invocation.
public struct FactToolTranscriptV1: Sendable {
    public let originalUTF8: Data
    public let outputs: [FactToolOutputV1]
    public let answer: FactToolAnswerV1?
    public let hasPendingFrame: Bool
    public static func decode(_ bytes: Data,runID: String,completed: Bool) throws -> Self {
        guard bytes.count <= 1_048_576,!runID.isEmpty else { throw TripFailure.invalidResponse }
        let octets = Array(bytes)
        var lines: [Data] = octets.split(separator:UInt8(10),omittingEmptySubsequences:false).map { Data($0) }
        let pending: Bool
        if bytes.last == 10 { lines.removeLast();pending = false }
        else if completed { pending = false }
        else { pending = !bytes.isEmpty;lines.removeLast() }
        var outputs: [FactToolOutputV1] = [],answer: FactToolAnswerV1?
        var previous: (round: Int64,index: Int64)?
        for line in lines {
            guard answer == nil,!line.isEmpty else { throw TripFailure.invalidResponse }
            var parser = StrictTripJSON(bytes:Array(line));let root = try parser.document().object()
            guard try root.required("data_origin").text() == "synthetic" else { throw TripFailure.invalidResponse }
            switch try root.required("version").text() {
            case "FACT-output.1":
                guard Set(root.keys) == ["version","data_origin","name","operation_key","result"],
                      try root.required("name").text() == "fact" else { throw TripFailure.invalidResponse }
                let key = try root.required("operation_key").text(),parts = key.split(separator:".",omittingEmptySubsequences:false)
                guard parts.count == 3,parts[0] == "tool",let round = Int64(parts[1]),round >= 0,String(round) == parts[1],
                      let index = Int64(parts[2]),(0...15).contains(index),String(index) == parts[2] else { throw TripFailure.invalidResponse }
                if let previous {
                    guard (round == previous.round && index == previous.index + 1)
                        || (previous.round < Int64.max && round == previous.round + 1 && index == 0) else { throw TripFailure.invalidResponse }
                } else { guard round == 0,index == 0 else { throw TripFailure.invalidResponse } }
                guard let range = parser.rootMemberRanges["result"] else { throw TripFailure.invalidResponse }
                let result = try FactResultV1.decode(Data(line[range]))
                let expected = "op-" + SHA256.hash(data:Data((runID + "\0" + key).utf8)).map { String(format:"%02x",$0) }.joined()
                guard factSame(result.requestReference,expected) else { throw TripFailure.invalidResponse }
                outputs.append(.init(operationKey:key,result:result));previous = (round,index)
            case "FACT-answer.1":
                guard Set(root.keys) == ["version","data_origin","text_zh","text_en"] else { throw TripFailure.invalidResponse }
                let zh = try root.required("text_zh").text(),en = try root.required("text_en").text()
                guard !zh.trimmingCharacters(in:CharacterSet.whitespacesAndNewlines).isEmpty,!en.trimmingCharacters(in:CharacterSet.whitespacesAndNewlines).isEmpty,
                      zh.utf8.count <= 65536,en.utf8.count <= 65536 else { throw TripFailure.invalidResponse }
                answer = .init(chinese:zh,english:en)
            default:throw TripFailure.invalidResponse
            }
        }
        guard !completed || answer != nil else { throw TripFailure.invalidResponse }
        return .init(originalUTF8:bytes,outputs:outputs,answer:answer,hasPendingFrame:pending)
    }
}
