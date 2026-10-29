import Foundation
import CJAPI

extension Components.Schemas.SourceTripProposalSnapshot {
    init(legacy: Components.Schemas.TripProposalSnapshot) {
        let status: Self.statusPayload
        switch legacy.status {
        case .pending: status = .pending
        case .accepted: status = .accepted
        case .rejected: status = .rejected
        case .expired: status = .expired
        case .superseded: status = .superseded
        }
        self.init(proposal_id: legacy.proposal_id, trip_id: legacy.trip_id,
                  expected_version: legacy.expected_version, basis_version: legacy.basis_version,
                  expires_at: legacy.expires_at, content_utf8_base64: legacy.content_utf8_base64,
                  document: .TripDocument(legacy.document), candidate_hash: legacy.candidate_hash, status: status)
    }
}
extension Components.Schemas.SourceTripRecord {
    init(legacy: Components.Schemas.TripRecord) {
        self.init(trip_id: legacy.trip_id, version: legacy.version,
                  content_utf8_base64: legacy.content_utf8_base64, document: .TripDocument(legacy.document))
    }
}

public struct TripSourceDisplayItem: Identifiable, Sendable {
    public let id: String
    public let text: String
    public let verification: Components.Schemas.TripDocumentItem.verificationPayload
    public let evidence: [String]
    public let category: Components.Schemas.SourceDocumentItemV1.source_categoryPayload?
    public let sourceRefs: [String]
}

extension Components.Schemas.SourceTripContent {
    public var title: String {
        switch self { case .TripDocument(let value): value.title; case .SourceDocumentV1(let value): value.title }
    }
    init(title: String, items: [Components.Schemas.TripDocumentItem]) {
        self = .TripDocument(.init(title: title, items: items))
    }
    /// Read-only UI projection; original encoded content and source metadata remain intact.
    public var items: [TripSourceDisplayItem] { displayItems }
    var displayItems: [TripSourceDisplayItem] {
        switch self {
        case .TripDocument(let value):
            return value.items.map { .init(id: $0.id, text: $0.text, verification: $0.verification,
                                           evidence: $0.evidence, category: nil, sourceRefs: []) }
        case .SourceDocumentV1(let value):
            return value.items.map { .init(id: $0.id, text: $0.text, verification: .pending,
                                           evidence: $0.evidence, category: $0.source_category, sourceRefs: $0.source_refs) }
        }
    }
    public var sources: [Components.Schemas.SourceRecordV1] {
        switch self { case .TripDocument: []; case .SourceDocumentV1(let value): value.sources }
    }
}

extension Operations.getTripProposal.Output.Ok.Body.jsonPayload {
    var sourceProposal: Components.Schemas.SourceTripProposalSnapshot {
        switch self {
        case .TripProposalResponse(let value): .init(legacy: value.proposal)
        case .SourceTripProposalResponse(let value): value.proposal
        }
    }
}
extension Operations.getTrip.Output.Ok.Body.jsonPayload {
    func sourceTrip() throws -> Components.Schemas.SourceTripRecord? {
        switch self {
        case .TripDetailResponse(let body):
            switch body.trip {
            case .TripRecord(let value): return .init(legacy: value)
            case .case2(let null): guard null.value == nil else { throw TripFailure.invalidResponse }; return nil
            }
        case .SourceTripDetailResponse(let body):
            switch body.trip {
            case .SourceTripRecord(let value): return value
            case .case2(let null): guard null.value == nil else { throw TripFailure.invalidResponse }; return nil
            }
        }
    }
}
extension Operations.listTrips.Output.Ok.Body.jsonPayload {
    var sourcePage: (trips: [Components.Schemas.SourceTripRecord], next_after: Components.Schemas.SourceTripListResponse.next_afterPayload) {
        switch self {
        case .SourceTripListResponse(let body): return (body.trips, body.next_after)
        case .TripListResponse(let body):
            let next: Components.Schemas.SourceTripListResponse.next_afterPayload
            switch body.next_after { case .case1(let id): next = .case1(id); case .case2(let null): next = .case2(null) }
            return (body.trips.map { .init(legacy: $0) }, next)
        }
    }
}
extension Operations.prepareTripConfirmation.Output.Ok.Body.jsonPayload {
    var sourcePreparation: (proposal: Components.Schemas.SourceTripProposalSnapshot, action_utf8_base64: String, expires_at: Int) {
        switch self {
        case .TripConfirmationResponse(let body): return (.init(legacy: body.proposal), body.action_utf8_base64, body.expires_at)
        case .SourceTripConfirmationResponse(let body): return (body.proposal, body.action_utf8_base64, body.expires_at)
        }
    }
}

extension TripPending {
    init(actionID: String, kind: TripActionKind, proposal: Components.Schemas.TripProposalSnapshot,
         confirmationReference: String) throws {
        try self.init(actionID: actionID, kind: kind, proposal: .init(legacy: proposal), confirmationReference: confirmationReference)
    }
    init(serverBytes: Data, proposal: Components.Schemas.TripProposalSnapshot) throws {
        try self.init(serverBytes: serverBytes, proposal: .init(legacy: proposal))
    }
}
extension TripClient {
    public func prepare(_ kind: TripActionKind, proposal: Components.Schemas.TripProposalSnapshot,
                        binding: TripBinding) async throws -> TripPreparedAction {
        try await prepare(kind, proposal: .init(legacy: proposal), binding: binding)
    }
    public func choose(_ kind: TripActionKind, proposal: Components.Schemas.TripProposalSnapshot,
                       binding: TripBinding) async throws -> TripActionResult {
        try await choose(kind, proposal: .init(legacy: proposal), binding: binding)
    }
}


extension TripSourceDisplayItem {
    func categoryLabel(_ language: TripLanguage) -> String {
        switch category {
        case .queried: language.text("Queried", "已查询")
        case .user_provided: language.text("User provided", "用户提供")
        case .estimated: language.text("Estimated", "估算")
        case .unknown: language.text("Unknown", "未知")
        case nil: language.text("Source not recorded", "来源未记录")
        }
    }
}
