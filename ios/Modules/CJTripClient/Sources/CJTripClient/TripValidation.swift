import Foundation
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
