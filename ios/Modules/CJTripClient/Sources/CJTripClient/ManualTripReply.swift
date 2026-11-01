import Foundation

public enum ManualTripProposalStatus: String, Sendable { case pending, accepted, rejected, expired, superseded }
public enum ManualTripCheckStatus: String, Sendable { case pass = "PASS", conflict = "CONFLICT", unknown = "UNKNOWN" }
public struct ManualTripCheck: Sendable {
    public let code: String
    public let status: ManualTripCheckStatus
    public let missing: [String]
    public let chinese: String
    public let english: String
    /// Original declared field values and paths; not acquired source authority.
    public let evidenceUTF8: Data
}
public struct ManualTripFeasibility: Sendable {
    public let status: ManualTripCheckStatus
    public let checks: [ManualTripCheck]
}

/// Validated response data. The client must still bind this to its original
/// opaque work, current source/session and retained command before enabling save.
public struct ManualTripPreparation: Sendable {
    public let requestID: String
    public let tripID: String
    public let expectedVersion: Int
    public let proposalID: String
    public let candidateHash: String
    public let status: ManualTripProposalStatus
    public let before: StructuredTripDocument
    public let after: StructuredTripDocument
    public let originalDiffUTF8: Data
    public let expiresAt: Int?
    public let feasibility: ManualTripFeasibility?
    let originalInputSHA256: String
}
public struct ManualTripReceipt: Sendable {
    public let actionID: String
    public let proposalID: String
    public let candidateHash: String
    public let tripID: String
    public let committedVersion: Int
}
public struct ManualTripSaveInput: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let actionID: String
    public let originalUTF8: Data
    let preparation: ManualTripPreparation
    let original: ManualTripInput
    public var description: String { "<manual trip save input>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }

    /// Data serialization only. The trusted editor, not a decoded DTO, supplies
    /// save authority and mints the action ID after its complete preflight.
    init(actionID: String, preparation: ManualTripPreparation, original: ManualTripInput) throws {
        guard tripID(actionID), preparation.status == .pending,
              same(preparation.originalInputSHA256, digest(original.originalUTF8)) else { throw TripFailure.invalidInput }
        self.actionID = actionID; self.preparation = preparation; self.original = original
        originalUTF8 = tripCanonicalJSON(.object([
            "version": .string(original.needs == nil ? "TRIP-manual-save.1" : "TRIP-needs-save.1"),
            "action_id": .string(actionID), "proposal_id": .string(preparation.proposalID), "candidate_hash": .string(preparation.candidateHash)]))
    }
}

public enum ManualTripReplies {
    public static func preparation(_ bytes: Data, original: ManualTripInput, requestID: String) throws -> ManualTripPreparation? {
        let f = try envelope(bytes, member: "preparation", needs: original.needs != nil, requestID: requestID)
        return try f.required("preparation").nullable { value in
            let expected = original.needs == nil
                ? "proposal_id trip_id expected_version basis expires_at candidate_hash status content diff feasibility"
                : "proposal_id trip_id expected_version candidate_hash status content diff"
            let p = try value.fields(expected), hash = try p.required("candidate_hash").text()
            guard try same(p.required("trip_id").text(), original.original.tripID),
                  try tripWireVersion(p.required("expected_version")) == original.original.version,
                  tripHash(hash), let status = ManualTripProposalStatus(rawValue: try p.required("status").text()) else { throw TripFailure.invalidResponse }
            let proposalID = try tripWireID(p.required("proposal_id"))
            let after = try StructuredTripDocument.decode(tripCanonicalJSON(p.required("content")))
            let diff = try p.required("diff").fields("before after request_id trip_id expected_version")
            guard try same(diff.required("request_id").text(), original.requestID),
                  try same(diff.required("trip_id").text(), original.original.tripID),
                  try tripWireVersion(diff.required("expected_version")) == original.original.version,
                  try tripCanonicalJSON(diff.required("before")) == original.original.document.originalUTF8,
                  try tripCanonicalJSON(diff.required("after")) == after.originalUTF8,
                  after.version == original.original.document.version else { throw TripFailure.invalidResponse }
            try validateDelta(before: diff.required("before"), after: diff.required("after"), original: original)
            let expires: Int?, feasibility: ManualTripFeasibility?
            if original.needs == nil {
                guard try p.required("basis").text() == "manual-unbound.1" else { throw TripFailure.invalidResponse }
                expires = try tripWireVersion(p.required("expires_at"))
                feasibility = try readFeasibility(p.required("feasibility"))
            } else { expires = nil; feasibility = nil }
            return try .init(requestID: original.requestID, tripID: original.original.tripID, expectedVersion: original.original.version,
                         proposalID: proposalID, candidateHash: hash, status: status, before: original.original.document,
                         after: after, originalDiffUTF8: tripCanonicalJSON(p.required("diff")), expiresAt: expires, feasibility: feasibility,
                         originalInputSHA256: digest(original.originalUTF8))
        }
    }
    public static func receipt(_ bytes: Data, original: ManualTripSaveInput, requestID: String) throws -> ManualTripReceipt? {
        let f = try envelope(bytes, member: "receipt", needs: original.original.needs != nil, requestID: requestID)
        return try f.required("receipt").nullable { value in
            let r = try value.fields("action_id kind proposal_id candidate_hash trip_id committed_version")
            let version = try tripWireVersion(r.required("committed_version")), before = original.original.original.version
            guard try same(r.required("action_id").text(), original.actionID), try r.required("kind").text() == "accept",
                  try same(r.required("proposal_id").text(), original.preparation.proposalID),
                  try same(r.required("candidate_hash").text(), original.preparation.candidateHash),
                  try same(r.required("trip_id").text(), original.original.original.tripID),
                  before < Int.max, version == before + 1 else { throw TripFailure.invalidResponse }
            return .init(actionID: original.actionID, proposalID: original.preparation.proposalID,
                candidateHash: original.preparation.candidateHash, tripID: original.original.original.tripID, committedVersion: version)
        }
    }
    private static func envelope(_ bytes: Data, member: String, needs: Bool, requestID: String) throws -> [String: TripJSONValue] {
        guard !bytes.isEmpty, bytes.count <= 1_000_000, UUID(uuidString: requestID) != nil else { throw TripFailure.invalidResponse }
        var parser = StrictTripJSON(bytes: Array(bytes)); let value = try parser.document()
        try factBounds(value, maxDepth: 32, maxNodes: 32768)
        let f = try value.fields("version request_id " + member)
        guard try f.required("version").text() == (needs ? "TRIP-needs-result.1" : "TRIP-manual-result.1"),
              try same(f.required("request_id").text(), requestID) else { throw TripFailure.invalidResponse }
        return f
    }
    private static func readFeasibility(_ value: TripJSONValue) throws -> ManualTripFeasibility {
        let f = try value.fields("version status checks")
        guard try f.required("version").text() == "FEASIBILITY-TRIP@1.0",
              let status = ManualTripCheckStatus(rawValue: try f.required("status").text()) else { throw TripFailure.invalidResponse }
        let checks = try f.required("checks").elements().map { value -> ManualTripCheck in
            let c = try value.fields("code status missing zh en evidence")
            guard let status = ManualTripCheckStatus(rawValue: try c.required("status").text()) else { throw TripFailure.invalidResponse }
            let evidence = try c.required("evidence").elements()
            for item in evidence {
                let e = try item.fields("path declaration")
                _ = try boundedTripText(e.required("path"), maximum: 4096)
            }
            return try .init(code: boundedTripText(c.required("code"), maximum: 128), status: status,
                missing: c.required("missing").elements().map { try boundedTripText($0, maximum: 4096) },
                chinese: boundedTripText(c.required("zh"), maximum: 4096), english: boundedTripText(c.required("en"), maximum: 4096),
                evidenceUTF8: tripCanonicalJSON(c.required("evidence")))
        }
        // This frozen adapter never proves overall feasibility. A conflicting
        // candidate is refused before publication, not offered as a ready diff.
        guard status == .unknown, !checks.contains(where: { $0.status == .conflict }) else { throw TripFailure.invalidResponse }
        return .init(status: status, checks: checks)
    }

    /// Response consistency only: validates selected values and every retained
    /// field against the captured original. Does not generate a patch or FEAS result.
    private static func validateDelta(before: TripJSONValue, after: TripJSONValue, original: ManualTripInput) throws {
        let b = try before.object(), a = try after.object()
        guard try same(a.required("title").text(), original.title ?? original.original.document.title) else { throw TripFailure.invalidResponse }
        let beforeItems = try b.required("items").elements(), afterItems = try a.required("items").elements()
        let expectedOrder = original.order ?? original.original.document.items.map(\.id)
        guard afterItems.count == beforeItems.count else { throw TripFailure.invalidResponse }
        var originals: [String: [String: TripJSONValue]] = [:]
        for node in beforeItems { let item = try node.object(); originals[try item.required("id").text()] = item }
        for (index, node) in afterItems.enumerated() {
            let item = try node.object(), id = try item.required("id").text()
            guard same(id, expectedOrder[index]), let old = originals[id] else { throw TripFailure.invalidResponse }
            let selected = original.changes.filter { same($0.itemID, id) }
            for change in selected {
                guard tripCanonicalJSON(try item.required(change.field.rawValue)) == change.valueUTF8 else { throw TripFailure.invalidResponse }
            }
            let textChanged = tripCanonicalJSON(try item.required("text")) != tripCanonicalJSON(try old.required("text"))
            let scheduleChanged = tripCanonicalJSON(try item.required("schedule")) != tripCanonicalJSON(try old.required("schedule"))
            var allowed = Set(selected.map { $0.field.rawValue })
            if textChanged || scheduleChanged {
                allowed.formUnion(["verification", "evidence"])
                guard try item.required("verification").text() == "pending", try item.required("evidence").elements().isEmpty else { throw TripFailure.invalidResponse }
            }
            if textChanged {
                allowed.formUnion(["source_category", "source_refs"])
                guard try item.required("source_category").text() == "user_provided", try item.required("source_refs").elements().isEmpty else { throw TripFailure.invalidResponse }
            }
            for field in old.keys where !allowed.contains(field) {
                guard tripCanonicalJSON(try item.required(field)) == tripCanonicalJSON(old[field]!) else { throw TripFailure.invalidResponse }
            }
        }
        // Only prune no-longer-referenced source copies; retain original bytes/order.
        var refs = Set<String>()
        for node in afterItems {
            let item = try node.object()
            for ref in try item.required("source_refs").elements() { refs.insert(try ref.text()) }
        }
        let retained = try b.required("sources").elements().filter { node in
            let source = try node.object(); return refs.contains(try source.required("id").text())
        }
        guard tripCanonicalJSON(.array(retained)) == tripCanonicalJSON(try a.required("sources")) else { throw TripFailure.invalidResponse }
    }
}
