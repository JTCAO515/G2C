import Foundation
import CJAPI
import CJMessageHTTP

public enum RunScopedDraftOutcome: Sendable {
    case ordinary(Components.Schemas.RunDraftStatusV2Response.draft_outcomePayload)
    case result(ScopedRunResultKind)
    public var rawValue: String {
        switch self { case .ordinary(let value): value.rawValue; case .result(let value): value.rawValue }
    }
    init(_ value: String) throws {
        if let old = Components.Schemas.RunDraftStatusV2Response.draft_outcomePayload(rawValue: value) { self = .ordinary(old) }
        else if let kind = ScopedRunResultKind(rawValue: value) { self = .result(kind) }
        else { throw RunDisplayFailure.invalidResponse }
    }
}

public struct RunScopedDraftStatus: Sendable {
    public let runStatus: Components.Schemas.RunDraftStatusV2Response.run_statusPayload
    public let draftOutcome: RunScopedDraftOutcome
    public let budgetStage: Components.Schemas.RunDraftStatusV2Response.budget_exhausted_stagePayload
    public let reference: MessageEditReference
    public let scopedResult: RunScopedResultReference?
}

private struct ScopedDraftProjection: Decodable {
    let request_id, conversation_id, generation, message_id, run_id: String
    let message_sequence, event_highwater: Int
    let run_status: Components.Schemas.RunDraftStatusV2Response.run_statusPayload
    let draft_outcome: String
    let budget_exhausted_stage: Components.Schemas.RunDraftStatusV2Response.budget_exhausted_stagePayload
}

func decodeScopedDraftStatus(_ bytes: Data, reference: MessageEditReference) throws -> (RunScopedDraftStatus, (String, String, String, String, String, Int, Int, String)) {
    let envelope = try RunTripEnvelope(bytes, fields: "request_id version conversation_id generation message_id run_id message_sequence event_highwater run_status draft_outcome budget_exhausted_stage reference scoped_result", version: "RUN-draft-status.6", reference: reference)
    try envelope.requireIntegers(["message_sequence", "event_highwater"])
    let p = try JSONDecoder().decode(ScopedDraftProjection.self, from: bytes)
    let outcome = try RunScopedDraftOutcome(p.draft_outcome)
    let result = try RunScopedResultReference.decodeResponseReference(bytes, maximumBytes: bytes.count, matching: reference)
    switch outcome {
    case .result(let kind):
        guard result?.kind == kind, p.run_status == .completed, p.budget_exhausted_stage == .none else { throw RunDisplayFailure.inconsistentSnapshot }
    case .ordinary:
        guard result == nil else { throw RunDisplayFailure.inconsistentSnapshot }
    }
    return (.init(runStatus: p.run_status, draftOutcome: outcome, budgetStage: p.budget_exhausted_stage, reference: reference, scopedResult: result),
        (p.request_id, p.conversation_id, p.generation, p.message_id, p.run_id, p.message_sequence, p.event_highwater, p.run_status.rawValue))
}
