import Foundation
import CryptoKit
import CJAPI

func validateDocument(_ document: Components.Schemas.TripDocument, original: String) throws {
    guard let bytes = Data(base64Encoded: original), bytes.base64EncodedString() == original,
          String(data: bytes, encoding: .utf8) != nil,
          !document.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
          !document.items.isEmpty else { throw TripFailure.invalidResponse }
    var strict = StrictTripJSON(bytes: Array(bytes)); try strict.check()
    // Use the official generated model; never rebuild original content or hash presentation JSON.
    let decoded = try JSONDecoder().decode(Components.Schemas.TripDocument.self, from: bytes)
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard try encoder.encode(decoded) == encoder.encode(document) else { throw TripFailure.invalidResponse }
    var ids = Set<Data>()
    for item in document.items {
        guard tripID(item.id), ids.insert(Data(item.id.utf8)).inserted,
              !item.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              item.evidence.allSatisfy({ !$0.isEmpty }),
              item.verification != .verified || !item.evidence.isEmpty else { throw TripFailure.invalidResponse }
    }
}
func validateRecord(_ trip: Components.Schemas.TripRecord) throws {
    guard tripID(trip.trip_id), trip.version > 0 else { throw TripFailure.invalidResponse }
    try validateDocument(trip.document, original: trip.content_utf8_base64)
}
func validateProposal(_ proposal: Components.Schemas.TripProposalSnapshot) throws {
    guard tripID(proposal.proposal_id), tripID(proposal.trip_id), tripID(proposal.basis_version),
          proposal.expected_version >= 0, proposal.expires_at > 0, tripHash(proposal.candidate_hash) else { throw TripFailure.invalidResponse }
    try validateDocument(proposal.document, original: proposal.content_utf8_base64)
}

func validateDocument(_ document: Components.Schemas.SourceTripContent, original: String) throws {
    if case .TripDocument(let legacy) = document {
        try validateDocument(legacy, original: original)
        return
    }
    guard let bytes = Data(base64Encoded: original), bytes.base64EncodedString() == original,
          String(data: bytes, encoding: .utf8) != nil else { throw TripFailure.invalidResponse }
    var strict = StrictTripJSON(bytes: Array(bytes)); try strict.check()
    let decoded = try JSONDecoder().decode(Components.Schemas.SourceTripContent.self, from: bytes)
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    guard try encoder.encode(decoded) == encoder.encode(document), case .SourceDocumentV1(let sourceDocument) = document,
          !sourceDocument.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
          (1...60).contains(sourceDocument.items.count), sourceDocument.sources.count <= 40 else {
        throw TripFailure.invalidResponse
    }
    var sources: [String: Components.Schemas.SourceRecordV1] = [:]
    for source in sourceDocument.sources {
        guard tripID(source.id), sources[source.id] == nil, !source.reference.isEmpty,
              !source.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              (source.kind == .message) == (source.evidence_level == .user_statement),
              let snapshot = Data(base64Encoded: source.snapshot_utf8_base64),
              snapshot.base64EncodedString() == source.snapshot_utf8_base64,
              source.snapshot_sha256 == SHA256.hash(data: snapshot).map({ String(format: "%02x", $0) }).joined(),
              let record = try JSONSerialization.jsonObject(with: snapshot) as? [String: Any],
              let snapshotText = record["display_text"] as? String, same(snapshotText, source.text) else { throw TripFailure.invalidResponse }
        var strictSnapshot = StrictTripJSON(bytes: Array(snapshot)); try strictSnapshot.check()
        sources[source.id] = source
    }
    var ids = Set<Data>(), used = Set<String>()
    for item in sourceDocument.items {
        guard tripID(item.id), ids.insert(Data(item.id.utf8)).inserted,
              !item.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              item.evidence.isEmpty else { throw TripFailure.invalidResponse }
        if item.source_category == .unknown {
            guard item.source_refs.isEmpty else { throw TripFailure.invalidResponse }
        } else {
            guard item.source_refs.count == 1, let reference = item.source_refs.first,
                  let source = sources[reference], same(item.text, source.text) else { throw TripFailure.invalidResponse }
            let expected: Components.Schemas.SourceRecordV1.kindPayload
            switch item.source_category {
            case .user_provided: expected = .message
            case .queried: expected = .place
            case .estimated: expected = .route_estimate
            case .unknown: throw TripFailure.invalidResponse
            }
            guard source.kind == expected else { throw TripFailure.invalidResponse }
            used.insert(reference)
        }
    }
    guard used == Set(sources.keys) else { throw TripFailure.invalidResponse }
}
func validateRecord(_ trip: Components.Schemas.SourceTripRecord) throws {
    guard tripID(trip.trip_id), trip.version > 0 else { throw TripFailure.invalidResponse }
    try validateDocument(trip.document, original: trip.content_utf8_base64)
}
func validateProposal(_ proposal: Components.Schemas.SourceTripProposalSnapshot) throws {
    guard tripID(proposal.proposal_id), tripID(proposal.trip_id), tripID(proposal.basis_version),
          proposal.expected_version >= 0, proposal.expires_at > 0, tripHash(proposal.candidate_hash) else { throw TripFailure.invalidResponse }
    try validateDocument(proposal.document, original: proposal.content_utf8_base64)
}
