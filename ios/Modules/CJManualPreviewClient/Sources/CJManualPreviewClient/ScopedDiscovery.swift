import Foundation
import CJTripClient
import CJMessageHTTP

public enum ScopedDiscoveryState: String, Sendable {
    case published, notRequested = "not_requested", pending, noCandidate = "no_candidate", unknown, unavailable
}
public struct ScopedFeasibilityCheck: Sendable {
    public let code: String
    public let status: String
    public let missing: [String]
    public let english: String
    public let chinese: String
}
public struct ScopedCandidate: Sendable {
    public let proposalID: String
    public let tripID: String
    public let expectedVersion: Int64
    public let candidateHash: String
    public let status: String
    public let expiresAt: Int64
    public let before: StructuredTripDocument
    public let after: StructuredTripDocument
    public let feasibilityStatus: String
    public let checks: [ScopedFeasibilityCheck]
    public let outputEnglish: String
    public let outputChinese: String
    /// Exact response retained for original-action recovery; never fresh write authority.
    public let discoveryUTF8: Data
}
public struct ScopedDiscovery: Sendable {
    public let state: ScopedDiscoveryState
    public let reference: MessageEditReference
    public let runStatus: String
    public let draftOutcome: String?
    public let candidate: ScopedCandidate?
    public let responseUTF8: Data

    public static func decode(_ bytes: Data, requestID: String, original: MessageEditReference) throws -> Self {
        let json = try ScopedWireJSON(bytes, maximumBytes: 4_000_000)
        let envelope = try ScopedWireJSON.fields(json.object, "version request_id discovery")
        guard envelope["version"] as? String == "TRIP-scoped-discovery.1",
              envelope["request_id"] as? String == requestID, UUID(uuidString: requestID) != nil else { throw PreviewFailure.invalidResponse }
        let value = try ScopedWireJSON.fields(envelope["discovery"], "state reference run_status draft_outcome proposal")
        guard let state = ScopedDiscoveryState(rawValue: try ScopedWireJSON.text(value["state"])) else { throw PreviewFailure.invalidResponse }
        let reference = try readReference(value["reference"])
        guard reference == original else { throw PreviewFailure.invalidResponse }
        let run = try ScopedWireJSON.text(value["run_status"])
        guard ["queued", "running", "completed", "unknown", "failed", "cancelled", "context_invalid"].contains(run) else { throw PreviewFailure.invalidResponse }
        let outcome: String?
        if value["draft_outcome"] is NSNull { outcome = nil }
        else {
            let text = try ScopedWireJSON.text(value["draft_outcome"])
            guard ["validation_failed", "provider_failed", "budget_exhausted", "provider_unknown"].contains(text) else { throw PreviewFailure.invalidResponse }
            outcome = text
        }
        let candidate: ScopedCandidate?
        if state == .published {
            guard run == "completed", outcome == nil, reference.intent == .proposeScopedEdit else { throw PreviewFailure.invalidResponse }
            candidate = try Self.candidate(value["proposal"], json: json, reference: reference, response: bytes)
        } else {
            guard value["proposal"] is NSNull else { throw PreviewFailure.invalidResponse }
            switch state {
            case .notRequested: guard reference.intent == .none, outcome == nil else { throw PreviewFailure.invalidResponse }
            case .pending: guard reference.intent == .proposeScopedEdit, ["queued", "running"].contains(run), outcome == nil else { throw PreviewFailure.invalidResponse }
            case .noCandidate: guard run == "completed", ["validation_failed", "provider_failed", "budget_exhausted"].contains(outcome) else { throw PreviewFailure.invalidResponse }
            case .unknown: guard run == "unknown" || outcome == "provider_unknown" else { throw PreviewFailure.invalidResponse }
            case .unavailable: guard ["failed", "cancelled", "context_invalid"].contains(run) else { throw PreviewFailure.invalidResponse }
            case .published: preconditionFailure("handled above")
            }
            candidate = nil
        }
        return .init(state: state, reference: reference, runStatus: run, draftOutcome: outcome, candidate: candidate, responseUTF8: bytes)
    }
    private static func readReference(_ value: Any?) throws -> MessageEditReference {
        let fields = try ScopedWireJSON.fields(["reference": value ?? NSNull()], "reference")
        return try MessageEditReference.decodeResponseReference(canonical(fields), maximumBytes: 65536)
    }
    private static func candidate(_ value: Any?, json: ScopedWireJSON, reference: MessageEditReference, response: Data) throws -> ScopedCandidate {
        let p = try ScopedWireJSON.fields(value, "proposal_id trip_id expected_version candidate_hash status expires_at content scope diff feasibility")
        let pid = try ScopedWireJSON.identifier(p["proposal_id"]), tid = try ScopedWireJSON.identifier(p["trip_id"])
        let version = try json.integer(["discovery", "proposal", "expected_version"], minimum: 1)
        let hash = try ScopedWireJSON.hash(p["candidate_hash"]), status = try ScopedWireJSON.text(p["status"])
        guard tid == reference.trip.id, version == reference.trip.expectedVersion,
              ["pending", "accepted", "rejected", "expired"].contains(status) else { throw PreviewFailure.invalidResponse }
        let scope = try ScopedWireJSON.fields(p["scope"], "version reference request")
        guard scope["version"] as? String == "TRIP-scoped-basis.1", try readReference(scope["reference"]) == reference else { throw PreviewFailure.invalidResponse }
        let request = try ScopedWireJSON.fields(scope["request"], "version request_id trip_id expected_version original_hash text language selection")
        guard request["version"] as? String == "TRIP-scoped-request.1", request["trip_id"] as? String == tid,
              try json.integer(["discovery", "proposal", "scope", "request", "expected_version"], minimum: 1) == version,
              request["original_hash"] as? String == reference.trip.contentSHA256,
              ["en", "zh-Hans"].contains(request["language"] as? String) else { throw PreviewFailure.invalidResponse }
        _ = try ScopedWireJSON.text(request["text"])
        _ = try ScopedWireJSON.identifier(request["request_id"])
        let selection: [String: Any]
        if let day = reference.trip.day {
            selection = try ScopedWireJSON.fields(request["selection"], "kind dates")
            guard selection["kind"] as? String == "dates", selection["dates"] as? [String] == [day.date] else { throw PreviewFailure.invalidResponse }
        } else {
            selection = try ScopedWireJSON.fields(request["selection"], "kind item_ids")
            guard selection["kind"] as? String == "items", selection["item_ids"] as? [String] == reference.trip.itemIDs else { throw PreviewFailure.invalidResponse }
        }
        let diff = try ScopedWireJSON.fields(p["diff"], "request_id trip_id expected_version before after")
        guard diff["trip_id"] as? String == tid, diff["request_id"] as? String == request["request_id"] as? String,
              try json.integer(["discovery", "proposal", "diff", "expected_version"], minimum: 1) == version else { throw PreviewFailure.invalidResponse }
        let before = try StructuredTripDocument.decode(canonical(diff["before"])), after = try StructuredTripDocument.decode(canonical(diff["after"]))
        guard before.contentSHA256 == reference.trip.contentSHA256, after.contentSHA256 == hash,
              after.originalUTF8 == (try canonical(p["content"])), before.version.rawValue == reference.contentVersion,
              before.version == after.version else { throw PreviewFailure.invalidResponse }
        // Verify the display association at the HTTP boundary. This does not
        // duplicate FEAS or grant scope: the server remains the unique authority.
        let old = try ScopedWireJSON.fields(diff["before"], "content_version title items sources")
        let new = try ScopedWireJSON.fields(diff["after"], "content_version title items sources")
        guard try canonical(old["title"]) == canonical(new["title"]), (try canonical(old["sources"])) == (try canonical(new["sources"])),
              let oldItems = old["items"] as? [[String: Any]], let newItems = new["items"] as? [[String: Any]],
              oldItems.count == newItems.count else { throw PreviewFailure.invalidResponse }
        for (a, b) in zip(oldItems, newItems) {
            guard let id = a["id"] as? String, id == b["id"] as? String else { throw PreviewFailure.invalidResponse }
            let fixed = a["fixed"] as? [String: Any]
            if !reference.resolvedItemIDs.contains(id) || fixed?["value"] as? Bool == true {
                guard try canonical(a) == canonical(b) else { throw PreviewFailure.invalidResponse }
            }
        }
        let report = try ScopedWireJSON.fields(p["feasibility"], "status checks output_check")
        let reportStatus = try ScopedWireJSON.text(report["status"])
        guard ["PASS", "UNKNOWN"].contains(reportStatus), let values = report["checks"] as? [Any], values.count <= 1024 else { throw PreviewFailure.invalidResponse }
        let checks = try values.map { raw -> ScopedFeasibilityCheck in
            let c = try ScopedWireJSON.fields(raw, "code status missing zh en")
            let status = try ScopedWireJSON.text(c["status"])
            guard ["PASS", "CONFLICT", "UNKNOWN", "INVALID", "NOT_APPLICABLE"].contains(status), let missing = c["missing"] as? [String] else { throw PreviewFailure.invalidResponse }
            return try .init(code: ScopedWireJSON.text(c["code"]), status: status, missing: missing,
                             english: ScopedWireJSON.text(c["en"]), chinese: ScopedWireJSON.text(c["zh"]))
        }
        let output = try ScopedWireJSON.fields(report["output_check"], "accepted codes zh en")
        guard output["accepted"] as? Bool == true, json.integers[["discovery", "proposal", "feasibility", "output_check", "accepted"]] == nil, output["codes"] is [String] else { throw PreviewFailure.invalidResponse }
        return try .init(proposalID: pid, tripID: tid, expectedVersion: version, candidateHash: hash, status: status,
            expiresAt: json.integer(["discovery", "proposal", "expires_at"], minimum: 1), before: before, after: after,
            feasibilityStatus: reportStatus, checks: checks, outputEnglish: ScopedWireJSON.text(output["en"]), outputChinese: ScopedWireJSON.text(output["zh"]), discoveryUTF8: response)
    }
}

// These frozen Trip objects contain integers only. Preserve original Unicode
// scalars and unescaped slashes, matching the owning Trip canonical decoder.
func canonical(_ value: Any?) throws -> Data {
    guard let value else { throw PreviewFailure.invalidResponse }
    return try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes, .fragmentsAllowed])
}
