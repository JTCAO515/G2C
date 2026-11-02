import Foundation

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

    public static func decode(_ bytes: Data,runID: String,completed: Bool) throws -> Self {
        let frames = try decodeToolFrames(bytes,runID:runID,completed:completed,name:"place",
                                          outputVersion:"TOOL-output.1",answerVersion:"TOOL-answer.1",
                                          output: { key,raw in
            let result = try PlaceResultV1.decode(raw)
            if let source = result.source {
                let ref = toolOperationReference(runID:runID,key:key)
                guard source.evidenceKind == "synthetic",Data(source.requestReference.utf8) == Data(ref.utf8) else { throw TripFailure.invalidResponse }
            }
            return PlaceToolOutputV1(operationKey:key,result:result)
        },answer: PlaceToolAnswerV1.init)
        return .init(originalUTF8:bytes,outputs:frames.outputs,answer:frames.answer,hasPendingFrame:frames.hasPendingFrame)
    }
}
