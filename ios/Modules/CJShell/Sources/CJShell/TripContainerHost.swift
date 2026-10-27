import Foundation
import Observation
import CJTripClient
import CJSession
import CJManualPreviewClient

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
    let manualPreviewResources: ManualPreviewResources?
    let current: @MainActor () -> TripBinding?
    public init(client: TripClient, trip: TripBinding, shellGeneration: ShellGeneration,
                session: SessionLifecycle, sessionOperation: SessionOperation, pageSize: Int,
                currentTripID: String? = nil, proposalID: String? = nil, synthetic: Bool,
                manualPreviewResources: ManualPreviewResources? = nil,
                currentBinding: @escaping @MainActor () -> TripBinding?) {
        self.client = client; self.trip = trip; self.shellGeneration = shellGeneration
        self.session = session; operation = sessionOperation; self.pageSize = pageSize
        self.currentTripID = currentTripID; self.proposalID = proposalID
        self.synthetic = synthetic; self.manualPreviewResources = manualPreviewResources; current = currentBinding
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
    private var manualForeground = false
    private var previewEntry: ManualPreviewEntry?
    private var previewEditor: PreviewEditor?
    @ObservationIgnored private var manualReadTask: Task<AcceptedTripDetailSnapshot?, any Error>?
    private var manualWorkToken: UUID?
    @ObservationIgnored private let makeManualEditor: ManualEditorFactory
    public private(set) var manualEditorState: ManualEditorLoadState = .unavailable
    public var manualPreviewIdentity: UUID? { previewEntry?.id }
    public var hasManualResources: Bool { current && binding?.manualPreviewResources != nil }
    public var canPrepareManualEditor: Bool { current && manualForeground && !busy && selectedTripID != nil && binding?.manualPreviewResources != nil }
    public var presentation: TripPresentation? { current ? value : nil }
    public var isConfigured: Bool { current }
    public var isSynthetic: Bool { current && binding?.synthetic == true }
    public var contextTripID: String? { current ? binding?.currentTripID : nil }
    public var contextProposalID: String? { current ? binding?.proposalID : nil }
    public var canLoadDetail: Bool { current && selectedTripID != nil }
    public var showsSelectedDetail: Bool {
        current && selectedTripID != nil && value?.selectedTripID == selectedTripID
    }
    public var canSubmitDecision: Bool { current && value?.acceptsUserActions == true }
    public convenience init(shell: ShellState) {
        self.init(shell: shell, makeManualEditor: { trip, source, session, operation, resources in
            try PreviewEditor(trip: trip, source: source, endpoint: resources.endpoint, session: session, operation: operation,
                              credentials: resources.credentials, previewRequestTimeout: resources.requestTimeout, previewResourceTimeout: resources.resourceTimeout)
        })
    }
    init(shell: ShellState, makeManualEditor: @escaping ManualEditorFactory) {
        self.shell = shell; self.makeManualEditor = makeManualEditor
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
        manualEditorState = binding.manualPreviewResources == nil ? .unavailable : .idle
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
        let oldRead = manualReadTask
        manualReadTask = nil; manualWorkToken = nil
        retireManualEditor()
        let original = value
        binding = nil; value = nil; epoch = UUID(); selectedTripID = nil; busy = false; executing = false
        // Canonical replace only clears its old presentation/client. No old host writes after this.
        manualEditorState = .unavailable
        original?.replace(binding: nil)
        oldRead?.cancel() // original task only; no old-lifetime host write follows cancellation callbacks
    }
    public func suspendForBackground() { manualForeground = false; invalidate() }
    private func reserve(_ work: TripPresentationWork?, context: TripContainerAction) -> TripContainerWork? {
        guard let work, accepts(context) else { return nil }
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
        retireManualEditor()
        context.binding.client.invalidateDetailSnapshots() // callback-free canonical selection retirement, including ABA
        selectedTripID = id; epoch = UUID(); return true
    }
    public func prepareTrip(context: TripContainerAction?) -> TripContainerWork? {
        guard let context, accepts(context), let id = selectedTripID else { return nil }
        retireManualEditor()
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

@MainActor extension TripContainerHost {
    public func setManualForeground(_ active: Bool) {
        manualForeground = active
        if !active {
            let oldRead = manualReadTask
            manualReadTask = nil
            if let token = manualWorkToken, epoch == token {
                epoch = UUID(); busy = false; executing = false
                manualEditorState = binding?.manualPreviewResources == nil ? .unavailable : .idle
            }
            manualWorkToken = nil
            retireManualEditor()
            oldRead?.cancel() // clear old bookkeeping before any cancellation callback
        }
    }
    public func cancelManualSourceRead() {
        guard let token = manualWorkToken, epoch == token else { return }
        let oldRead = manualReadTask
        manualReadTask = nil; manualWorkToken = nil
        epoch = UUID(); busy = false; executing = false
        manualEditorState = binding?.manualPreviewResources == nil ? .unavailable : .idle
        oldRead?.cancel() // original task only; no writes after cancellation callbacks
    }
    private func retireManualEditor() {
        let original = previewEditor
        previewEditor = nil; previewEntry = nil
        original?.retire() // local editor only; cannot retire a newer Trip source
    }
    public func retireManualPreview(_ entry: ManualPreviewEntry) {
        guard previewEntry?.id == entry.id else { return }
        retireManualEditor()
    }
    public func manualEditor(for entry: ManualPreviewEntry) -> PreviewEditor? {
        let token = epoch
        guard manualForeground, previewEntry?.id == entry.id, let editor = previewEditor, current,
              epoch == token, previewEntry?.id == entry.id, previewEditor === editor else { return nil }
        return editor
    }
    private func finishManualLoad(_ work: ManualEditorWork, state: ManualEditorLoadState) {
        guard binding?.id == work.context.binding.id, value === work.context.presentation,
              epoch == work.token, manualWorkToken == work.token, shell.generation == work.context.binding.shellGeneration else { return }
        manualReadTask = nil; manualWorkToken = nil
        busy = false; executing = false; manualEditorState = state
    }
    private func ownsManualWithoutCallbacks(_ work: ManualEditorWork) -> Bool {
        manualForeground && binding?.id == work.context.binding.id && value === work.context.presentation && epoch == work.token
            && shell.generation == work.context.binding.shellGeneration && !shell.messageBindingBlocked
            && work.context.binding.session.isCurrent(work.context.binding.operation)
    }
    /// A selected ID requests the guarded GET. Only its closed returned snapshot can open an editor.
    public func prepareManualEditor(context: TripContainerAction?) -> ManualEditorWork? {
        guard let context, accepts(context), manualForeground, let id = selectedTripID,
              let resources = context.binding.manualPreviewResources else { return nil }
        retireManualEditor()
        do {
            let request = try context.binding.client.prepareDetailSnapshot(id: id, binding: context.binding.trip)
            guard accepts(context), manualForeground else { return nil }
            let token = UUID(); epoch = token; manualWorkToken = token; busy = true; executing = false; manualEditorState = .loading
            return ManualEditorWork(context: context, request: request, token: token, resources: resources)
        } catch {
            if accepts(context), manualForeground { manualEditorState = .failed }
            return nil
        }
    }
    public func performManualEditor(_ work: ManualEditorWork?) async -> ManualPreviewEntry? {
        guard let work, owns(work.context, work.token), ownsManualWithoutCallbacks(work), busy, !executing else { return nil }
        executing = true
        do {
            let read = Task { try await work.context.binding.client.detailSnapshot(for: work.request) }
            manualReadTask = read
            let source = try await withTaskCancellationHandler(operation: { try await read.value }, onCancel: { read.cancel() })
            guard owns(work.context, work.token), ownsManualWithoutCallbacks(work) else {
                finishManualLoad(work, state: .failed); return nil
            }
            guard let source else { finishManualLoad(work, state: .missing); return nil }
            let candidate = try makeManualEditor(work.context.binding.client, source, work.context.binding.session,
                                                 work.context.binding.operation, work.resources)
            // The final source check may edit/retire selection. No callback follows the local fence.
            guard candidate.display() != nil, ownsManualWithoutCallbacks(work) else {
                candidate.retire(); finishManualLoad(work, state: .failed); return nil
            }
            let entry = ManualPreviewEntry()
            previewEditor = candidate; previewEntry = entry
            finishManualLoad(work, state: .ready)
            return entry
        } catch {
            finishManualLoad(work, state: .failed)
            return nil // no raw decoder/transport error or private content is projected
        }
    }
}
