import Foundation
import Observation
import CJTripClient
import CJSession

/// Supplied only by the trusted root with the same client/session/binding lifetime.
/// Context IDs are existing application selections, not generated travel or authority.
@MainActor public struct TripContainerBinding {
    fileprivate let id = UUID()
    let client: TripClient
    let trip: TripBinding
    let shellGeneration: ShellGeneration
    let session: SessionLifecycle
    let operation: SessionOperation
    let pageSize: Int
    let currentTripID: String?
    let proposalID: String?
    let synthetic: Bool
    let current: @MainActor () -> TripBinding?
    public init(client: TripClient, trip: TripBinding, shellGeneration: ShellGeneration,
                session: SessionLifecycle, sessionOperation: SessionOperation, pageSize: Int,
                currentTripID: String? = nil, proposalID: String? = nil, synthetic: Bool,
                currentBinding: @escaping @MainActor () -> TripBinding?) {
        self.client = client; self.trip = trip; self.shellGeneration = shellGeneration
        self.session = session; operation = sessionOperation; self.pageSize = pageSize
        self.currentTripID = currentTripID; self.proposalID = proposalID
        self.synthetic = synthetic; current = currentBinding
    }
}
@MainActor public struct TripContainerAction {
    fileprivate let binding: TripContainerBinding
    fileprivate let presentation: TripPresentation
    fileprivate let epoch: UUID
}

/// Contains the canonical opaque work prepared synchronously at the original UI event.
@MainActor public struct TripContainerWork {
    fileprivate let context: TripContainerAction
    fileprivate let work: TripPresentationWork
    fileprivate let token: UUID
}

@MainActor @Observable public final class TripContainerHost {
    private let shell: ShellState
    private var binding: TripContainerBinding?
    private var value: TripPresentation?
    private var epoch = UUID()
    private var selectedTripID: String?
    public private(set) var busy = false
    private var executing = false
    public var presentation: TripPresentation? { current ? value : nil }
    public var isConfigured: Bool { current }
    public var isSynthetic: Bool { current && binding?.synthetic == true }
    public var contextTripID: String? { current ? binding?.currentTripID : nil }
    public var contextProposalID: String? { current ? binding?.proposalID : nil }
    public var canLoadDetail: Bool { current && selectedTripID != nil }
    public var showsSelectedDetail: Bool {
        current && selectedTripID != nil && value?.selectedTripID == selectedTripID
    }
    public var canSubmitDecision: Bool { false }
    public init(shell: ShellState) {
        self.shell = shell
        shell.tripContainerHost?.invalidate()
        shell.tripContainerHost = self
    }
    func belongs(to shell: ShellState) -> Bool { self.shell === shell }
    private var current: Bool {
        guard let binding, !shell.messageBindingBlocked, shell.generation == binding.shellGeneration,
              binding.session.isCurrent(binding.operation) else { return false }
        let observed = binding.current()
        return self.binding?.id == binding.id && observed == binding.trip
            && shell.generation == binding.shellGeneration && !shell.messageBindingBlocked
            && binding.session.isCurrent(binding.operation)
    }
    @discardableResult public func bind(_ binding: TripContainerBinding) -> Bool {
        guard self.binding == nil, (1...100).contains(binding.pageSize),
              shell.generation == binding.shellGeneration, !shell.messageBindingBlocked,
              binding.session.isCurrent(binding.operation), binding.current() == binding.trip,
              self.binding == nil, shell.generation == binding.shellGeneration,
              !shell.messageBindingBlocked, binding.session.isCurrent(binding.operation) else { return false }
        let presentation = TripPresentation(client: binding.client)
        presentation.replace(binding: binding.trip)
        self.binding = binding; value = presentation; epoch = UUID()
        return true
    }
    public func captureAction() -> TripContainerAction? {
        guard current, !busy, let binding, let value else { return nil }
        return TripContainerAction(binding: binding, presentation: value, epoch: epoch)
    }
    private func accepts(_ action: TripContainerAction) -> Bool {
        current && !busy && binding?.id == action.binding.id && value === action.presentation && epoch == action.epoch
    }
    private func owns(_ action: TripContainerAction, _ token: UUID) -> Bool {
        current && binding?.id == action.binding.id && value === action.presentation && epoch == token
    }
    public func invalidate() {
        let original = value
        binding = nil; value = nil; epoch = UUID(); selectedTripID = nil; busy = false; executing = false
        // Canonical replace only clears its old presentation/client. No old host writes after this.
        original?.replace(binding: nil)
    }
    public func suspendForBackground() { invalidate() }
    private func reserve(_ work: TripPresentationWork?, context: TripContainerAction) -> TripContainerWork? {
        guard let work else { return nil }
        let token = UUID(); epoch = token; busy = true; executing = false
        return TripContainerWork(context: context, work: work, token: token)
    }
    public func prepareTrips(context: TripContainerAction?, more: Bool = false) -> TripContainerWork? {
        guard let context, accepts(context), !more || context.presentation.next != nil else { return nil }
        return reserve(context.presentation.prepareTrips(limit: context.binding.pageSize, more: more), context: context)
    }
    public func perform(_ prepared: TripContainerWork?) async {
        guard let prepared, owns(prepared.context, prepared.token), busy, !executing else { return }
        executing = true // duplicate queued copies cannot settle another in-flight work's busy state
        await prepared.context.presentation.perform(prepared.work)
        guard owns(prepared.context, prepared.token) else { return }
        busy = false; executing = false
    }
    @discardableResult public func selectTrip(_ id: String, context: TripContainerAction?) -> Bool {
        guard let context, accepts(context),
              context.presentation.trips.contains(where: { $0.trip_id == id }) || context.binding.currentTripID == id else { return false }
        selectedTripID = id; epoch = UUID(); return true
    }
    public func prepareTrip(context: TripContainerAction?) -> TripContainerWork? {
        guard let context, accepts(context), let id = selectedTripID else { return nil }
        return reserve(context.presentation.prepareTrip(id: id), context: context)
    }
    public func prepareProposal(context: TripContainerAction?) -> TripContainerWork? {
        guard let context, accepts(context), let id = context.binding.proposalID else { return nil }
        return reserve(context.presentation.prepareProposal(id: id), context: context)
    }
    public func loadPending(context: TripContainerAction?) {
        guard let context, accepts(context) else { return }
        let token = UUID(); epoch = token; busy = true
        context.presentation.loadPending()
        guard owns(context, token) else { return }; busy = false
    }
    @discardableResult public func selectPending(_ id: String, context: TripContainerAction?) -> Bool {
        guard let context, accepts(context), context.presentation.pendingState == .loaded,
              context.presentation.pendingActions.contains(where: { $0.actionID == id }) else { return false }
        let token = UUID(); epoch = token; busy = true
        context.presentation.selectPending(actionID: id) // canonical original-store reread
        guard owns(context, token) else { return false }
        busy = false
        return context.presentation.pendingState == .loaded && context.presentation.selectedActionID == id
    }
    public func prepareReconciliation(context: TripContainerAction?) -> TripContainerWork? {
        guard let context, accepts(context), context.presentation.selectedActionID != nil,
              case .unknown = context.presentation.decision else { return nil }
        return reserve(context.presentation.prepareReconciliation(), context: context)
    }
}
