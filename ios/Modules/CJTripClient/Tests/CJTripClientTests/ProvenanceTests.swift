import Foundation
import Testing
import CJAPI
import HTTPTypes
@testable import CJTripClient

/// Synthetic source records produced by the Python canonical Proposal builder.
private func sourceProposal() throws -> Components.Schemas.SourceTripProposalSnapshot {
    let url = try #require(Bundle.module.url(forResource: "provenance", withExtension: "json", subdirectory: "Fixtures"))
    return try JSONDecoder().decode(Components.Schemas.SourceTripProposalSnapshot.self, from: Data(contentsOf: url))
}

@Suite @MainActor struct ProvenanceTests {
    @Test func sourceLabelsChangeLanguageWithoutChangingCandidateOrSources() throws {
        let proposal = try sourceProposal()
        try validateProposal(proposal)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let before = try encoder.encode(proposal)
        let items = proposal.document.displayItems
        #expect(Set(items.compactMap { $0.category?.rawValue }) == ["queried", "user_provided", "estimated", "unknown"])
        #expect(Set(items.map { $0.categoryLabel(.english) }) == ["Queried", "User provided", "Estimated", "Unknown"])
        #expect(Set(items.map { $0.categoryLabel(.simplifiedChinese) }) == ["已查询", "用户提供", "估算", "未知"])
        #expect(items.allSatisfy { $0.verification == .pending && $0.evidence.isEmpty })
        #expect(try encoder.encode(proposal) == before)
        let legacy = Components.Schemas.SourceTripContent.TripDocument(try fixture().proposal.document)
        #expect(legacy.displayItems.allSatisfy { $0.category == nil && $0.categoryLabel(.english) == "Source not recorded" })
    }

    @Test func sourceAwareReadRetainsOriginalBytesAndRejectsMismatchedProjection() async throws {
        let h = try Harness(); defer { h.clean() }
        let proposal = try sourceProposal()
        let wire = Interceptor { request, _, _ in
            #expect(request.headerFields[HTTPField.Name("X-CJ-Trip-Content")!] == "provenance.1")
            return "{\"request_id\":\"\(trace)\",\"representation\":\"provenance.1\",\"proposal\":\(try json(proposal))}"
        }
        let read = try await h.client(wire).proposal(id: proposal.proposal_id, binding: h.binding)
        #expect(read == proposal)
        var changed = proposal
        if case .SourceDocumentV1(var document) = changed.document {
            document.sources[0].text = "not the original source"
            changed.document = .SourceDocumentV1(document)
        }
        #expect(throws: TripFailure.invalidResponse) { try validateProposal(changed) }
    }

    @Test func canonicallyEquivalentUnicodeCannotReplaceOriginalContent() throws {
        var proposal = try sourceProposal()
        guard case .SourceDocumentV1(var document) = proposal.document else { Issue.record("fixture version"); return }
        document.items[document.items.count - 1].text = "cafe\u{301}"
        proposal.document = .SourceDocumentV1(document)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        proposal.content_utf8_base64 = try encoder.encode(proposal.document).base64EncodedString()
        try validateProposal(proposal)
        document.items[document.items.count - 1].text = "caf\u{e9}"
        proposal.document = .SourceDocumentV1(document)
        #expect(throws: TripFailure.invalidResponse) { try validateProposal(proposal) }
    }

    @Test func originalSourceActionSurvivesEncryptedStoreReopen() throws {
        let h = try Harness(); defer { h.clean() }
        let proposal = try sourceProposal()
        let action = try TripPending(actionID: "source-action", kind: .accept, proposal: proposal,
                                     confirmationReference: "synthetic-test-proof")
        try h.store().append(action)
        let reopened = try #require(try h.store().pending().first)
        #expect(reopened.originalUTF8 == action.originalUTF8)
        #expect(reopened.proposal == proposal)
        try reopened.validate()
    }

    @Test func sourcePreparationKeepsExactReviewedContentAndOriginalDispatch() async throws {
        let h = try Harness(); defer { h.clean() }
        let proposal = try sourceProposal()
        let store = try h.store()
        let expires = 1_900_000_000
        let wire = Interceptor { request, bytes, operation in
            if operation == "prepareTripConfirmation" {
                #expect(request.headerFields[HTTPField.Name("X-CJ-Trip-Content")!] == "provenance.1")
                let input = try JSONDecoder().decode([String: String].self, from: bytes)
                let fields = [try #require(input["action_id"]), try #require(input["kind"]), proposal.proposal_id,
                              proposal.candidate_hash, "tc1.\(expires).\(String(repeating: "ab", count: 32))"]
                let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]
                let raw = try encoder.encode(fields).base64EncodedString()
                return "{\"request_id\":\"\(trace)\",\"representation\":\"provenance.1\",\"action_utf8_base64\":\"\(raw)\",\"expires_at\":\(expires),\"proposal\":\(try json(proposal))}"
            }
            let original = try await MainActor.run { try #require(try store.pending().first) }
            #expect(original.originalUTF8 == bytes && original.proposal == proposal)
            return try response("receipt", actionReceipt(original))
        }
        let client = try h.client(wire, store: store)
        let prepared = try await client.prepare(.accept, proposal: proposal, binding: h.binding)
        #expect(prepared.proposal == proposal)
        #expect(try store.pending().isEmpty)
        guard case .confirmed = try await client.confirm(prepared, binding: h.binding, now: expires - 120) else {
            Issue.record("Expected original action receipt"); return
        }
        #expect(await wire.calls.map(\.operation) == ["prepareTripConfirmation", "actOnTripProposal"])
    }
}
