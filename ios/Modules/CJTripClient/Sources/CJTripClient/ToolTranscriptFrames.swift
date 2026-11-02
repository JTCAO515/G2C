import Foundation
import CryptoKit

/// Newline-framed tool host transcript from a protected original RUN. Streaming
/// prefixes expose complete frames only. A completed RUN must include the final
/// bilingual answer; other terminal states retain their valid prefix and
/// explicitly mark any incomplete tail. Carries data only: never dispatches a tool.
func decodeToolFrames<Output, Answer>(_ bytes: Data, runID: String, completed: Bool, name: String,
                                      outputVersion: String, answerVersion: String,
                                      output: (_ key: String, _ exactResult: Data) throws -> Output,
                                      answer makeAnswer: (_ chinese: String, _ english: String) -> Answer) throws
    -> (outputs: [Output], answer: Answer?, hasPendingFrame: Bool) {
    guard bytes.count <= 1_048_576,!runID.isEmpty else { throw TripFailure.invalidResponse }
    let octets = Array(bytes)
    var lines: [Data] = octets.split(separator:UInt8(10),omittingEmptySubsequences:false).map { Data($0) }
    let pending: Bool
    if bytes.last == 10 { lines.removeLast();pending = false }
    else if completed { pending = false }
    else { pending = !bytes.isEmpty;lines.removeLast() }
    var outputs: [Output] = [],answer: Answer?
    var previous: (round: Int64,index: Int64)?
    for line in lines {
        guard answer == nil,!line.isEmpty else { throw TripFailure.invalidResponse }
        var parser = StrictTripJSON(bytes:Array(line))
        let root = try parser.document().object()
        guard try root.required("data_origin").text() == "synthetic" else { throw TripFailure.invalidResponse }
        switch try root.required("version").text() {
        case outputVersion:
            guard Set(root.keys) == ["version","data_origin","name","operation_key","result"],
                  try root.required("name").text() == name else { throw TripFailure.invalidResponse }
            let key = try root.required("operation_key").text(),parts = key.split(separator:".",omittingEmptySubsequences:false)
            guard parts.count == 3,parts[0] == "tool",let round = Int64(parts[1]),round >= 0,String(round) == parts[1],
                  let index = Int64(parts[2]),(0...15).contains(index),String(index) == parts[2] else { throw TripFailure.invalidResponse }
            if let previous {
                guard (round == previous.round && index == previous.index + 1)
                    || (previous.round < Int64.max && round == previous.round + 1 && index == 0) else { throw TripFailure.invalidResponse }
            } else { guard round == 0,index == 0 else { throw TripFailure.invalidResponse } }
            guard let range = parser.rootMemberRanges["result"] else { throw TripFailure.invalidResponse }
            // Preserve exact nested bytes; no JSONSerialization number/default
            // conversion between the frame and the fixed strict tool codec.
            outputs.append(try output(key,Data(line[range])));previous = (round,index)
        case answerVersion:
            guard Set(root.keys) == ["version","data_origin","text_zh","text_en"] else { throw TripFailure.invalidResponse }
            let chinese = try root.required("text_zh").text(),english = try root.required("text_en").text()
            guard !chinese.trimmingCharacters(in:CharacterSet.whitespacesAndNewlines).isEmpty,
                  !english.trimmingCharacters(in:CharacterSet.whitespacesAndNewlines).isEmpty,
                  chinese.utf8.count <= 65536,english.utf8.count <= 65536 else { throw TripFailure.invalidResponse }
            answer = makeAnswer(chinese,english)
        default:throw TripFailure.invalidResponse
        }
    }
    guard !completed || answer != nil else { throw TripFailure.invalidResponse }
    return (outputs,answer,pending)
}

func toolOperationReference(runID: String, key: String) -> String {
    "op-" + SHA256.hash(data:Data((runID + "\0" + key).utf8)).map { String(format:"%02x",$0) }.joined()
}
