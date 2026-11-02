import Foundation

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
        let frames = try decodeToolFrames(bytes,runID:runID,completed:completed,name:"fact",
                                          outputVersion:"FACT-output.1",answerVersion:"FACT-answer.1",
                                          output: { key,raw in
            let result = try FactResultV1.decode(raw)
            guard factSame(result.requestReference,toolOperationReference(runID:runID,key:key)) else { throw TripFailure.invalidResponse }
            return FactToolOutputV1(operationKey:key,result:result)
        },answer: FactToolAnswerV1.init)
        return .init(originalUTF8:bytes,outputs:frames.outputs,answer:frames.answer,hasPendingFrame:frames.hasPendingFrame)
    }
}
