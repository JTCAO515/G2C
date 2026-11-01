import Foundation
import Testing
@testable import CJTripClient

@Suite @MainActor struct ManualTripReplyTests {
    let trace = "B35279D6-8B42-466D-A55D-8A16B64BB270"
    let inputs = ManualTripInputTests()
    func payload(_ name: String = "text") throws -> Data {
        let f = try inputs.fixture(name); return Data(base64Encoded: f.preparation_utf8_base64)!
    }
    func original(_ name: String = "text") throws -> ManualTripInput { try inputs.frozen(inputs.fixture(name)) }
    func decode(_ bytes: Data, input: ManualTripInput) throws -> ManualTripPreparation {
        let value = try ManualTripReplies.preparation(bytes, original: input, requestID: trace)
        return try #require(value)
    }
    func mutate(_ data: Data, _ change: (inout [String: Any]) -> Void) throws -> Data {
        var value = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        change(&value); return try JSONSerialization.data(withJSONObject: value)
    }
    func mutatePreparation(_ data: Data, _ change: (inout [String: Any]) -> Void) throws -> Data {
        try mutate(data) { body in
            var value = body["preparation"] as! [String: Any]; change(&value); body["preparation"] = value
        }
    }
    @Test func canonicalPreparationSaveAndReceiptMatchOfficialCodecs() throws {
        for f in try inputs.fixtures() {
            let input = try inputs.frozen(f), reply = try decode(Data(base64Encoded: f.preparation_utf8_base64)!, input: input)
            #expect(reply.requestID == input.requestID && reply.expectedVersion == input.original.version)
            #expect(reply.before.originalUTF8 == input.original.document.originalUTF8)
            #expect(reply.after.originalUTF8 == Data(base64Encoded: f.after_utf8_base64))
            #expect(reply.originalDiffUTF8 == Data(base64Encoded: f.diff_utf8_base64))
            #expect(reply.status == .pending)
            if input.needs == nil { #expect(reply.feasibility?.status == .unknown && reply.expiresAt == 1_900_000_000) }
            else { #expect(reply.feasibility == nil && reply.expiresAt == nil) }
            let save = try ManualTripSaveInput(actionID: "synthetic-save."+f.name, preparation: reply, original: input)
            #expect(save.originalUTF8 == Data(base64Encoded: f.save_utf8_base64))
            let receipt = try ManualTripReplies.receipt(Data(base64Encoded: f.receipt_utf8_base64)!, original: save, requestID: trace)
            #expect(receipt?.actionID == save.actionID && receipt?.committedVersion == input.original.version+1)
            #expect(Mirror(reflecting: save).children.isEmpty)
        }
    }
    @Test func changedBeforeOrWrongOriginalIDsNeverBecomeReviewedDiffs() throws {
        let data = try payload(), input = try original()
        for field in ["request_id", "trip_id", "expected_version", "before"] {
            let bad = try mutatePreparation(data) { p in
                var diff = p["diff"] as! [String: Any]
                if field == "expected_version" { diff[field] = input.original.version+1 }
                else if field == "before" {
                    var before = diff[field] as! [String: Any]; before["title"] = "different original"; diff[field] = before
                } else { diff[field] = "other-original" }
                p["diff"] = diff
            }
            #expect(throws: TripFailure.invalidResponse) { try decode(bad, input: input) }
        }
    }
    @Test func unselectedContentAndOrderCannotHideInsideConsistentAfterCopies() throws {
        let data = try payload(), input = try original()
        for reorder in [false, true] {
            let bad = try mutatePreparation(data) { p in
                var content = p["content"] as! [String: Any], items = content["items"] as! [[String: Any]]
                if reorder { items.reverse() } else { items[1]["text"] = "unselected changed" }
                content["items"] = items; p["content"] = content
                var diff = p["diff"] as! [String: Any]; diff["after"] = content; p["diff"] = diff
            }
            #expect(throws: TripFailure.invalidResponse) { try decode(bad, input: input) }
        }
    }
    @Test func textChangesCannotRetainOrUpgradeOldEvidence() throws {
        let data = try payload(), input = try original()
        for category in ["verification", "source_category"] {
            let bad = try mutatePreparation(data) { p in
                var content = p["content"] as! [String: Any], items = content["items"] as! [[String: Any]]
                if category == "verification" { items[0]["verification"] = "verified"; items[0]["evidence"] = ["invented-proof"] }
                else { items[0]["source_category"] = "unknown" }
                content["items"] = items; p["content"] = content
                var diff = p["diff"] as! [String: Any]; diff["after"] = content; p["diff"] = diff
            }
            #expect(throws: TripFailure.invalidResponse) { try decode(bad, input: input) }
        }
    }
    @Test func unknownOrConflictingResultsCannotSupplySaveInput() throws {
        let data = try payload(), input = try original()
        let unknown = try mutatePreparation(data) { $0["status"] = "unknown" }
        #expect(throws: TripFailure.invalidResponse) { try decode(unknown, input: input) }
        for state in ["accepted", "rejected", "expired", "superseded"] {
            let bytes = try mutatePreparation(data) { $0["status"] = state }, reply = try decode(bytes, input: input)
            #expect(throws: TripFailure.invalidInput) { try ManualTripSaveInput(actionID: "new-action", preparation: reply, original: input) }
        }
        for status in ["CONFLICT", "PASS"] {
            let bytes = try mutatePreparation(data) { p in
                var f = p["feasibility"] as! [String: Any]; f["status"] = status; p["feasibility"] = f
            }
            #expect(throws: TripFailure.invalidResponse) { try decode(bytes, input: input) }
        }
    }
    @Test func anotherInputCannotBorrowAReviewedPreparation() throws {
        let input = try original(), prep = try decode(payload(), input: input)
        let other = try original("title")
        #expect(throws: TripFailure.invalidInput) { try ManualTripSaveInput(actionID: "wrong-input", preparation: prep, original: other) }
    }
    @Test func receiptRequiresExactOriginalRatherThanMatchingCurrentVersion() throws {
        let f = try inputs.fixture(), input = try inputs.frozen(f), prep = try decode(payload(), input: input)
        let save = try ManualTripSaveInput(actionID: "synthetic-save.text", preparation: prep, original: input)
        let good = Data(base64Encoded: f.receipt_utf8_base64)!
        for field in ["action_id", "kind", "proposal_id", "candidate_hash", "trip_id", "committed_version", "confirmed"] {
            let bad = try mutate(good) { body in
                var receipt = body["receipt"] as! [String: Any]
                if field == "committed_version" { receipt[field] = input.original.version }
                else if field == "confirmed" { receipt[field] = true }
                else { receipt[field] = "different-original" }
                body["receipt"] = receipt
            }
            #expect(throws: TripFailure.invalidResponse) { try ManualTripReplies.receipt(bad, original: save, requestID: trace) }
        }
        let absent = try mutate(good) { $0["receipt"] = NSNull() }
        #expect(try ManualTripReplies.receipt(absent, original: save, requestID: trace) == nil)
    }
    @Test func wrongResultVersionAndNullPreparationNeverFallback() throws {
        let input = try original("needs_text"), data = try payload("needs_text")
        let wrong = try mutate(data) { $0["version"] = "TRIP-manual-result.1" }
        #expect(throws: TripFailure.invalidResponse) { try decode(wrong, input: input) }
        let absent = try mutate(data) { $0["preparation"] = NSNull() }
        #expect(try ManualTripReplies.preparation(absent, original: input, requestID: trace) == nil)
    }
}
