import Foundation
import Observation
import CJAPI

public enum TripLoadState: Equatable, Sendable {
    case unavailable, idle, loading, loaded, missing, failed, unknown
}
public enum TripDecisionState: Sendable {
    case unavailable, submitting, unknown, reconciling
    case confirmed(Components.Schemas.TripActionReceipt)
    /// Asking the server to prepare a signed original action; nothing is submitted.
    case preparing
    /// Server-prepared action shown for the user's explicit confirmation; nothing is submitted yet.
    case awaitingConfirmation(TripPreparedAction)
    /// Preparation was refused or failed; no action exists, so the user may review again.
    case prepareFailed
    /// The original action can no longer commit (no receipt, signed confirmation expired).
    case expiredUncommitted
}

/// Opaque, one-use UI work captured synchronously before a Task is queued.
/// Not an account, server confirmation, or permission to write.
public struct TripPresentationWork: Sendable {
    fileprivate enum Kind: Sendable {
        case proposal(String), detail(String), list(Int, TripCursor?), reconcile(String)
        case prepare(String, TripActionKind), confirm(TripPreparedAction)
    }
    fileprivate let owner: UUID
    fileprivate let lifetime: UUID
    fileprivate let binding: TripBinding
    fileprivate let request: UUID
    fileprivate let detailSource: UUID?
    fileprivate let kind: Kind
}

/// Embed one state owner in a trusted host. Language changes never recreate it.
@MainActor @Observable public final class TripPresentation {
    public private(set) var binding: TripBinding?
    public private(set) var selectedProposalID: String?
    public private(set) var selectedTripID: String?
    public private(set) var proposal: Components.Schemas.TripProposalSnapshot?
    public private(set) var trip: Components.Schemas.TripRecord?
    public private(set) var trips: [Components.Schemas.TripRecord] = []
    public private(set) var proposalState: TripLoadState = .unavailable
    public private(set) var detailState: TripLoadState = .unavailable
    public private(set) var listState: TripLoadState = .unavailable
    public private(set) var decision: TripDecisionState = .unavailable
    public private(set) var next: TripCursor?
    public private(set) var pendingActions: [TripPending] = []
    public private(set) var pendingState: TripLoadState = .unavailable
    public private(set) var selectedActionID: String?
    private let client: TripClient?
    private let owner = UUID()
    private var lifetime = UUID()
    private var proposalRequest = UUID()
    private var detailRequest = UUID()
    private var listRequest = UUID()
    private var pendingRequest = UUID()
    private var startedProposal: UUID?
    private var startedDetail: UUID?
    private var startedList: UUID?
    public init(client: TripClient?) { self.client = client }

    /// Synchronous host fence before identity, environment or selection replacement.
    public func replace(binding: TripBinding?) {
        lifetime = UUID(); proposalRequest = UUID(); detailRequest = UUID(); listRequest = UUID(); pendingRequest = UUID()
        startedProposal = nil; startedDetail = nil; startedList = nil
        client?.invalidate(); self.binding = binding
        proposal = nil; trip = nil; trips = []; next = nil
        selectedProposalID = nil; selectedTripID = nil; selectedActionID = nil; decision = .unavailable
        pendingActions = []; pendingState = .unavailable
        proposalState = .unavailable; detailState = .unavailable; listState = .unavailable
    }
    private func isCurrent(_ binding: TripBinding, _ lifetime: UUID) -> Bool {
        guard self.binding == binding, self.lifetime == lifetime, let client else { return false }
        return client.ownsBinding(binding) && self.binding == binding && self.lifetime == lifetime
    }
    private func work(_ kind: TripPresentationWork.Kind, request: UUID) -> TripPresentationWork? {
        guard let binding, client != nil else { return nil }
        let source: UUID?
        if case .detail = kind { source = client?.detailSnapshotSource } else { source = nil }
        return .init(owner: owner, lifetime: lifetime, binding: binding, request: request, detailSource: source, kind: kind)
    }
    /// Capture at the lifecycle event/button click, not inside its asynchronous Task.
    public func prepareProposal(id: String) -> TripPresentationWork? {
        proposalRequest = UUID(); selectedProposalID = id; selectedActionID = nil
        proposal = nil; decision = .unavailable
        let work = work(.proposal(id), request: proposalRequest)
        proposalState = work == nil ? .unavailable : .loading
        return work
    }
    public func prepareTrip(id: String) -> TripPresentationWork? {
        if let client {
            guard let binding else { detailState = .unavailable; return nil }
            let originalLifetime = lifetime; let originalRequest = detailRequest
            do { try client.retireDetailSnapshots(ifCurrent: binding) }
            catch {
                guard lifetime == originalLifetime, detailRequest == originalRequest else { return nil }
                detailState = .unavailable; return nil
            }
        }
        detailRequest = UUID(); selectedTripID = id; trip = nil
        let work = work(.detail(id), request: detailRequest)
        detailState = work == nil ? .unavailable : .loading
        return work
    }
    public func prepareTrips(limit: Int, more: Bool = false) -> TripPresentationWork? {
        if more && (next == nil || listState == .loading) { return nil }
        let cursor = more ? next : nil
        listRequest = UUID()
        if !more { trips = []; next = nil }
        let work = work(.list(limit, cursor), request: listRequest)
        listState = work == nil ? .unavailable : .loading
        return work
    }
    /// True only when the host granted live writes with a durable pending store.
    public var acceptsUserActions: Bool { client?.acceptsUserActions == true }
    /// Step 1 of a decision: ask the server to prepare the signed original action. Read-only.
    public func prepareDecision(_ kind: TripActionKind) -> TripPresentationWork? {
        guard acceptsUserActions, selectedActionID == nil, let proposal, proposal.status == .pending,
              let id = selectedProposalID, same(id, proposal.proposal_id) else { return nil }
        switch decision {
        case .unavailable, .prepareFailed, .expiredUncommitted: break
        default: return nil
        }
        proposalRequest = UUID()
        guard let work = work(.prepare(id, kind), request: proposalRequest) else { return nil }
        decision = .preparing
        return work
    }
    /// Step 2: the user explicitly confirmed the prepared action shown on screen.
    public func prepareConfirmation(now: Int = Int(Date().timeIntervalSince1970)) -> TripPresentationWork? {
        guard case .awaitingConfirmation(let prepared) = decision, selectedActionID == nil else { return nil }
        guard prepared.expiresAt - confirmationClockMargin > now else { decision = .expiredUncommitted; return nil }
        proposalRequest = UUID()
        guard let work = work(.confirm(prepared), request: proposalRequest) else { return nil }
        selectedActionID = prepared.pending.actionID
        decision = .submitting
        return work
    }
    /// Drops a prepared action before confirmation. Preparation wrote nothing, so this is safe.
    public func cancelConfirmation() {
        guard case .awaitingConfirmation = decision else { return }
        proposalRequest = UUID(); decision = .unavailable
    }
    public func prepareReconciliation() -> TripPresentationWork? {
        guard case .unknown = decision, let actionID = selectedActionID else { return nil }
        proposalRequest = UUID()
        guard let work = work(.reconcile(actionID), request: proposalRequest) else { return nil }
        decision = .reconciling
        return work
    }
    private func matches(_ work: TripPresentationWork) -> Bool {
        guard work.owner == owner, work.lifetime == lifetime, work.binding == binding else { return false }
        switch work.kind {
        case .proposal(let id): return proposalRequest == work.request && selectedProposalID.map { same($0, id) } == true
        case .reconcile(let id): return proposalRequest == work.request && selectedActionID.map { same($0, id) } == true
        case .prepare(let id, _): return proposalRequest == work.request && selectedActionID == nil && selectedProposalID.map { same($0, id) } == true
        case .confirm(let prepared): return proposalRequest == work.request && selectedActionID.map { same($0, prepared.pending.actionID) } == true
        case .detail(let id):
            return detailRequest == work.request && selectedTripID.map { same($0, id) } == true
                && work.detailSource == client?.detailSnapshotSource
        case .list: return listRequest == work.request
        }
    }
    private func isCurrent(_ work: TripPresentationWork) -> Bool {
        // ownsBinding can synchronously reenter UI: compare the original selection again afterward.
        matches(work) && isCurrent(work.binding, work.lifetime) && matches(work)
    }
    private func claim(_ work: TripPresentationWork) -> Bool {
        switch work.kind {
        case .proposal, .reconcile, .prepare, .confirm:
            guard startedProposal != work.request else { return false }; startedProposal = work.request
        case .detail:
            guard startedDetail != work.request else { return false }; startedDetail = work.request
        case .list:
            guard startedList != work.request else { return false }; startedList = work.request
        }
        return true
    }
    public func perform(_ work: TripPresentationWork) async {
        guard isCurrent(work), claim(work), let client else { return }
        do {
            switch work.kind {
            case .proposal(let id):
                let value = try await client.proposal(id: id, binding: work.binding)
                guard isCurrent(work) else { return }; proposal = value; proposalState = .loaded
            case .detail(let id):
                guard let source = work.detailSource else { return }
                let value = try await client.selectedDetail(id: id, binding: work.binding, source: source)
                guard isCurrent(work) else { return }; trip = value; detailState = value == nil ? .missing : .loaded
            case .list(let limit, let cursor):
                let page = try await client.list(limit: limit, after: cursor, binding: work.binding)
                guard isCurrent(work) else { return }; trips.append(contentsOf: page.trips); next = page.next; listState = .loaded
            case .reconcile(let actionID):
                let result = try await client.query(actionID: actionID, binding: work.binding)
                guard isCurrent(work) else { return }
                apply(result)
            case .prepare(_, let kind):
                guard let proposal else { return }
                let prepared = try await client.prepare(kind, proposal: proposal, binding: work.binding)
                guard isCurrent(work) else { return }
                decision = .awaitingConfirmation(prepared)
            case .confirm(let prepared):
                let result = try await client.confirm(prepared, binding: work.binding, now: Int(Date().timeIntervalSince1970))
                guard isCurrent(work) else { return }
                apply(result)
            }
        } catch {
            guard isCurrent(work) else { return }
            switch work.kind {
            case .proposal: proposalState = .failed
            case .detail: detailState = .failed
            case .list: listState = .failed
            case .reconcile: decision = .unknown
            // Preparation writes nothing; the user may review and try again.
            case .prepare: decision = .prepareFailed
            // After confirmation the outcome may be committed: only the original action may be queried.
            case .confirm: decision = .unknown
            }
        }
    }
    public func loadPending() {
        guard let binding, let client else { pendingState = .unavailable; return }
        let lifetime = lifetime; let request = UUID(); pendingRequest = request
        do {
            let actions = try client.pending(binding: binding)
            guard isCurrent(binding, lifetime), pendingRequest == request else { return }
            pendingActions = actions; pendingState = .loaded
        } catch {
            guard isCurrent(binding, lifetime), pendingRequest == request else { return }; pendingState = .failed
        }
    }
    public func selectPending(actionID: String) {
        let originalLifetime = lifetime; let originalBinding = binding
        let request = UUID(); proposalRequest = request
        selectedActionID = nil; selectedProposalID = nil; proposal = nil
        decision = .unavailable; proposalState = .loading
        loadPending()
        guard lifetime == originalLifetime, binding == originalBinding, proposalRequest == request else { return }
        guard pendingState == .loaded else { proposalState = .failed; return }
        guard let action = pendingActions.first(where: { same($0.actionID, actionID) }) else { proposalState = .missing; return }
        selectedActionID = action.actionID
        selectedProposalID = action.proposal.proposal_id; proposal = action.proposal
        proposalState = .loaded; decision = .unknown
    }
    /// No reviewed flag or fabricated confirmation reference can enable this operation.
    private func apply(_ result: TripActionResult) {
        switch result {
        case .confirmed(let receipt): decision = .confirmed(receipt)
        case .notObserved: decision = .unknown
        case .expiredUncommitted: decision = .expiredUncommitted
        }
    }
    /// Superseded by `prepareDecision` + `prepareConfirmation`; kept so old hosts stay inert.
    public func choose(_ kind: TripActionKind) {
        guard selectedActionID == nil else { return }
        decision = .unavailable
    }
}
