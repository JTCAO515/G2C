import Foundation
import CryptoKit

/// Fixed synthetic PLACE-TOOL-HOST@1 frames from an original protected RUN read.
/// Carries data only: never dispatches a tool or accepts a TripProposal.
public struct PlaceToolOutputV1: Sendable {
    public let operationKey: String
    public let result: PlaceResultV1
}
public struct PlaceToolAnswerV1: Sendable {
    public let chinese: String
    public let english: String
}
public struct PlaceToolTranscriptV1: Sendable {
    public let originalUTF8: Data
    public let outputs: [PlaceToolOutputV1]
    public let answer: PlaceToolAnswerV1?
    public let hasPendingFrame: Bool

    /// Streaming prefixes expose complete newline-terminated frames only. A
    /// completed RUN must include the final bilingual answer; other terminal
    /// states retain their valid prefix and explicitly mark any incomplete tail.
    public static func decode(_ bytes: Data,runID: String,completed: Bool) throws -> Self {
        guard bytes.count <= 1_048_576,!runID.isEmpty else { throw TripFailure.invalidResponse }
        let octets = Array(bytes)
        var lines: [Data] = octets.split(separator:UInt8(10),omittingEmptySubsequences:false).map { Data($0) }
        let pending: Bool
        if bytes.last == 10 { lines.removeLast();pending = false }
        else if completed { pending = false }
        else { pending = !bytes.isEmpty;lines.removeLast() }
        var outputs: [PlaceToolOutputV1] = [],answer: PlaceToolAnswerV1?
        var previous: (round: Int64,index: Int64)?
        for line in lines {
            guard answer == nil,!line.isEmpty else { throw TripFailure.invalidResponse }
            var parser = StrictTripJSON(bytes:Array(line))
            let root = try parser.document().object()
            guard try root.required("data_origin").text() == "synthetic" else { throw TripFailure.invalidResponse }
            switch try root.required("version").text() {
            case "TOOL-output.1":
                guard Set(root.keys) == ["version","data_origin","name","operation_key","result"],
                      try root.required("name").text() == "place" else { throw TripFailure.invalidResponse }
                let key = try root.required("operation_key").text(),parts = key.split(separator:".",omittingEmptySubsequences:false)
                guard parts.count == 3,parts[0] == "tool",let round = Int64(parts[1]),round >= 0,String(round) == parts[1],
                      let index = Int64(parts[2]),(0...15).contains(index),String(index) == parts[2] else { throw TripFailure.invalidResponse }
                if let previous {
                    guard (round == previous.round && index == previous.index + 1)
                        || (previous.round < Int64.max && round == previous.round + 1 && index == 0) else { throw TripFailure.invalidResponse }
                } else { guard round == 0,index == 0 else { throw TripFailure.invalidResponse } }
                guard let range = parser.rootMemberRanges["result"] else { throw TripFailure.invalidResponse }
                // Preserve exact nested bytes; no JSONSerialization number/default
                // conversion between the frame and the fixed strict PLACE codec.
                let result = try PlaceResultV1.decode(Data(line[range]))
                if let source = result.source {
                    let ref = "op-" + SHA256.hash(data:Data((runID + "\0" + key).utf8)).map { String(format:"%02x",$0) }.joined()
                    guard source.evidenceKind == "synthetic",Data(source.requestReference.utf8) == Data(ref.utf8) else { throw TripFailure.invalidResponse }
                }
                outputs.append(.init(operationKey:key,result:result));previous = (round,index)
            case "TOOL-answer.1":
                guard Set(root.keys) == ["version","data_origin","text_zh","text_en"] else { throw TripFailure.invalidResponse }
                let chinese = try root.required("text_zh").text(),english = try root.required("text_en").text()
                guard !chinese.trimmingCharacters(in:CharacterSet.whitespacesAndNewlines).isEmpty,
                      !english.trimmingCharacters(in:CharacterSet.whitespacesAndNewlines).isEmpty,
                      chinese.utf8.count <= 65536,english.utf8.count <= 65536 else { throw TripFailure.invalidResponse }
                answer = .init(chinese:chinese,english:english)
            default:throw TripFailure.invalidResponse
            }
        }
        guard !completed || answer != nil else { throw TripFailure.invalidResponse }
        return .init(originalUTF8:bytes,outputs:outputs,answer:answer,hasPendingFrame:pending)
    }
}
