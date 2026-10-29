import Foundation
import CJAPI

private enum CheckFailure: Error { case unexpectedAcceptance, wrongValue }

@main
struct DraftStatusV2GeneratedCheck {
    static func main() throws {
        let base: [String: Any] = [
            "request_id": "00000000-0000-4000-8000-000000000001",
            "version": "RUN-draft-status.2", "conversation_id": "chat",
            "generation": "g", "message_id": "m", "run_id": "r",
            "message_sequence": 1, "run_status": "completed", "event_highwater": 4,
            "draft_outcome": "not_recorded"
        ]
        for stage in ["none", "answer", "draft"] {
            var value = base
            value["budget_exhausted_stage"] = stage
            let decoded = try JSONDecoder().decode(Components.Schemas.RunDraftStatusV2Response.self,
                from: JSONSerialization.data(withJSONObject: value))
            guard decoded.budget_exhausted_stage.rawValue == stage else { throw CheckFailure.wrongValue }
        }
        for stage: Any in ["", "tool", NSNull()] {
            var value = base
            value["budget_exhausted_stage"] = stage
            try reject(value)
        }
        try reject(base)
        print("PASS actual generated v2: none/answer/draft accepted; empty/unknown/null/missing rejected")
    }

    private static func reject(_ value: [String: Any]) throws {
        do {
            _ = try JSONDecoder().decode(Components.Schemas.RunDraftStatusV2Response.self,
                from: JSONSerialization.data(withJSONObject: value))
            throw CheckFailure.unexpectedAcceptance
        } catch is DecodingError { }
    }
}
