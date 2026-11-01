import Foundation
import CJMessageHTTP

struct ScopedOriginal: ScopedJournalRecord, Sendable {
    let actionID: String
    let actionUTF8: Data
    let discoveryUTF8: Data
    var action: ScopedAction { get throws { try ScopedAction(originalUTF8: actionUTF8) } }
    func discovery() throws -> ScopedDiscovery {
        let json = try ScopedWireJSON(discoveryUTF8, maximumBytes: 4_000_000)
        let value = try ScopedWireJSON.fields(json.object["discovery"], "state reference run_status draft_outcome proposal")
        let reference = try MessageEditReference.decodeResponseReference(canonical(["reference": value["reference"]!]), maximumBytes: 65536)
        return try .decode(discoveryUTF8, requestID: ScopedWireJSON.text(json.object["request_id"]), original: reference)
    }
    func validate() throws {
        let action = try action
        guard exact(actionID, action.actionID), let candidate = try discovery().candidate,
              exact(action.proposalID, candidate.proposalID), action.candidateHash == candidate.candidateHash else { throw PreviewFailure.invalidResponse }
    }
}
struct ScopedSettlement: ScopedJournalRecord, Sendable {
    let actionID: String
    let original: ScopedOriginal
    let responseUTF8: Data
    let trace: String
    let httpStatus: Int
    func receipt() throws -> ScopedActionReceipt {
        guard let c = try original.discovery().candidate,
              let receipt = try ScopedActionReceipt.decode(responseUTF8, requestID: trace, original: original.action,
                tripID: c.tripID, expectedVersion: c.expectedVersion, maximumBytes: 65536) else { throw PreviewFailure.invalidResponse }
        return receipt
    }
    func validate() throws {
        try original.validate()
        guard exact(actionID, original.actionID) else { throw PreviewFailure.invalidResponse }
        if httpStatus == 200 { _ = try receipt() }
        else { try validateScopedRejection(responseUTF8, trace: trace, status: httpStatus) }
    }
}

func validateScopedRejection(_ bytes: Data, trace: String, status: Int) throws {
    let json = try ScopedWireJSON(bytes, maximumBytes: 65536)
    let root = try ScopedWireJSON.fields(json.object, "request_id error")
    let error = try ScopedWireJSON.fields(root["error"], "code category message_en message_zh outcome recovery")
    guard root["request_id"] as? String == trace, UUID(uuidString: trace) != nil,
          error["outcome"] as? String == "failed", error["recovery"] as? String == "do_not_retry",
          (status == 409 && error["code"] as? String == "TRIP_CONFLICT" && error["category"] as? String == "conflict") ||
          (status == 400 && error["code"] as? String == "INVALID_INPUT" && error["category"] as? String == "input") else { throw PreviewFailure.invalidResponse }
    _ = try ScopedWireJSON.text(error["message_en"]); _ = try ScopedWireJSON.text(error["message_zh"])
}
